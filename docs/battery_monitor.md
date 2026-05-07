# BT-7274 Battery Monitor

## Overview

The Battery Monitor is BT-7274's power-management subsystem. It continuously tracks the MacBook's battery level, warns at configurable thresholds, and logs critical levels (≤10%) to `logs/system_logs`.

---

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  macOS pmset    │────▶│  BatteryMonitor │────▶│  BT-7274 TTS   │
│  -g batt        │     │  (60s interval) │     │  Voice Warnings│
└─────────────────┘     └─────────────────┘     └─────────────────┘
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

| Level | Voice Line |
|-------|-----------|
| **≤ 5%** | "CRITICAL BATTERY: {level}% — Connect power immediately, Pilot." |
| **≤ 10%** | "LOW BATTERY: {level}% — Recommend connecting power, Pilot." |
| **≤ 20%** | "BATTERY AT {level}% — Consider connecting power, Pilot." |
| **≤ 50%** | "BATTERY AT {level}% — Monitor power levels, Pilot." |

---

## Configuration (`config.yaml`)

```yaml
battery:
  enabled: true
  interval: 60              # seconds between checks
  thresholds: [50, 20, 10, 5]
```

### Options

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enabled` | bool | `true` | Master switch for battery monitoring |
| `interval` | int | `60` | Seconds between battery checks |
| `thresholds` | list[int] | `[50, 20, 10, 5]` | Warning thresholds (descending) |

---

## Hysteresis

To prevent spam, warnings use a **+2% recovery buffer**:

- If battery drops to **9%** → warns for 10% threshold
- If battery recovers to **12%** → resets the 10% warning
- If battery drops to **9%** again → warns again

This ensures you get re-warned if the battery genuinely drops back down, but not if it fluctuates by 1%.

---

## Log Format

Critical levels (≤10%) are written to `logs/system_logs/bt7274_system_YYYY-MM-DD.log`:

```
2025-04-28T12:00Z [battery] level=9%
```

---

## File Location

- **Source**: `bt7274_workstation/battery_monitor.py`
- **Pipeline integration**: `bt7274_assistant/pipeline.py` (step 10.1)
