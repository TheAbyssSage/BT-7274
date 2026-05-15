"""
Battery monitoring for BT-7274.
Warns at 50%, 20%, 10%, 5% battery levels.
Only logs critical levels (<= 10%) to telemetry/system.
"""

import os
import re
import time
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable

from bt7274.bt7274_assistant.ui import info, success, warning, error, status
from bt7274.bt7274_workstation.log_manager import get_telemetry_system_dir, append_log, daily_log_path


class BatteryMonitor:
    """Monitors macOS battery level and warns at configured thresholds."""

    # Default warning thresholds in descending order
    DEFAULT_THRESHOLDS = [50, 20, 10, 5]

    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}
        self.enabled = self.config.get("enabled", True)
        self.interval = self.config.get("interval", 60)  # seconds between checks
        self.thresholds = sorted(
            self.config.get("thresholds", self.DEFAULT_THRESHOLDS),
            reverse=True
        )
        self._warned_levels: set[int] = set()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_level: Optional[int] = None
        self._last_warning_time: float = 0.0
        self._rewarn_interval: int = 300  # Re-warn every 5 minutes when below 20%
        self._log_dir = get_telemetry_system_dir()
        self._log_dir.mkdir(parents=True, exist_ok=True)

    def _get_battery_level(self) -> Optional[int]:
        """Get current battery percentage on macOS."""
        try:
            result = os.popen("pmset -g batt").read()
            # Parse output like: "Now drawing from 'Battery Power'\n -InternalBattery-0\t95%; discharging; 4:12 remaining"
            match = re.search(r"(\d+)%", result)
            if match:
                return int(match.group(1))
        except Exception as e:
            error(f"Battery check failed: {e}")
        return None

    def get_level(self) -> Optional[int]:
        """Public alias for _get_battery_level."""
        return self._get_battery_level()

    def _log_critical(self, level: int):
        """Log critical battery level to telemetry/system."""
        log_file = daily_log_path(self._log_dir, "bt7274_system")
        append_log(log_file, f"[battery] level={level}%")

    def _warn(self, level: int):
        """Issue a battery warning."""
        if level <= 5:
            warning(f"CRITICAL BATTERY: {level}% — Connect power immediately, Pilot.")
        elif level <= 10:
            warning(f"LOW BATTERY: {level}% — Recommend connecting power, Pilot.")
        elif level <= 20:
            warning(f"BATTERY AT {level}% — Consider connecting power, Pilot.")
        else:
            info(f"BATTERY AT {level}% — Monitor power levels, Pilot.")

    def check(self) -> Optional[int]:
        """Perform a single battery check and warn if needed."""
        if not self.enabled:
            return None

        level = self._get_battery_level()
        if level is None:
            return None

        self._last_level = level

        # Determine if we should warn
        for threshold in self.thresholds:
            if level <= threshold and threshold not in self._warned_levels:
                self._warned_levels.add(threshold)
                self._warn(level)
                self._last_warning_time = time.time()
                # Log only critical levels (<= 10%)
                if level <= 10:
                    self._log_critical(level)
                break

        # Re-warn periodically when battery stays below 20%
        if level <= 20 and time.time() - self._last_warning_time > self._rewarn_interval:
            self._warn(level)
            self._last_warning_time = time.time()
            if level <= 10:
                self._log_critical(level)

        # Reset warnings if battery recovers above a threshold + buffer
        # (e.g., if it was at 9% and now is at 12%, reset 10% warning)
        to_reset = [t for t in self._warned_levels if level > t + 2]
        for t in to_reset:
            self._warned_levels.discard(t)

        return level

    def _monitor_loop(self):
        """Background monitoring loop."""
        while self._running:
            self.check()
            time.sleep(self.interval)

    def start(self):
        """Start background battery monitoring."""
        if not self.enabled:
            info("Battery monitoring disabled.")
            return
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        status("BATTERY", "Monitoring active")

    def stop(self):
        """Stop background battery monitoring."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None

    def get_status(self) -> dict:
        """Return current battery status."""
        level = self._get_battery_level()
        return {
            "enabled": self.enabled,
            "level": level,
            "last_level": self._last_level,
            "warned_levels": sorted(self._warned_levels),
            "thresholds": self.thresholds,
        }
