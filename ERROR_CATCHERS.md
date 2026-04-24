# BT-7274 Error Catchers Reference

This document lists all error triggers and exception handlers added across the BT-7274 assistant codebase. Errors are captured at the component level and reported to the **per-interaction** error list, which is stored in each interaction log entry under the `errors` field.

---

## Error Reporting Infrastructure

### `pipeline.py` — `_report_error()`

Central error reporting method on `BT7274Assistant`:

```python
def _report_error(self, component: str, function: str, error: Exception, context: dict = None):
    error_entry = {
        "timestamp": datetime.now().isoformat(),
        "component": component,
        "function": function,
        "error_type": type(error).__name__,
        "error_message": str(error),
        "traceback": traceback.format_exc(),
        "context": context or {},
    }
    self.errors_this_interaction.append(error_entry)   # per-interaction
    self.errors_this_session.append(error_entry)         # session-wide backup
```

Every error caught in the pipeline is appended to `self.errors_this_interaction`. When `InteractionLogger.log_interaction()` is called, **only the errors from the current interaction** are passed under the `errors` key. The list is then cleared for the next turn.

This means:
- **Conversation 1** → log entry contains only errors from Convo 1
- **Conversation 2** → log entry contains only errors from Convo 2
- No cross-contamination between interactions

---

## Module-by-Module Error Catchers

### 1. `pipeline.py` — Main Pipeline

| Function | Component | What’s Protected | On Error |
|----------|-----------|------------------|----------|
| `initialize()` | `stt` | WhisperSTT initialization + model preload | Prints failure, logs error |
| `initialize()` | `llm` | OllamaClient initialization | Prints failure, logs error |
| `initialize()` | `tts` | XTTSClient / StreamingXTTSClient init + warmup | Prints failure, logs error |
| `initialize()` | `actions` | ActionHandler initialization | Prints failure, logs error |
| `initialize()` | `location` | LocationProvider initialization + first update | Prints failure, logs error |
| `process_command()` | `stt` | `stt.transcribe(audio_path)` | Logs error, sets `text = ""`, `confidence = 0.0` |
| `process_command()` | `actions` | `actions.execute("get_location")` | Logs error, returns fallback message |
| `process_command()` | `actions` | `actions.execute("tell_time")` / `tell_date` | Logs error, returns fallback message |
| `process_command()` | `actions` | `actions.execute("get_weather")` / `get_weather_for_location` | Logs error, returns fallback message |
| `process_command()` | `llm` | `llm.chat(weather_summary_prompt)` | Logs error, returns raw weather data |
| `process_command()` | `actions` | `actions.execute("search_web")` | Logs error, returns fallback message |
| `process_command()` | `llm` | `llm.chat(search_summary_prompt)` | Logs error, returns raw search results |
| `process_command()` | `llm` | `llm.chat(text)` (general fallback) | Logs error, returns BT-style error response |
| `process_command()` | `tts` | `play_audio(standby_wav)` | Logs error, falls through to TTS |
| `process_command()` | `tts` | `tts.speak_streaming()` / `tts.speak()` | Logs error, skips audio playback |
| `process_command()` | `tts` | `play_audio(output_wav)` | Logs error, skips audio playback |

---

### 2. `actions.py` — Action Handler

| Action | Function | What’s Protected | On Error |
|--------|----------|------------------|----------|
| `open` | `action_open()` | `os.system(f'open -a "{app}"')` | Returns `"Failed to open {app}: ..."` |
| `run_script` | `action_run_script()` | `subprocess.run(...)` | Returns `"Script failed: ..."` |
| `set_volume` | `action_set_volume()` | `osascript` volume command | Returns `"Failed to set volume: ..."` |
| `tell_time` | `action_tell_time()` | `datetime.now().strftime()` | Returns `"Failed to get time: ..."` |
| `tell_date` | `action_tell_date()` | `datetime.now().strftime()` | Returns `"Failed to get date: ..."` |
| `web_search` | `action_web_search()` | `webbrowser.open()` | Returns `"Search failed: ..."` |
| `trigger_shortcut` | `action_trigger_shortcut()` | `shortcuts run` command | Returns `"Shortcut failed: ..."` |
| `search_web` | `action_search_web()` | `DDGS` search query | Returns `"Search failed: ..."` |
| `get_location` | `action_get_location()` | `LocationProvider.update()` | Returns `"Location error: ..."` |
| `get_location_structured` | `action_get_location_structured()` | `LocationProvider.update()` + JSON build | Returns `"Location error: ..."` |
| `get_weather` | `action_get_weather()` | `LocationProvider.update()` + `_fetch_weather()` | Returns `"Weather data unavailable: ..."` |
| `get_weather_for_location` | `action_get_weather_for_location()` | Geocoding request + `_fetch_weather()` | Returns `"Weather data unavailable: ..."` |

**Note:** `_execute_action()` and `execute()` already had `try/except` wrappers that return `"Action failed: {str(e)}"`.

---

### 3. `stt.py` — Speech-to-Text (Whisper)

| Function | What’s Protected | On Error |
|----------|------------------|----------|
| `transcribe()` | `self.model.transcribe(...)` | Returns dict with `"error"` key, `text=""`, `confidence=0.0` |
| `transcribe_buffer()` | `sf.write()` + `self.transcribe()` + `os.remove()` | Returns dict with `"error"` key, `text=""`, `confidence=0.0` |

**Error return format:**
```json
{
  "text": "",
  "confidence": 0.0,
  "language": "en",
  "error": "STT transcription failed: ..."
}
```

---

### 4. `llm.py` — LLM Clients

| Class | Function | What’s Protected | On Error |
|-------|----------|------------------|----------|
| `OllamaClient` | `chat()` | `requests.post(...)` + JSON parse | Returns BT-style error string |
| `OllamaClient` | `extract_action()` | Regex + `json.loads()` | Returns `{"error": "Action extraction failed: ..."}` |
| `CloudLLMClient` | `chat()` | `requests.post(...)` + JSON parse | Returns BT-style error string |
| `CloudLLMClient` | `extract_action()` | Regex + `json.loads()` | Returns `{"error": "Action extraction failed: ..."}` |

**Error return formats:**
- Connection error: `"Pilot, I am unable to connect to my neural network. Is Ollama running?"`
- General error: `"Pilot, an error occurred in my systems: ..."`
- Extraction error: `{"error": "Action extraction failed: ..."}`

---

### 5. `tts.py` — Standard Text-to-Speech (XTTS)

| Function | What’s Protected | On Error |
|----------|------------------|----------|
| `_warmup()` | Speaker latent cache + dummy synthesis | Prints warning, continues |
| `speak()` | `self.model.tts(...)` + `sf.write(...)` | Prints `"✗ TTS error: ..."`, sets `_last_metrics = {"error": ...}`, returns `None` |

---

### 6. `tts_fast.py` — Streaming Text-to-Speech (XTTS)

| Function | What’s Protected | On Error |
|----------|------------------|----------|
| `_warmup()` | Speaker latent cache + dummy synthesis | Prints warning, continues |
| `_synthesize_sentence()` | `self.model.tts(...)` + format conversion + `sf.write(...)` | Prints `"✗ TTS synthesis error: ..."` + traceback, returns `None` |
| `_synthesis_worker()` | Queue read + `_synthesize_sentence()` | Prints `"✗ Synthesis worker error: ..."`, continues loop |
| `_playback_worker()` | Queue read + `_play_audio_chunk()` | Prints `"✗ Playback worker error: ..."`, continues loop |
| `_play_audio_chunk()` | `sd.play(...)` + `sd.wait()` | Prints `"✗ Audio playback error: ..."` |

---

### 7. `location.py` — Location Provider

| Function | What’s Protected | On Error |
|----------|------------------|----------|
| `_reverse_geocode()` | `requests.get(...)` + JSON parse | Returns `("", "", "")` |
| `_get_macos_location()` | `CLLocationManager` + delegate + runloop | Returns `None` |
| `_get_ip_location()` | `requests.get(...)` + JSON parse | Returns `None` |
| `update()` | macOS location → IP fallback → assignment | Returns `False` |
| `location_str` (property) | `_is_stale()` + `update()` + string build | Returns `"Unknown location"` |
| `lat_lon` (property) | `_is_stale()` + `update()` | Returns `None` |
| `enrich_query()` | `_is_stale()` + `update()` + string concat | Returns original `query` |

---

## Log Entry Structure (Per-Interaction Errors)

Each interaction log entry contains **only the errors that occurred during that specific interaction**:

### Conversation 1 — Location Error
```json
{
  "timestamp": "2026-04-24T14:32:01.123456",
  "pilot_message": "Hey BT, where am I?",
  "bt_response": "Pilot, my navigation systems are currently unable to establish our position.",
  "errors": [
    {
      "timestamp": "2026-04-24T14:32:02.456789",
      "component": "actions",
      "function": "get_location",
      "error_type": "ConnectionError",
      "error_message": "HTTPSConnectionPool(host='...', port=443): Max retries exceeded",
      "traceback": "Traceback (most recent call last):\n  ...",
      "context": {}
    }
  ],
  "actions_executed": ["location"],
  "session_id": "a1b2c3d4",
  ...
}
```

### Conversation 2 — Web Search Error
```json
{
  "timestamp": "2026-04-24T14:33:15.789012",
  "pilot_message": "Hey BT, search for Titanfall news",
  "bt_response": "Pilot, my sensors cannot reach the data network at this time.",
  "errors": [
    {
      "timestamp": "2026-04-24T14:33:16.123456",
      "component": "actions",
      "function": "search_web",
      "error_type": "ImportError",
      "error_message": "No module named 'ddgs'",
      "traceback": "Traceback (most recent call last):\n  ...",
      "context": {"query": "Titanfall news"}
    }
  ],
  "actions_executed": ["search"],
  "session_id": "a1b2c3d4",
  ...
}
```

### Conversation 3 — No Errors
```json
{
  "timestamp": "2026-04-24T14:34:30.456789",
  "pilot_message": "Hey BT, what time is it?",
  "bt_response": "Pilot, today is Thursday, April 24, 2026. The current time is 02:34 PM.",
  "errors": null,
  "actions_executed": ["time"],
  "session_id": "a1b2c3d4",
  ...
}
```

---

## Adding New Error Catchers

When adding new functions or components, follow this pattern:

**In `pipeline.py`:**
```python
try:
    result = some_component.some_function()
except Exception as e:
    self._report_error("component_name", "function_name", e, context={"extra": "data"})
    result = "Fallback response for Pilot."
```

**In standalone modules (`actions.py`, `stt.py`, etc.):**
```python
def some_function():
    try:
        # risky operation
        return success_result
    except Exception as e:
        return f"Descriptive failure message: {str(e)}"
```

This ensures every failure is captured, logged per-interaction, and surfaced to the Pilot in-character.
