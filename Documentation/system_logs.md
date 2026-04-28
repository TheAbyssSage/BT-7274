# BT-7274 System Logs

## Overview

BT-7274 maintains a comprehensive logging infrastructure across multiple directories. This document describes the log directory structure, file formats, and how to read them.

---

## Directory Structure

```
logs/
├── bt-pilot_interactions/     # Full conversation logs (JSONL)
├── bt_logs/                    # Web search logs (JSONL)
├── system_logs/                # System events (plain text)
├── pilot_health/               # Weather/environmental warnings (JSONL)
├── pilot_logs/                 # Pilot-specific events (extensible)
├── pilot_voice_commands/       # Voice command history (extensible)
├── bt_vision/                  # Vision/perception logs (extensible)
├── bt_workstation/             # Workstation tool logs (extensible)
└── bt_brief/                   # Mission brief logs (extensible)
```

---

## File Formats

### Plain Text Logs (`.log`)

Used for: `system_logs`

```
2025-04-28T12:00Z [battery] level=9%
2025-04-28T12:05Z [vpn] connected proton-be-01 wifi=Starbucks_Guest
2025-04-28T12:10Z [environmental_warnings] enabled
```

Format: `{ISO_TIMESTAMP} [{TAG}] {MESSAGE}`

### JSONL Logs (`.jsonl`)

Used for: `bt-pilot_interactions`, `bt_logs`, `pilot_health`

Each line is a self-contained JSON object:

```json
{"timestamp": "2025-04-28T12:00:00", "type": "heavy_rain", "severity": "high", "details": {"temperature": 18}}
{"timestamp": "2025-04-28T12:05:00", "type": "thunderstorm", "severity": "high", "details": {"temperature": 22}}
```

---

## Log Types

| Tag | Source | Description | Example |
|-----|--------|-------------|---------|
| `[battery]` | `battery_monitor.py` | Critical battery levels | `level=9%` |
| `[vpn]` | `vpn_monitor.py` | VPN state changes | `connected proton-be-01 wifi=Starbucks_Guest` |
| `[environmental_warnings]` | `weather_monitor.py` | Monitor enable/disable | `enabled` |
| `[weather]` | `weather_monitor.py` | Weather warnings (JSONL) | See `pilot_health/` |

---

## Viewing Logs

### Command Line

```bash
# Today's system events
cat logs/system_logs/bt7274_system_$(date +%Y-%m-%d).log

# Today's interactions (pretty-printed)
cat logs/bt-pilot_interactions/bt7274_interactions_$(date +%Y-%m-%d).jsonl | python -m json.tool

# Search logs
cat logs/bt_logs/bt_logs_$(date +%Y-%m-%d).jsonl | python -m json.tool
```

### Python

```python
from pathlib import Path
import json
from datetime import datetime

log_dir = Path("logs/system_logs")
today = datetime.now().strftime("%Y-%m-%d")
log_file = log_dir / f"bt7274_system_{today}.log"

with open(log_file) as f:
    for line in f:
        print(line.strip())
```

### Using `view_logs.py`

```bash
python view_logs.py              # Today's interactions
python view_logs.py --all        # All log files
python view_logs.py --summary    # Summary statistics
python view_logs.py --date 2026-04-24  # Specific date
python view_logs.py --logs       # All logs content
```

---

## Log Rotation

Logs are automatically rotated daily based on filename date suffix. There is no automatic deletion — old logs should be archived or cleaned up manually.

---

## Privacy Considerations

- **Interaction logs** contain full voice transcriptions and responses
- **Search logs** contain all web queries
- **System logs** contain Wi-Fi SSIDs and VPN server names
- **Location context** is included in interaction logs when available

Consider encrypting or periodically purging `logs/` if operating in sensitive environments.

---

## File Location

- **Log directories**: Created automatically at startup in `logs/`
- **System log writer**: `bt7274_workstation/battery_monitor.py`, `bt7274_workstation/vpn_monitor.py`, `bt7274_workstation/weather_monitor.py`
- **Interaction log writer**: `bt7274_workstation/interaction_logger.py`
- **Log viewer**: `view_logs.py`
