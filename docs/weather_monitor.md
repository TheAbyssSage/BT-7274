# BT-7274 Weather & Environmental Monitor

## Overview

The Environmental Monitor is BT-7274's atmospheric hazard-detection system. It fetches live weather data from Open-Meteo, warns about rain, thunderstorms, hail, and temperature extremes, and logs all alerts to `logs/pilot_health` and `logs/system_logs`.

---

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Open-Meteo API │────▶│  WeatherMonitor │────▶│  BT-7274 TTS   │
│  (free, no key) │     │  (5 min interval)│     │  Voice Warnings│
└─────────────────┘     └─────────────────┘     └─────────────────┘
         ▲                       │
         │                       ▼
┌─────────────────┐     ┌─────────────────┐
│  LocationProvider│     │  logs/pilot/    │
│  (lat/lon)      │     │  weather_warnings│
│                 │     │  _YYYY-MM-DD.jsonl
└─────────────────┘     └─────────────────┘
                               │
                               ▼
                        ┌─────────────────┐
                        │  logs/system/   │
                        │  bt7274_system_ │
                        │  YYYY-MM-DD.log │
                        └─────────────────┘
```

---

## Voice Warnings

| Condition | Severity | Example Voice Line |
|-----------|----------|-------------------|
| Rain (light/moderate) | low/medium | "Precipitation detected, 14°C, wind 12 km/h. Take precautions, Pilot." |
| Heavy rain | high | "Heavy precipitation detected, 18°C, wind 45 km/h. Take precautions, Pilot." |
| Thunderstorm | high | "Thunderstorm activity detected, 22°C, wind 60 km/h. Take precautions, Pilot." |
| Thunderstorm + hail | critical | "Thunderstorm with hail detected, 19°C, wind 55 km/h. Take precautions, Pilot." |
| Extreme heat (≥35°C) | high | "Extreme heat detected: 36°C. Recommend hydration and shade, Pilot." |
| Extreme cold (≤-10°C) | high | "Extreme cold detected: -12°C. Recommend protective gear, Pilot." |

---

## Configuration (`config.yaml`)

```yaml
environmental_warnings:
  enabled: true
  interval: 300             # seconds between checks (5 minutes)
```

### Options

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enabled` | bool | `true` | Master switch for weather monitoring |
| `interval` | int | `300` | Seconds between weather checks |

---

## Voice Commands

| Command | Action |
|---------|--------|
| "Enable weather warnings" | Starts the environmental monitor |
| "Disable weather warnings" | Stops the environmental monitor |
| "What's the weather?" | Fetches current weather + speaks summary |
| "Weather forecast" | Fetches multi-day forecast + speaks summary |

---

## Alert Codes (WMO)

| Code | Condition | Severity |
|------|-----------|----------|
| 61 | Slight rain | low |
| 63 | Moderate rain | medium |
| 65 | Heavy rain | high |
| 80 | Rain showers | low |
| 81 | Moderate showers | medium |
| 82 | Violent showers | high |
| 95 | Thunderstorm | high |
| 96 | Thunderstorm with hail | critical |
| 99 | Thunderstorm with heavy hail | critical |

### Temperature Thresholds

| Threshold | Value | Trigger |
|-----------|-------|---------|
| Extreme heat | ≥ 35°C | Once per day |
| Extreme cold | ≤ -10°C | Once per day |

---

## Log Format

### System Logs (`logs/system_logs/bt7274_system_YYYY-MM-DD.log`)

```
2025-04-28T12:00Z [environmental_warnings] enabled
2025-04-28T12:00Z [environmental_warnings] disabled
```

### Health Logs (`logs/pilot_health/weather_warnings_YYYY-MM-DD.jsonl`)

```json
{"timestamp": "2025-04-28T12:00:00", "type": "heavy_rain", "severity": "high", "details": {"temperature": 18, "windspeed": 45, "weathercode": 65}}
```

---

## Deduplication

Warnings are deduplicated per-day:
- **Weather codes**: Once a WMO code is warned, it is not warned again until midnight
- **Temperature extremes**: Once a temperature threshold is crossed, it is not warned again until midnight

The monitor resets its warned-state cache at midnight automatically.

---

## File Location

- **Source**: `bt7274_workstation/weather_monitor.py`
- **Pipeline integration**: `bt7274_assistant/pipeline.py` (step 10.2)
