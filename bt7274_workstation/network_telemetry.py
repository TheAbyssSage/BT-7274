"""
Network Telemetry for BT-7274.

Logs periodic snapshots of network state:
- Wi-Fi SSID, BSSID, signal strength
- VPN connection status
- Public IP / geolocation hints
- Latency to a reliable target (e.g., 1.1.1.1)
- Detect public Wi-Fi and warn

Stores JSONL entries under logs/telemetry/network/.
"""

import re
import subprocess
import time
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional, Any

from bt7274_workstation.log_manager import get_telemetry_network_dir, daily_jsonl_path, append_jsonl
from bt7274_assistant.ui import info, warning, error, status


class NetworkTelemetry:
    """Monitors and logs network connectivity metrics."""

    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}
        self.enabled = self.config.get("enabled", True)
        self.interval = self.config.get("interval", 30)  # seconds
        self.latency_target = self.config.get("latency_target", "1.1.1.1")
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._log_dir = get_telemetry_network_dir()
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._last_wifi: Optional[str] = None
        self._last_vpn: Optional[str] = None

    def _get_wifi_info(self) -> Optional[dict]:
        """Get current Wi-Fi SSID, BSSID, and signal info on macOS."""
        info_dict: dict[str, Any] = {}
        try:
            result = subprocess.run(
                ["networksetup", "-getairportnetwork", "en0"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                match = re.search(r"Current Wi-Fi Network:\s*(.+)", result.stdout)
                if match:
                    info_dict["ssid"] = match.group(1).strip()
        except Exception:
            pass

        # Fallback: system_profiler (works without sudo, slower but reliable)
        if not info_dict:
            try:
                result = subprocess.run(
                    ["system_profiler", "SPAirPortDataType", "-json"],
                    capture_output=True, text=True, timeout=10
                )
                if result.returncode == 0:
                    import json
                    data = json.loads(result.stdout)
                    for item in data.get("SPAirPortDataType", []):
                        interfaces = item.get("spairport_airport_interfaces", [])
                        for iface in interfaces:
                            current = iface.get("spairport_current_network_information", {})
                            if current:
                                info_dict["ssid"] = current.get("_name", "")
                                signal_noise = current.get("spairport_signal_noise", "")
                                if signal_noise:
                                    parts = signal_noise.split(" / ")
                                    if parts:
                                        try:
                                            info_dict["rssi_dbm"] = int(parts[0].replace(" dBm", "").strip())
                                        except ValueError:
                                            pass
                                rate = current.get("spairport_network_rate", 0)
                                if rate:
                                    try:
                                        info_dict["tx_rate_mbps"] = int(rate)
                                    except ValueError:
                                        pass
                                break
            except Exception:
                pass

        return info_dict if info_dict else None

    def _get_vpn_status(self) -> Optional[dict]:
        """Check if any VPN tunnel is active."""
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
                            return {"state": "connected", "service": parts[1]}
        except Exception:
            pass

        try:
            result = subprocess.run(
                ["ifconfig"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                for match in re.finditer(r"(utun\d+):.*?inet (\d+\.\d+\.\d+\.\d+)", result.stdout, re.DOTALL):
                    iface, ip = match.groups()
                    if not ip.startswith("127.") and not ip.startswith("169.254."):
                        return {"state": "connected", "interface": iface, "ip": ip}
        except Exception:
            pass

        return {"state": "disconnected"}

    def _get_latency(self) -> Optional[float]:
        """Measure round-trip latency to configured target."""
        try:
            result = subprocess.run(
                ["ping", "-c", "1", "-W", "2", self.latency_target],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                match = re.search(r"time=([\d.]+)\s*ms", result.stdout)
                if match:
                    return float(match.group(1))
        except Exception:
            pass
        return None

    def _is_public_wifi(self, ssid: Optional[str]) -> bool:
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

    def snapshot(self) -> dict:
        """Capture a single network snapshot."""
        wifi = self._get_wifi_info()
        vpn = self._get_vpn_status()
        latency = self._get_latency()

        entry = {
            "timestamp": datetime.now().isoformat(),
            "wifi": wifi,
            "vpn": vpn,
            "latency_ms": latency,
            "public_wifi_detected": self._is_public_wifi(wifi.get("ssid") if wifi else None),
        }

        # Track changes for optional warnings
        current_wifi = wifi.get("ssid") if wifi else None
        current_vpn = vpn.get("state") if vpn else None

        if self._last_wifi and self._last_wifi != current_wifi:
            entry["event"] = "wifi_changed"
            entry["previous_wifi"] = self._last_wifi
        if self._last_vpn and self._last_vpn != current_vpn:
            entry["event"] = "vpn_changed"
            entry["previous_vpn"] = self._last_vpn

        self._last_wifi = current_wifi
        self._last_vpn = current_vpn
        return entry

    def log_snapshot(self):
        """Capture and write a network snapshot to JSONL."""
        entry = self.snapshot()
        log_file = daily_jsonl_path(self._log_dir, "network_telemetry")
        append_jsonl(log_file, entry)

        # Warn if on public Wi-Fi without VPN
        if entry.get("public_wifi_detected") and (entry.get("vpn") or {}).get("state") != "connected":
            warning(f"Public network detected ({entry['wifi'].get('ssid')}). Recommend engaging cloak, Pilot.")

    def _monitor_loop(self):
        """Background monitoring loop."""
        while self._running:
            try:
                self.log_snapshot()
            except Exception as e:
                error(f"Network telemetry failed: {e}")
            time.sleep(self.interval)

    def start(self):
        """Start background network monitoring."""
        if not self.enabled:
            info("Network telemetry disabled.")
            return
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        status("NET", "Network telemetry active")

    def stop(self):
        """Stop background network monitoring."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None

    def get_status(self) -> dict:
        """Return current network telemetry status."""
        return {
            "enabled": self.enabled,
            "running": self._running,
            "last_snapshot": self.snapshot(),
        }
