# BT-7274 TTS Optimization Summary

This is a quick-reference summary of the TTS optimizations. For full technical details, see [`TTS_OPTIMIZATIONS.md`](TTS_OPTIMIZATIONS.md).

## Key Improvements

| # | Optimization | Impact |
|---|--------------|--------|
| 1 | **Response Caching** | 50–80% faster for repeated responses |
| 2 | **Enhanced Standby Clips** | 70–90% faster for common phrases |
| 3 | **Improved Text Processing** | 0–20% faster for first-time responses |
| 4 | **Memory Management** | Better long-term stability |

## Quick Commands

```bash
# Regenerate standby clips
python scripts/regenerate_standby_bt_voice.py --force

# Test optimizations
python scripts/test_tts_optimizations.py

# Start the assistant
./start_bt7274.sh
```

## Maintenance

- **Clear cache:** Say "BT, clear tts cache" or restart the assistant.
- **Update standby clips:** After editing `config.yaml`, run the regeneration script and restart.

For architecture details, configuration options, and troubleshooting, refer to [`TTS_OPTIMIZATIONS.md`](TTS_OPTIMIZATIONS.md).