# BT-7274 Action Handler

## Overview

The Action Handler is BT-7274's command-execution subsystem. It parses structured action requests from the LLM (or direct calls), validates them against an allow-list, and executes the corresponding Python function.

---

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  LLM Response   │────▶│  ActionHandler  │────▶│  Registered     │
│  (JSON block)   │     │  parse_and_execute│    │  Function       │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                               │
                               ▼
                        ┌─────────────────┐
                        │  Allow-list     │
                        │  Check          │
                        └─────────────────┘
```

---

## Registration

Actions are registered via the `@register_action("name")` decorator:

```python
@register_action("tell_time")
def action_tell_time():
    """Return current time."""
    now = datetime.now().strftime("%I:%M %p")
    return f"The current time is {now}."
```

All registered actions are stored in the `_ACTIONS` dictionary.

---

## Allowed Commands (`config.yaml`)

```yaml
actions:
  enabled: true
  allowed_commands:
    - say
    - open
    - run_script
    - set_volume
    - tell_time
    - tell_date
    - web_search
    - trigger_shortcut
    - search_web
    - get_location
    - get_location_structured
    - get_weather
    - get_weather_for_location
    - get_weather_forecast
    - clear_tts_cache
    - read_logs
```

**Security**: Only commands in this list can be executed. Unknown or disallowed actions return:

```
Action '{name}' is not allowed.
```

---

## Built-in Actions

| Command | Function | Parameters |
|---------|----------|------------|
| `say` | No-op (TTS handles this) | `text` |
| `open` | Open macOS app | `app` |
| `run_script` | Execute shell command | `script` |
| `set_volume` | Set system volume | `level` (0-100) |
| `tell_time` | Current time | — |
| `tell_date` | Current date | — |
| `web_search` | Open browser search | `query` |
| `trigger_shortcut` | Run macOS Shortcut | `name` |
| `search_web` | DuckDuckGo search + return results | `query` |
| `get_location` | Human-readable location | — |
| `get_location_structured` | JSON location data | — |
| `get_weather` | Current weather at location | — |
| `get_weather_for_location` | Weather for specific place | `location` |
| `get_weather_forecast` | Multi-day forecast | `days`, `location` |
| `clear_tts_cache` | Clear TTS response cache | — |
| `read_logs` | Read recent interaction logs | `lines`, `date`, `search` |

---

## JSON Parsing

The handler accepts actions in three formats:

1. **Raw JSON** (entire response is JSON):
   ```json
   {"action": "tell_time", "params": {}}
   ```

2. **JSON code block**:
   ```json
   ```json
   {"action": "set_volume", "params": {"level": 75}}
   ```
   ```

3. **Inline JSON** (loose matching):
   ```
   Let me check that. {"action": "get_weather", "params": {}}
   ```

---

## File Location

- **Source**: `bt7274_workstation/actions.py`
- **Pipeline integration**: `bt7274_assistant/pipeline.py` (step 7)
