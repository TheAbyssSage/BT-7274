"""
Environmental / Weather warnings for BT-7274.
Warns about rain, heavy rain, hail, thunderstorms, and extreme temperatures.
Logs warnings per-day to telemetry/health.
Logs state changes to telemetry/system.
"""

import time
import threading
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests

from bt7274.bt7274_assistant.ui import info, success, warning, error, status
from bt7274.bt7274_workstation.log_manager import get_telemetry_system_dir, get_telemetry_health_dir, append_log, append_jsonl, daily_log_path, daily_jsonl_path


# WMO weather codes that trigger warnings
WEATHER_ALERT_CODES = {
    # Rain
    61: ("rain", "low"),
    63: ("rain", "medium"),
    65: ("heavy_rain", "high"),
    80: ("rain", "low"),
    81: ("rain", "medium"),
    82: ("heavy_rain", "high"),
    # Thunderstorms
    95: ("thunderstorm", "high"),
    96: ("thunderstorm_with_hail", "critical"),
    99: ("thunderstorm_with_heavy_hail", "critical"),
    # Hail / snow variants that include hail
    96: ("thunderstorm_with_hail", "critical"),
    99: ("thunderstorm_with_heavy_hail", "critical"),
}

# Temperature thresholds (Celsius)
TEMP_THRESHOLDS = {
    "extreme_heat": 35,
    "extreme_cold": -10,
}


class WeatherMonitor:
    """Monitors weather conditions and warns about environmental hazards."""

    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}
        self.enabled = self.config.get("enabled", True)
        self.interval = self.config.get("interval", 300)  # seconds (5 min default)
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._warned_codes: set[int] = set()
        self._warned_temps: set[str] = set()
        self._last_weather: Optional[dict] = None

        # Log directories
        self._system_log_dir = get_telemetry_system_dir()
        self._health_log_dir = get_telemetry_health_dir()
        self._system_log_dir.mkdir(parents=True, exist_ok=True)
        self._health_log_dir.mkdir(parents=True, exist_ok=True)

    def _fetch_weather(self, lat: float, lon: float) -> Optional[dict]:
        """Fetch current weather from Open-Meteo."""
        try:
            url = (
                f"https://api.open-meteo.com/v1/forecast?"
                f"latitude={lat}&longitude={lon}&current_weather=true"
            )
            resp = requests.get(url, timeout=10)
            data = resp.json()
            current = data.get("current_weather", {})
            if current:
                return {
                    "temperature": current.get("temperature"),
                    "windspeed": current.get("windspeed"),
                    "weathercode": current.get("weathercode"),
                    "timestamp": datetime.now().isoformat(),
                }
        except Exception as e:
            error(f"Weather fetch failed: {e}")
        return None

    def _get_location(self) -> Optional[tuple[float, float]]:
        """Get current lat/lon from location provider."""
        try:
            from bt7274.bt7274_workstation.location import LocationProvider
            loc = LocationProvider()
            if loc.update():
                return loc.lat_lon
        except Exception as e:
            error(f"Location fetch failed: {e}")
        return None

    def _log_state_change(self, state: str):
        """Log state changes to telemetry/system (per-day)."""
        log_file = daily_log_path(self._system_log_dir, "bt7274_system")
        append_log(log_file, f"[environmental_warnings] {state}")

    def _log_warning(self, alert_type: str, severity: str, details: dict):
        """Log weather warnings to telemetry/health (per-day JSONL)."""
        log_file = daily_jsonl_path(self._health_log_dir, "weather_warnings")
        entry = {
            "timestamp": datetime.now().isoformat(),
            "type": alert_type,
            "severity": severity,
            "details": details,
        }
        append_jsonl(log_file, entry)

    def _warn(self, message: str, severity: str = "medium"):
        """Issue a weather warning to the UI."""
        if severity in ("critical", "high"):
            warning(f"ENVIRONMENTAL ALERT: {message}")
        else:
            info(f"ENVIRONMENTAL: {message}")

    def check(self) -> Optional[dict]:
        """Perform a single weather check and warn if needed."""
        if not self.enabled:
            return None

        lat_lon = self._get_location()
        if not lat_lon:
            return None

        lat, lon = lat_lon
        weather = self._fetch_weather(lat, lon)
        if not weather:
            return None

        self._last_weather = weather
        code = weather.get("weathercode")
        temp = weather.get("temperature")

        # Check weather code alerts
        if code is not None and code in WEATHER_ALERT_CODES:
            alert_type, severity = WEATHER_ALERT_CODES[code]
            if code not in self._warned_codes:
                self._warned_codes.add(code)
                msg = self._alert_message(alert_type, weather)
                self._warn(msg, severity)
                self._log_warning(alert_type, severity, weather)

        # Check temperature extremes
        if temp is not None:
            if temp >= TEMP_THRESHOLDS["extreme_heat"] and "extreme_heat" not in self._warned_temps:
                self._warned_temps.add("extreme_heat")
                msg = f"Extreme heat detected: {temp}°C. Recommend hydration and shade, Pilot."
                self._warn(msg, "high")
                self._log_warning("extreme_heat", "high", weather)

            if temp <= TEMP_THRESHOLDS["extreme_cold"] and "extreme_cold" not in self._warned_temps:
                self._warned_temps.add("extreme_cold")
                msg = f"Extreme cold detected: {temp}°C. Recommend protective gear, Pilot."
                self._warn(msg, "high")
                self._log_warning("extreme_cold", "high", weather)

        # Reset warnings if conditions improve (simple approach: reset after 1 hour)
        # In a more advanced version, you could re-fetch and compare
        return weather

    def _alert_message(self, alert_type: str, weather: dict) -> str:
        """Generate a BT-themed alert message."""
        temp = weather.get("temperature")
        wind = weather.get("windspeed")
        base = {
            "rain": "Precipitation detected",
            "heavy_rain": "Heavy precipitation detected",
            "thunderstorm": "Thunderstorm activity detected",
            "thunderstorm_with_hail": "Thunderstorm with hail detected",
            "thunderstorm_with_heavy_hail": "Severe thunderstorm with heavy hail detected",
        }.get(alert_type, "Environmental hazard detected")

        parts = [base]
        if temp is not None:
            parts.append(f"{temp}°C")
        if wind is not None:
            parts.append(f"wind {wind} km/h")
        return f"{', '.join(parts)}. Take precautions, Pilot."

    def reset_warnings(self):
        """Reset all warned states (e.g., after conditions improve or on new day)."""
        self._warned_codes.clear()
        self._warned_temps.clear()

    def _monitor_loop(self):
        """Background monitoring loop."""
        last_day = datetime.now().day
        while self._running:
            # Reset warnings at midnight for a new day
            now = datetime.now()
            if now.day != last_day:
                self.reset_warnings()
                last_day = now.day

            self.check()
            time.sleep(self.interval)

    def start(self):
        """Start background weather monitoring."""
        if not self.enabled:
            info("Environmental warnings disabled.")
            return
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        self._log_state_change("enabled")
        status("ENV", "Environmental monitoring active")

    def stop(self):
        """Stop background weather monitoring."""
        if self._running:
            self._log_state_change("disabled")
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None

    def get_status(self) -> dict:
        """Return current weather monitor status."""
        return {
            "enabled": self.enabled,
            "running": self._running,
            "last_weather": self._last_weather,
            "warned_codes": sorted(self._warned_codes),
            "warned_temps": sorted(self._warned_temps),
        }
