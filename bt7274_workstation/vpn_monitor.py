"""
VPN monitoring for BT-7274.
Detects Proton VPN connect/disconnect events.
Speaks voice lines on state changes.
Logs all state changes to logs/system_logs.
"""

import re
import time
import threading
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable

from bt7274_assistant.ui import info, success, warning, error, status


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
        self._log_dir = Path(__file__).parent.parent / "logs" / "system_logs"
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

    def _get_vpn_state(self) -> tuple[Optional[str], Optional[str]]:
        """Get current VPN connection state and server name."""
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
        try:
            result = subprocess.run(
                ["ifconfig"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                for match in re.finditer(r"(utun\d+):.*?inet (\d+\.\d+\.\d+\.\d+)", result.stdout, re.DOTALL):
                    iface, ip = match.groups()
                    if not ip.startswith("127.") and not ip.startswith("169.254."):
                        return "connected", f"{self.provider}-{iface}"
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
        """Log VPN state change to logs/system_logs."""
        timestamp = datetime.now().strftime("%Y-%m-%dT%H:%MZ")
        server_str = f" {server}" if server else ""
        wifi_str = f" wifi={wifi}" if wifi else ""
        log_line = f"{timestamp} [vpn] {state}{server_str}{wifi_str}\n"
        today = datetime.now().strftime("%Y-%m-%d")
        log_file = self._log_dir / f"bt7274_system_{today}.log"
        try:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(log_line)
        except Exception as e:
            error(f"Failed to write VPN log: {e}")

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

    def connect(self) -> bool:
        """Attempt to connect the VPN (engage cloak)."""
        try:
            if self.provider == "protonvpn":
                result = subprocess.run(
                    ["protonvpn-cli", "connect", "--fastest"],
                    capture_output=True, text=True, timeout=30
                )
                if result.returncode == 0:
                    self._announce("Cloak engaged. Network traffic obfuscated.")
                    return True
                else:
                    error(f"ProtonVPN connect failed: {result.stderr}")
                    return False
            else:
                warning(f"VPN connect not implemented for provider: {self.provider}")
                return False
        except FileNotFoundError:
            error("protonvpn-cli not found. Cannot engage cloak.")
            return False
        except Exception as e:
            error(f"VPN connect failed: {e}")
            return False

    def disconnect(self) -> bool:
        """Attempt to disconnect the VPN (disengage cloak)."""
        try:
            if self.provider == "protonvpn":
                result = subprocess.run(
                    ["protonvpn-cli", "disconnect"],
                    capture_output=True, text=True, timeout=30
                )
                if result.returncode == 0:
                    self._announce("Cloak offline. We are exposed, Pilot.")
                    return True
                else:
                    error(f"ProtonVPN disconnect failed: {result.stderr}")
                    return False
            else:
                warning(f"VPN disconnect not implemented for provider: {self.provider}")
                return False
        except FileNotFoundError:
            error("protonvpn-cli not found. Cannot disengage cloak.")
            return False
        except Exception as e:
            error(f"VPN disconnect failed: {e}")
            return False
