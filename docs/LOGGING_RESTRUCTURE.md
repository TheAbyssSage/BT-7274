# BT-7274 Logging System Restructure (2026-05-11)

## Summary of Changes

This update reorganizes the BT-7274 logging system to consolidate telemetry and archive structures for better organization and easier browsing of historical logs.

## What Changed

### 1. **Telemetry Consolidation**
   - **Before:** Separate `telemetry/hardware/` and `telemetry/network/` directories
   - **After:** All system telemetry (hardware metrics + network status) consolidated into `telemetry/system/`
   
   **Files Affected:**
   - `bt7274/bt7274_workstation/log_manager.py` — Updated `get_telemetry_hardware_dir()` and `get_telemetry_network_dir()` to point to `telemetry/system/`
   - `bt7274/bt7274_workstation/hardware_telemetry.py` — Automatically uses new location (no code changes needed)
   - `bt7274/bt7274_workstation/network_telemetry.py` — Automatically uses new location (no code changes needed)
   - `bt7274/bt7274_workstation/vpn_monitor.py` — Automatically uses new location (no code changes needed)

### 2. **Centralized Archive Structure**
   - **Before:** Each session created a new timestamped folder: `archive/20260503_230442/`, `archive/20260504_020325/`, etc.
   - **After:** Single consolidated file: `archive/sessions.jsonl` with one JSON entry per line for each archived session
   
   **Benefits:**
   - Easier to browse session history as a single file
   - Dated/timed metadata preserved in each entry for historical lookups
   - Reduces filesystem clutter (no more dozens of nested directories)
   
   **Files Affected:**
   - `bt7274/bt7274_workstation/session_cache_manager.py` — Updated `archive_and_clear_session()` to write to centralized JSONL

### 3. **Automatic Migration**
   A new migration function `migrate_telemetry_and_archive()` handles:
   - Moving existing hardware telemetry files to `telemetry/system/`
   - Moving existing network telemetry files to `telemetry/system/`
   - Consolidating old timestamped archive folders into `sessions.jsonl`
   
   **Files Affected:**
   - `bt7274/bt7274_workstation/log_manager.py` — New migration function
   - `bt7274/bt7274_assistant/pipeline/core.py` — Calls migration on startup

### 4. **Documentation Updates**
   - `docs/logging_system.md` — Updated to reflect new structure and file organization
   - Updated last modified date to 2026-05-11

## New Log Directory Structure

```
logs/
├── archive/                    # Session archives (centralized)
│   └── sessions.jsonl          # One timestamped entry per archived session
├── bt_memory/                  # BT internal logs
├── conversations/              # Pilot↔BT interactions
├── pilot_memory/               # Pilot's personal data
├── telemetry/
│   ├── system/                 # Hardware + Network telemetry (consolidated)
│   │   ├── hardware_telemetry_2026-05-11.jsonl
│   │   └── network_telemetry_2026-05-11.jsonl
│   ├── health/                 # Environmental/wellness alerts
│   └── voice/                  # STT/TTS/wake-word events
└── vision/                     # Visual observations
```

## Session Archive Entry Format

Each line in `archive/sessions.jsonl` is a JSON object:

```json
{
  "timestamp": "2026-05-11T14:30:45.123456",
  "session_timestamp": "20260511_143045",
  "session_state": { ... },
  "file_counts": {
    "tts_outputs": 25,
    "stt_temp": 8,
    "semantic": 1,
    ...
  },
  "cache_location": "/path/to/session_cache"
}
```

## Migration Details

When BT-7274 starts, it automatically:
1. Checks for old hardware/network telemetry directories
2. Moves any files to `telemetry/system/` (if not already there)
3. Consolidates old timestamped archive folders into `sessions.jsonl` (if not already done)
4. Cleans up empty old directories

This is a one-shot operation — safe to run multiple times (skips already-migrated items).

## Backward Compatibility

- Existing code continues to use `get_telemetry_hardware_dir()` and `get_telemetry_network_dir()` — these now return `telemetry/system/` instead
- Session cache manager functions work the same way — archive structure is internal detail
- Old archive folders remain intact (for safety); new sessions use consolidated format

## Files Modified

1. `bt7274/bt7274_workstation/log_manager.py` — Core logic + migration
2. `bt7274/bt7274_workstation/session_cache_manager.py` — Archive consolidation
3. `bt7274/bt7274_assistant/pipeline/core.py` — Trigger migration on startup
4. `docs/logging_system.md` — Documentation updates

## Testing

To verify the restructure is working:

```bash
# View current log structure
cd /path/to/BT-7274
python -c "from bt7274.bt7274_workstation.log_manager import get_log_tree; print(get_log_tree())"

# Check migration results
python -c "from bt7274.bt7274_workstation.log_manager import migrate_telemetry_and_archive; print(migrate_telemetry_and_archive())"
```

## Notes

- All timestamps in system telemetry files use ISO 8601 format (YYYY-MM-DDTHH:MM:SSZ)
- JSONL format ensures each session archive entry can be parsed independently
- Hardware and network telemetry continue to write daily files with consistent naming patterns
