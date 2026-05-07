# BT-7274 Interaction Logging

## Overview

The Interaction Logger records every exchange between the Pilot and BT-7274, along with rich metadata: timing, errors, TTS metrics, location context, and protocol references. Logs are stored as daily JSONL files.

---

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Pipeline       │────▶│  InteractionLogger│    │  Daily JSONL    │
│  process_command│     │  log_interaction()│    │  Files          │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                               │
                               ▼
                        ┌─────────────────┐
                        │  logs/bt-pilot/ │
                        │  interactions/  │
                        │  bt7274_        │
                        │  interactions_  │
                        │  YYYY-MM-DD.jsonl
                        └─────────────────┘
```

---

## Log Entry Schema

```json
{
  "timestamp": "2025-04-28T12:00:00",
  "session_id": "a1b2c3d4",
  "pilot_message": "What's the weather?",
  "bt_response": "Pilot, current weather in Hasselt: mainly clear, 14°C, wind 12 km/h.",
  "ai_mode": "local",
  "performance_mode": "standard",
  "interaction_type": "voice",
  "interaction_count": 5,
  "pilot_trust_level": 2,
  "protocol_reference": "Protocol 2: Uphold the Mission",
  "mission_elapsed_time": 360.5,
  "conversation_duration": 45.2,
  "llm_response_time": 1.23,
  "stt_confidence": 0.85,
  "cache_hit_type": "standby_clip",
  "clip_source": "bt_clip",
  "clip_phrase": "copy that pilot stand by",
  "audio_file_path": "/path/to/output.wav",
  "location_context": "Hasselt, Limburg, Belgium",
  "weather_context": "...",
  "actions_executed": ["weather"],
  "errors": [
    {
      "timestamp": "2025-04-28T12:00:01",
      "component": "tts",
      "function": "speak",
      "error_type": "RuntimeError",
      "error_message": "Audio device busy",
      "traceback": "..."
    }
  ],
  "tts_metrics": {
    "synthesis_time": 2.5,
    "playback_time": 3.0,
    "cached": false
  }
}
```

---

## Log Directories

| Directory | Content | File Pattern |
|-----------|---------|--------------|
| `logs/bt-pilot_interactions/` | Full interaction logs | `bt7274_interactions_YYYY-MM-DD.jsonl` |
| `logs/bt_logs/` | Search query logs | `bt_logs_YYYY-MM-DD.jsonl` |
| `logs/system_logs/` | System events | `bt7274_system_YYYY-MM-DD.log` |
| `logs/pilot_health/` | Weather warnings | `weather_warnings_YYYY-MM-DD.jsonl` |
| `logs/pilot_logs/` | Pilot-specific logs | (extensible) |
| `logs/pilot_voice_commands/` | Voice command history | (extensible) |
| `logs/bt_vision/` | Vision/perception logs | (extensible) |
| `logs/bt_workstation/` | Workstation tool logs | (extensible) |
| `logs/bt_brief/` | Mission brief logs | (extensible) |

---

## Deduplication

The logger keeps a rolling hash of the last 50 entries to prevent duplicate logging:

```python
content = f"{pilot_message.strip().lower()}|{bt_response.strip().lower()}"
hash = md5(content).hexdigest()[:16]
```

If the same message/response pair is seen twice within the window, the second entry is silently dropped.

---

## Search Logger

A separate `SearchLogger` (`bt7274_workstation/search_logger.py`) records all web searches:

```json
{
  "timestamp": "2025-04-28T12:00:00",
  "query": "Titanfall 2 release date",
  "results": "...",
  "success": true,
  "response_time": 1.5
}
```

---

## File Location

- **Interaction Logger**: `bt7274_workstation/interaction_logger.py`
- **Search Logger**: `bt7274_workstation/search_logger.py`
- **Pipeline integration**: `bt7274_assistant/pipeline.py`
