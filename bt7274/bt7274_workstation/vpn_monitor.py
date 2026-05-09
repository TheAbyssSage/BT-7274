"""
VPN monitoring for BT-7274.
Detects Proton VPN connect/disconnect events.
Speaks voice lines on state changes.
Logs all state changes to telemetry/network.
"""

import re
import time
import threading
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable

from bt7274.bt7274_assistant.ui import info, success, warning, error, status
from bt7274.bt7274_workstation.log_manager import get_telemetry_network_dir, append_log, daily_log_path


class VPNMonitor:
    """Monitors VPN connection state and announces changes."""

    def __init__(self, config: Optional[dict] = None, tts_callback: Optional[Callable[[str], None]] = None):
        self.config = config or {}
        self.enabled = self.config.get("enabled", True)
        self.interval = self.config.get("interval", 10)  # seconds between checks
        self.provider = self.config.get("provider", "protonvpn")
        self.auto_cloak = self.config.get("auto_cloak", False)
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_state: Optional[str] = None  # "connected", "disconnected", or None
        self._last_server: Optional[str] = None
        self._last_wifi: Optional[str] = None
        self._tts_callback = tts_callback
        self._log_dir = get_telemetry_network_dir()
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._public_wifi_warned = False

    def _get_wifi_ssid(self) -> Optional[str]:
        """Get current Wi-Fi SSID on macOS."""
        try:
            result = subprocess.run(
                ["networksetup", "-getairportnetwork", "en0"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                match = re.search(r"Current Wi-Fi Network: (.+)", result.stdout)
                if match:
                    return match.group(1).strip()
        except Exception:
            pass

        try:
            result = subprocess.run(
                ["/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport", "-I"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                match = re.search(r" SSID: (.+)", result.stdout)
                if match:
                    return match.group(1).strip()
        except Exception:
            pass

        return None

    def _get_vpn_state(self) -> tuple[str, Optional[str]]:
        """Get current VPN connection state and server name.

        Uses multiple detection methods since ProtonVPN uses NetworkExtension
        (NEPacketTunnelProvider) which creates utun interfaces but may not
        appear in scutil --nc list.
        """
        # Method 1: Check scutil for VPN connections
        try:
            result = subprocess.run(
                ["scutil", "--nc", "list"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    if "Connected" in line:
                        parts = line.split('"')
                        if len(parts) >= 2:
                            service = parts[1]
                            if any(k in service.lower() for k in ["proton", "vpn"]):
                                return "connected", service
        except Exception:
            pass

        # Method 2: Check ifconfig for tunnel interfaces with non-local IPs
        # ProtonVPN WireGuard creates utun interfaces with real IPs
        try:
            result = subprocess.run(
                ["ifconfig"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                # Look for utun interfaces with non-local, non-link-local IPs
                for match in re.finditer(
                    r"(utun\d+):.*?inet (\d+\.\d+\.\d+\.\d+)",
                    result.stdout, re.DOTALL
                ):
                    iface, ip = match.groups()
                    if not ip.startswith("127.") and not ip.startswith("169.254.") and not ip.startswith("192.168.") and not ip.startswith("10.") and not ip.startswith("172.1"):
                        return "connected", f"{self.provider}-{iface}"
        except Exception:
            pass

        # Method 3: Check if ProtonVPN process is running and has established tunnels
        try:
            result = subprocess.run(
                ["pgrep", "-f", "ProtonVPN"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                # ProtonVPN is running — check for active tunnel
                netstat_result = subprocess.run(
                    ["netstat", "-rn", "-f", "inet"],
                    capture_output=True, text=True, timeout=5
                )
                if netstat_result.returncode == 0:
                    # Look for default route through utun (VPN tunnel)
                    for line in netstat_result.stdout.splitlines():
                        if line.startswith("default") and "utun" in line:
                            return "connected", f"{self.provider}-tunnel"
        except Exception:
            pass

        return "disconnected", None

    def _is_public_wifi(self, ssid: Optional[str]) -> bool:
        """Detect if current Wi-Fi is likely public."""
        if not ssid:
            return False
        public_patterns = [
            "guest", "public", "free", "wifi", "hotspot",
            "starbucks", "mcdonalds", "costa", "kfc", "burgerking",
            "airport", "hotel", "motel", "hilton", "marriott",
            "train", "station", "bus", "terminal",
            "library", "cafe", "coffee", "restaurant",
            "shopping", "mall", "store"
        ]
        ssid_lower = ssid.lower()
        return any(pattern in ssid_lower for pattern in public_patterns)

    def _log_state_change(self, state: str, server: Optional[str] = None, wifi: Optional[str] = None):
        """Log VPN state change to telemetry/network."""
        server_str = f" {server}" if server else ""
        wifi_str = f" wifi={wifi}" if wifi else ""
        log_file = daily_log_path(self._log_dir, "bt7274_network")
        append_log(log_file, f"[vpn] {state}{server_str}{wifi_str}")

    def _announce(self, message: str):
        """Announce a message via TTS callback or UI."""
        if self._tts_callback:
            try:
                self._tts_callback(message)
            except Exception as e:
                error(f"VPN TTS callback failed: {e}")
        status("VPN", message)

    def _on_state_change(self, new_state: str, old_state: Optional[str], server: Optional[str] = None, wifi: Optional[str] = None):
        """Handle VPN state change."""
        self._log_state_change(new_state, server, wifi)

        if new_state == "connected" and old_state != "connected":
            self._announce("Cloak engaged. Network traffic obfuscated.")
            self._public_wifi_warned = False
        elif new_state == "disconnected" and old_state == "connected":
            self._announce("Cloak offline. We are exposed, Pilot.")
            self._public_wifi_warned = False

    def check(self) -> Optional[dict]:
        """Perform a single VPN check and handle state changes."""
        if not self.enabled:
            return None

        state, server = self._get_vpn_state()
        wifi = self._get_wifi_ssid()

        # Handle state changes
        if state != self._last_state:
            self._on_state_change(state, self._last_state, server, wifi)
            self._last_state = state
            self._last_server = server
            self._last_wifi = wifi

        # Auto-cloak logic: warn if on public Wi-Fi without VPN
        if self.auto_cloak and state == "disconnected" and self._is_public_wifi(wifi):
            if not self._public_wifi_warned:
                self._announce(f"Warning: Public network detected ({wifi}). Recommend engaging cloak, Pilot.")
                self._public_wifi_warned = True
        elif state == "connected" or not self._is_public_wifi(wifi):
            self._public_wifi_warned = False

        return {
            "state": state,
            "server": server,
            "wifi": wifi,
        }

    def _monitor_loop(self):
        """Background monitoring loop."""
        while self._running:
            self.check()
            time.sleep(self.interval)

    def start(self):
        """Start background VPN monitoring."""
        if not self.enabled:
            info("VPN monitoring disabled.")
            return
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        status("VPN", "Monitoring active")

    def stop(self):
        """Stop background VPN monitoring."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None

    def get_status(self) -> dict:
        """Return current VPN monitor status."""
        return {
            "enabled": self.enabled,
            "running": self._running,
            "state": self._last_state,
            "server": self._last_server,
            "wifi": self._last_wifi,
            "auto_cloak": self.auto_cloak,
        }

    def _get_vpn_service_name(self) -> Optional[str]:
        """Get the VPN service name for macOS VPN control.

        Tries multiple methods since ProtonVPN uses NetworkExtension
        (NEPacketTunnelProvider) which may not appear in scutil --nc list.
        """
        # Method 1: Check scutil for VPN connections
        try:
            result = subprocess.run(
                ["scutil", "--nc", "list"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    if any(k in line.lower() for k in ["proton", "vpn"]):
                        match = re.search(r'"([^"]+)"', line)
                        if match:
                            return match.group(1)
        except Exception:
            pass

        # Method 2: Check networksetup for VPN services
        try:
            result = subprocess.run(
                ["networksetup", "-listallnetworkservices"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    line = line.strip()
                    if any(k in line.lower() for k in ["proton", "vpn"]):
                        return line
        except Exception:
            pass

        # Method 3: Check if ProtonVPN app exists at all
        try:
            result = subprocess.run(
                ["mdfind", "kMDItemKind == 'Application' && kMDItemFSName == 'ProtonVPN.app'"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                # App exists but no service found in system configs.
                # ProtonVPN uses its own NetworkExtension — we'll use
                # AppleScript UI automation instead.
                return "__protonvpn_app__"
        except Exception:
            pass

        return None

    def connect(self) -> bool:
        """Attempt to connect the VPN (engage cloak) — delegates to connect_and_wait."""
        return self.connect_and_wait(timeout=30)

    def connect_and_wait(self, timeout: int = 30) -> bool:
        """Connect VPN and wait until confirmed connected (or timeout).

        CRITICAL: ProtonVPN's WireGuard NEExtension handshake requires the app
        to stay frontmost for 15-20 seconds. If backgrounded, the tunnel exists
        but no real traffic flows — only ~20 KB/s of keepalive packets.
        We keep the app frontmost AND verify real connectivity before returning.
        """
        # Check if already connected WITH real connectivity
        if self._verify_connectivity():
            self._announce("Cloak is already engaged, Pilot.")
            return True

        state, _ = self._get_vpn_state()
        if state == "connected":
            # Tunnel exists but no real traffic — disconnect first, then reconnect
            warning("Cloak tunnel exists but no traffic flowing. Resetting...")
            self.disconnect()
            time.sleep(3)

        service_name = self._get_vpn_service_name()

        # ── Method 1: AppleScript UI automation (primary) ──────────────
        status("VPN", "Cloak engaging. Establishing secure tunnel...")
        try:
            script = '''
tell application "ProtonVPN" to activate
delay 3

-- Wait for window to exist (up to 5s)
set winReady to false
repeat 10 times
    try
        tell application "System Events"
            tell process "ProtonVPN"
                if (count of windows) > 0 then
                    set winReady to true
                    exit repeat
                end if
            end tell
        end tell
    end try
    delay 0.5
end repeat

if not winReady then
    return "NO_WINDOW"
end if

-- Find and click the connect button (handles multiple naming variants)
tell application "System Events"
    tell process "ProtonVPN"
        set btnClicked to false
        repeat with btnName in {"Quick Connect", "Connect", "Quick Connect ", "Connect "}
            try
                if exists button btnName of window 1 then
                    click button btnName of window 1
                    set btnClicked to true
                    exit repeat
                end if
            end try
        end repeat
        if not btnClicked then
            try
                click button 1 of window 1
                set btnClicked to true
            end try
        end if
        if not btnClicked then
            return "NO_BUTTON"
        end if
    end tell
end tell

-- Wait for connection (button changes to "Disconnect")
repeat 30 times
    delay 1
    try
        tell application "System Events"
            tell process "ProtonVPN"
                try
                    if exists button "Disconnect" of window 1 then
                        -- CRITICAL: Keep frontmost for full handshake (20s)
                        -- The NEExtension needs the app in foreground to complete
                        -- the WireGuard cryptographic handshake. If backgrounded,
                        -- only keepalive packets flow (~20 KB/s).
                        delay 20
                        return "CONNECTED"
                    end if
                end try
            end tell
        end tell
    end try
end repeat
return "TIMEOUT"
'''
            result = subprocess.run(
                ["osascript", "-"],
                input=script,
                capture_output=True,
                text=True,
                timeout=75,  # 3s activate + 5s window + 30s button wait + 20s handshake + buffer
            )
            apple_result = result.stdout.strip()
            status("VPN", f"AppleScript result: {apple_result}")

            if apple_result == "CONNECTED":
                # Verify REAL connectivity (not just tunnel existence)
                if self._verify_connectivity(retries=10):
                    self._last_state = "connected"
                    self._announce("Cloak engaged. Network traffic obfuscated.")
                    return True
                else:
                    warning("Cloak tunnel established but no traffic flowing. Handshake may be incomplete.")
                    # Give it more time with app still frontmost
                    time.sleep(10)
                    if self._verify_connectivity(retries=5):
                        self._last_state = "connected"
                        self._announce("Cloak engaged. Network traffic obfuscated.")
                        return True

            if apple_result == "TIMEOUT":
                warning("Cloak handshake timed out. Checking connectivity anyway...")
                if self._verify_connectivity(retries=10):
                    self._last_state = "connected"
                    self._announce("Cloak engaged. Network traffic obfuscated.")
                    return True

            if apple_result in ("NO_WINDOW", "NO_BUTTON"):
                warning(f"Could not interact with ProtonVPN window ({apple_result}).")

        except subprocess.TimeoutExpired:
            warning("AppleScript timed out. Checking connectivity anyway...")
            if self._verify_connectivity(retries=5):
                self._last_state = "connected"
                self._announce("Cloak engaged. Network traffic obfuscated.")
                return True
        except Exception as e:
            warning(f"AppleScript error: {e}")

        # ── Method 2: URL scheme ───────────────────────────────────────
        status("VPN", "Trying URL scheme...")
        try:
            subprocess.run(
                ["open", "protonvpn://connect"],
                capture_output=True, text=True, timeout=10
            )
            # Keep ProtonVPN frontmost for handshake
            time.sleep(5)
            subprocess.run(["open", "-a", "ProtonVPN"], capture_output=True, timeout=5)
            time.sleep(20)  # Full handshake wait
            if self._verify_connectivity(retries=10):
                self._last_state = "connected"
                self._announce("Cloak engaged. Network traffic obfuscated.")
                return True
        except Exception:
            pass

        # ── Method 3: scutil (for traditional VPN services) ────────────
        if service_name and service_name != "__protonvpn_app__":
            status("VPN", "Trying scutil...")
            try:
                subprocess.run(
                    ["scutil", "--nc", "start", service_name],
                    capture_output=True, text=True, timeout=30
                )
                for _ in range(timeout):
                    if self._verify_connectivity(retries=1):
                        self._last_state = "connected"
                        self._announce("Cloak engaged. Network traffic obfuscated.")
                        return True
                    time.sleep(1)
            except Exception:
                pass

        # ── Method 4: Manual activation ────────────────────────────────
        warning("Cloak requires manual activation. Opening ProtonVPN app...")
        try:
            subprocess.run(
                ["open", "-a", "ProtonVPN"],
                capture_output=True, text=True, timeout=10
            )
            self._announce(
                "Cloak requires manual activation, Pilot. "
                "Please click the Connect button in the ProtonVPN app."
            )
        except Exception as e:
            warning(f"Could not open ProtonVPN app: {e}")

        return False

    def _verify_connectivity(self, retries: int = 5) -> bool:
        """Verify real internet connectivity through the VPN tunnel.

        Checks multiple targets to confirm traffic is actually flowing,
        not just that a tunnel interface exists with keepalive packets.

        Returns:
            True if we can reach the internet through the tunnel.
        """
        # First: check that a tunnel actually exists
        state, _ = self._get_vpn_state()
        if state != "connected":
            return False

        # Second: try to reach external hosts (not just ping — fetch data)
        import urllib.request
        import urllib.error

        targets = [
            ("https://www.google.com", 3.0),       # Fast, reliable
            ("https://api.ipify.org", 3.0),         # Returns our public IP
            ("https://1.1.1.1", 3.0),               # Cloudflare DNS
        ]

        for attempt in range(retries):
            for url, req_timeout in targets:
                try:
                    req = urllib.request.Request(url, method='HEAD')
                    req.add_header('User-Agent', 'BT-7274-Cloak-Check/1.0')
                    resp = urllib.request.urlopen(req, timeout=req_timeout)
                    if resp.status in (200, 301, 302, 403):
                        # 403 from 1.1.1.1 is fine — it means we reached it
                        return True
                except urllib.error.HTTPError as e:
                    # HTTP errors still mean we reached the server
                    if e.code in (403, 404):
                        return True
                except Exception:
                    continue
            if attempt < retries - 1:
                time.sleep(1)

        return False

    def disconnect(self) -> bool:
        """Attempt to disconnect the VPN (disengage cloak).

        Uses AppleScript UI automation to click the "Disconnect" button
        in the ProtonVPN app. Falls back to networksetup/scutil.
        """
        # Check if actually connected
        state, _ = self._get_vpn_state()
        if state != "connected":
            self._announce("Cloak is already disengaged, Pilot.")
            return True

        service_name = self._get_vpn_service_name()

        # ── Method 1: AppleScript UI automation ────────────────────────
        status("VPN", "Disengaging cloak...")
        try:
            script = '''
tell application "ProtonVPN" to activate
delay 2

tell application "System Events"
    tell process "ProtonVPN"
        -- Try to find and click the Disconnect button
        set btnClicked to false
        repeat with btnName in {"Disconnect", "Disconnect "}
            try
                if exists button btnName of window 1 then
                    click button btnName of window 1
                    set btnClicked to true
                    exit repeat
                end if
            end try
        end repeat
        if not btnClicked then
            -- Last resort: try button 1 (usually Disconnect when connected)
            try
                click button 1 of window 1
                set btnClicked to true
            end try
        end if
        if not btnClicked then
            return "NO_BUTTON"
        end if
    end tell
end tell

-- Wait for disconnect
repeat 15 times
    delay 1
    try
        tell application "System Events"
            tell process "ProtonVPN"
                try
                    if exists button "Quick Connect" of window 1 then
                        return "DISCONNECTED"
                    end if
                    if exists button "Connect" of window 1 then
                        return "DISCONNECTED"
                    end if
                end try
            end tell
        end tell
    end try
end repeat
return "TIMEOUT"
'''
            result = subprocess.run(
                ["osascript", "-"],
                input=script,
                capture_output=True,
                text=True,
                timeout=30,
            )
            apple_result = result.stdout.strip()
            status("VPN", f"Disconnect AppleScript: {apple_result}")

            if apple_result in ("DISCONNECTED", "TIMEOUT"):
                # Verify via system checks
                for _ in range(10):
                    state, _ = self._get_vpn_state()
                    if state == "disconnected":
                        self._last_state = "disconnected"
                        self._last_server = None
                        self._announce("Cloak offline. We are exposed, Pilot.")
                        return True
                    time.sleep(0.5)
                # If AppleScript said disconnected but system checks disagree
                if apple_result == "DISCONNECTED":
                    self._last_state = "disconnected"
                    self._last_server = None
                    self._announce("Cloak offline. We are exposed, Pilot.")
                    return True

        except Exception as e:
            warning(f"AppleScript disconnect error: {e}")

        # ── Method 2: scutil ───────────────────────────────────────────
        if service_name and service_name != "__protonvpn_app__":
            try:
                subprocess.run(
                    ["scutil", "--nc", "stop", service_name],
                    capture_output=True, text=True, timeout=15
                )
                for _ in range(10):
                    state, _ = self._get_vpn_state()
                    if state == "disconnected":
                        self._last_state = "disconnected"
                        self._last_server = None
                        self._announce("Cloak offline. We are exposed, Pilot.")
                        return True
                    time.sleep(0.5)
            except Exception:
                pass

        # ── Method 3: networksetup ──────────────────────────────────────
        if service_name and service_name != "__protonvpn_app__":
            try:
                subprocess.run(
                    ["networksetup", "-disconnectpppoeservice", service_name],
                    capture_output=True, text=True, timeout=15
                )
                for _ in range(10):
                    state, _ = self._get_vpn_state()
                    if state == "disconnected":
                        self._last_state = "disconnected"
                        self._last_server = None
                        self._announce("Cloak offline. We are exposed, Pilot.")
                        return True
                    time.sleep(0.5)
            except Exception:
                pass

        warning("Unable to disengage cloak automatically. Please disconnect manually in the ProtonVPN app.")
        return False

    def show_status(self) -> str:
        """Return a detailed human-readable VPN status."""
        state, server = self._get_vpn_state()
        service_name = self._get_vpn_service_name()
        wifi = self._get_wifi_ssid()

        lines = ["BT-7274 Cloak Diagnostics", "─" * 30]
        lines.append(f"Status: {'ENGAGED' if state == 'connected' else 'OFFLINE'}")
        if server:
            lines.append(f"Server: {server}")
        if wifi:
            lines.append(f"Network: {wifi}")
            if self._is_public_wifi(wifi):
                lines.append("⚠ Public network detected")
        lines.append(f"Auto-cloak: {'Enabled' if self.auto_cloak else 'Disabled'}")

        if service_name and service_name != "__protonvpn_app__":
            lines.append(f"Service: {service_name}")
            try:
                result = subprocess.run(
                    ["scutil", "--nc", "status", service_name],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    lines.append(f"Details: {result.stdout.strip()}")
            except Exception:
                pass

        return "\n".join(lines)
