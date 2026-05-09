# BT-7274 Logging System

> Last updated: 2026-05-03

## Overview

All runtime data is persisted under the `logs/` directory at the project root. The structure is organized by **domain** rather than by **source component**, making it easier to browse, query, and archive.

## Directory Layout

```
logs/
├── archive/              # Session cache archives (timestamped folders)
├── bt_memory/            # BT's internal memory / free-form logs
├── conversations/          # Pilot↔BT interaction transcripts (JSONL)
├── pilot_memory/           # Pilot's personal logs, todos, and notes
├── telemetry/
│   ├── system/             # Battery, VPN, weather state changes
│   ├── health/             # Environmental warnings, wellness alerts
│   ├── voice/              # STT confidence, TTS metrics, wake events
│   ├── hardware/           # CPU, RAM, disk, thermal, uptime snapshots
│   └── network/            # Wi-Fi, VPN, latency, public-network events
└── vision/                 # Visual observations + archived images
```

## Directory Reference

### `conversations/`
- **Format:** JSONL (one JSON object per line)
- **Files:** `bt7274_interactions_YYYY-MM-DD.jsonl`
- **Content:** Full interaction records including timestamps, pilot message, BT response, STT confidence, LLM response time, TTS metrics, actions executed, errors, location/weather context, and metadata.

### `bt_memory/`
- **Format:** Text (`.log`) and JSONL
- **Files:** `bt_YYYY-MM-DD.log`, `bt_logs_YYYY-MM-DD.jsonl`
- **Content:** Free-form BT internal logs and structured search query logs.

### `pilot_memory/`
- **Format:** Text (`.log`), Markdown (`.md`), and JSONL
- **Files:**
  - `pilot_YYYY-MM-DD.log` — free-form pilot logs
  - `pilot_logs.md` — single-file pilot log (optional)
  - `interaction_details_YYYY-MM-DD.jsonl` — per-interaction detail dumps
  - `<name>_todo.json` — to-do lists
  - `<name>_notes.jsonl` — personal notes
- **Content:** Anything the pilot explicitly saves via voice commands (`make log`, `make note`, `add todo`).

### `telemetry/system/`
- **Format:** Text (`.log`)
- **Files:** `bt7274_system_YYYY-MM-DD.log`
- **Content:** State-change events for battery, VPN, and environmental warnings. One line per event with an ISO timestamp.

### `telemetry/health/`
- **Format:** JSONL
- **Files:** `weather_warnings_YYYY-MM-DD.jsonl`
- **Content:** Environmental hazard warnings (rain, thunderstorms, extreme temperatures) with severity levels and weather details.

### `telemetry/voice/`
- **Format:** JSONL
- **Files:** `voice_telemetry_YYYY-MM-DD.jsonl`
- **Content:**
  - `wake_word` events — trigger phrase, confidence, latency
  - `stt` events — transcript, confidence, model, duration
  - `intent` events — classified intent, action triggered, LLM fallback flag
  - `tts` events — text length, generation time, cache hit, streaming flag
  - `error` events — pipeline stage, error type, message

### `telemetry/hardware/`
- **Format:** JSONL
- **Files:** `hardware_telemetry_YYYY-MM-DD.jsonl`
- **Content:** Periodic snapshots of:
  - CPU usage (%)
  - RAM usage (total / used / percent)
  - Disk usage (total / used / free / percent)
  - macOS thermal state (if available)
  - System uptime (seconds)

### `telemetry/network/`
- **Format:** JSONL
- **Files:** `network_telemetry_YYYY-MM-DD.jsonl`
- **Content:** Periodic snapshots of:
  - Wi-Fi SSID, BSSID, RSSI (dBm), TX rate (Mbps)
  - VPN connection state and service name
  - Round-trip latency to `1.1.1.1` (ms)
  - Public Wi-Fi detection flag
  - Change events (`wifi_changed`, `vpn_changed`)

### `vision/`
- **Format:** JSONL + image files
- **Files:**
  - `bt_vision_YYYY-MM-DD.jsonl` — observation records
  - `images/YYYY-MM-DD/` — archived camera frames
- **Content:** Vision model descriptions, trigger type, pilot query, model name, response time, and paths to archived images.

### `archive/`
- **Format:** Mixed (session cache dumps)
- **Folders:** `<timestamp>/`
- **Content:** End-of-session archives of TTS outputs, STT temp files, semantic vectors, speaker latents, location cache, and session state.

## Configuration

Telemetry modules are controlled from `bt7274_assistant/config.yaml`:

```yaml
hardware_telemetry:
  enabled: true
  interval: 60          # seconds between snapshots

network_telemetry:
  enabled: true
  interval: 30          # seconds between snapshots
  latency_target: "1.1.1.1"

voice_telemetry:
  enabled: true
```

## API / Helpers

All paths are exposed through `bt7274_workstation.log_manager`:

```python
from bt7274.bt7274_workstation.log_manager import (
    get_conversations_dir,
    get_bt_memory_dir,
    get_pilot_memory_dir,
    get_telemetry_system_dir,
    get_telemetry_health_dir,
    get_telemetry_voice_dir,
    get_telemetry_hardware_dir,
    get_telemetry_network_dir,
    get_vision_dir,
    get_archive_dir,
    daily_jsonl_path,
    daily_log_path,
    append_jsonl,
    append_log,
    list_log_structure,
    get_log_tree,
    migrate_legacy_logs,
)
```

## Legacy Migration

If you previously used the old flat layout (`bt-pilot_interactions/`, `bt_logs/`, `system_logs/`, etc.), run this once to migrate existing files:

```python
from bt7274.bt7274_workstation.log_manager import migrate_legacy_logs
migrate_legacy_logs()
```

This is automatically called at BT startup via `core.py`.

## Notes

- All daily files use the `YYYY-MM-DD` suffix so they sort chronologically.
- JSONL files are append-only and can be streamed/processed line-by-line without loading the entire file.
- The `telemetry/` subtree is designed for time-series analysis and alerting.
