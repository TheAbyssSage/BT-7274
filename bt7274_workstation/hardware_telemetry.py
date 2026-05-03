"""
Hardware Telemetry for BT-7274.

Logs periodic snapshots of system hardware state:
- CPU usage & temperature (if available)
- RAM usage
- Disk usage
- Thermal pressure (macOS)
- Uptime

Stores JSONL entries under logs/telemetry/hardware/.
"""

import os
import platform
import subprocess
import time
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from bt7274_workstation.log_manager import get_telemetry_hardware_dir, daily_jsonl_path, append_jsonl
from bt7274_assistant.ui import info, warning, error, status


class HardwareTelemetry:
    """Monitors and logs system hardware metrics."""

    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}
        self.enabled = self.config.get("enabled", True)
        self.interval = self.config.get("interval", 60)  # seconds
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._log_dir = get_telemetry_hardware_dir()
        self._log_dir.mkdir(parents=True, exist_ok=True)

    def _get_cpu_usage(self) -> Optional[float]:
        """Get current CPU usage percentage."""
        try:
            import psutil
            return psutil.cpu_percent(interval=0.5)
        except ImportError:
            pass
        try:
            result = subprocess.run(
                ["top", "-l", "1", "-n", "0"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    if "CPU usage" in line:
                        parts = line.split()
                        for p in parts:
                            if "%" in p:
                                try:
                                    return float(p.replace("%", ""))
                                except ValueError:
                                    continue
        except Exception:
            pass
        return None

    def _get_ram_usage(self) -> Optional[dict]:
        """Get RAM usage stats in MB."""
        try:
            import psutil
            mem = psutil.virtual_memory()
            return {
                "total_mb": round(mem.total / (1024 * 1024), 1),
                "used_mb": round(mem.used / (1024 * 1024), 1),
                "percent": mem.percent,
            }
        except ImportError:
            pass
        try:
            result = subprocess.run(
                ["vm_stat"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                # Parse vm_stat output on macOS
                stats = {}
                for line in result.stdout.splitlines():
                    if ":" in line:
                        key, val = line.split(":", 1)
                        val = val.strip().replace(".", "")
                        try:
                            stats[key.strip()] = int(val)
                        except ValueError:
                            continue
                page_size = 4096  # macOS default page size
                free_pages = stats.get("Pages free", 0)
                active_pages = stats.get("Pages active", 0)
                inactive_pages = stats.get("Pages inactive", 0)
                wired_pages = stats.get("Pages wired down", 0)
                used_pages = active_pages + inactive_pages + wired_pages
                total_pages = used_pages + free_pages
                if total_pages > 0:
                    return {
                        "total_mb": round(total_pages * page_size / (1024 * 1024), 1),
                        "used_mb": round(used_pages * page_size / (1024 * 1024), 1),
                        "percent": round(used_pages / total_pages * 100, 1),
                    }
        except Exception:
            pass
        return None

    def _get_disk_usage(self) -> Optional[dict]:
        """Get disk usage for the project root."""
        try:
            import psutil
            root = Path(__file__).parent.parent.parent.resolve()
            usage = psutil.disk_usage(str(root))
            return {
                "total_gb": round(usage.total / (1024**3), 2),
                "used_gb": round(usage.used / (1024**3), 2),
                "free_gb": round(usage.free / (1024**3), 2),
                "percent": usage.percent,
            }
        except ImportError:
            pass
        try:
            result = subprocess.run(
                ["df", "-h", "."],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                lines = result.stdout.strip().splitlines()
                if len(lines) >= 2:
                    parts = lines[-1].split()
                    if len(parts) >= 5:
                        return {
                            "total": parts[1],
                            "used": parts[2],
                            "free": parts[3],
                            "percent": parts[4],
                        }
        except Exception:
            pass
        return None

    def _get_thermal_state(self) -> Optional[str]:
        """Get macOS thermal state if available."""
        try:
            result = subprocess.run(
                ["pmset", "-g", "therm"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    if "Thermal level" in line:
                        return line.split(":")[-1].strip()
        except Exception:
            pass
        return None

    def _get_uptime_seconds(self) -> Optional[float]:
        """Get system uptime in seconds."""
        try:
            result = subprocess.run(
                ["sysctl", "-n", "kern.boottime"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                import re
                match = re.search(r"sec\s*=\s*(\d+)", result.stdout)
                if match:
                    boot_time = int(match.group(1))
                    return time.time() - boot_time
        except Exception:
            pass
        return None

    def snapshot(self) -> dict:
        """Capture a single hardware snapshot and return it."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "platform": platform.platform(),
            "cpu_percent": self._get_cpu_usage(),
            "ram": self._get_ram_usage(),
            "disk": self._get_disk_usage(),
            "thermal_state": self._get_thermal_state(),
            "uptime_seconds": self._get_uptime_seconds(),
        }
        return entry

    def log_snapshot(self):
        """Capture and write a hardware snapshot to JSONL."""
        entry = self.snapshot()
        log_file = daily_jsonl_path(self._log_dir, "hardware_telemetry")
        append_jsonl(log_file, entry)

    def _monitor_loop(self):
        """Background monitoring loop."""
        while self._running:
            try:
                self.log_snapshot()
            except Exception as e:
                error(f"Hardware telemetry failed: {e}")
            time.sleep(self.interval)

    def start(self):
        """Start background hardware monitoring."""
        if not self.enabled:
            info("Hardware telemetry disabled.")
            return
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        status("HW", "Hardware telemetry active")

    def stop(self):
        """Stop background hardware monitoring."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None

    def get_status(self) -> dict:
        """Return current hardware telemetry status."""
        return {
            "enabled": self.enabled,
            "running": self._running,
            "last_snapshot": self.snapshot(),
        }
