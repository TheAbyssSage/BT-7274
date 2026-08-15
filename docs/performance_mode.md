# BT-7274 Performance Mode Documentation

## Overview

Performance Mode is a high-performance streaming TTS system that dramatically reduces the time between receiving an LLM response and hearing BT-7274's voice. Instead of synthesizing the entire response before playing any audio, Performance Mode synthesizes and plays sentences in parallel.

## Architecture

```
Standard Mode:
┌─────────────┐     ┌─────────────────┐     ┌─────────────┐
│ LLM Response│────▶│ Synthesize ALL  │────▶│ Play ALL    │
└─────────────┘     │ (6-15 seconds)│     └─────────────┘
                    └─────────────────┘

Performance Mode:
┌─────────────┐     ┌─────────────────┐     ┌─────────────┐
│ LLM Response│────▶│ Sentence 1 Synth│────▶│ Play Sent 1 │
└─────────────┘     │ (2-4s)          │     └─────────────┘
                    └─────────────────┘
                           │
                    ┌─────────────────┐     ┌─────────────┐
                    │ Sentence 2 Synth│────▶│ Play Sent 2 │
                    │ (parallel)      │     └─────────────┘
                    └─────────────────┘
                           │
                    ┌─────────────────┐     ┌─────────────┐
                    │ Sentence 3 Synth│────▶│ Play Sent 3 │
                    │ (parallel)      │     └─────────────┘
                    └─────────────────┘
```

## Key Components

### 1. StreamingXTTSClient (`tts_fast.py`)

The core of Performance Mode. Features:
- **Sentence-level streaming**: Breaks responses into sentences
- **Parallel synthesis and playback**: Three worker threads
- **Intelligent caching**: Caches synthesized sentences for reuse
- **Backpressure management**: Prevents memory issues with queue limits
- **Performance metrics**: Tracks synthesis and playback times

### 2. Pipeline Integration (`pipeline.py`)

Modified to support both modes:
- **Startup selection**: Choose mode during initialization
- **Dynamic switching**: Can be set via config or command line
- **Mode-aware playback**: Uses appropriate TTS method based on mode

### 3. Configuration (`config.yaml`)

```yaml
# Performance Mode Configuration
performance_mode: standard    # Options: standard | performance

# Streaming TTS settings (only used in performance mode)
streaming:
  enabled: false              # Auto-enabled when performance_mode = performance
  max_queue_size: 3           # Max sentences to buffer ahead
  sentence_min_length: 20       # Minimum characters to treat as a sentence
  enable_metrics: true          # Show timing stats after each response
```

## Performance Comparison

### Short Response (1-2 sentences)
| Mode | Time to First Audio | Total Time |
|------|---------------------|------------|
| Standard | 6-8s | 6-8s |
| Performance | 4-6s | 6-8s |

### Medium Response (3-5 sentences)
| Mode | Time to First Audio | Total Time |
|------|---------------------|------------|
| Standard | 10-15s | 10-15s |
| Performance | 2-4s | 8-12s |

### Long Response (6+ sentences)
| Mode | Time to First Audio | Total Time |
|------|---------------------|------------|
| Standard | 15-20s | 15-20s |
| Performance | 2-4s | 10-15s |

## Voice Quality

**BT-7274's voice is maintained in both modes.** Performance Mode uses:
- The same XTTS v2 model (`tts_models/multilingual/multi-dataset/xtts_v2`)
- The same reference speaker file (`dataset/reference_speaker.wav`)
- Pre-computed speaker conditioning latents for consistency
- Identical text preprocessing and pronunciation rules

The only difference is the timing of synthesis and playback, not the voice itself.

## Usage

### Interactive Selection

When starting the assistant, you'll see:
```
[4/9] Performance Mode Selection
  [1] Standard Mode
      Full response synthesized, then played
      Best for: Short responses, maximum voice quality

  [2] Performance Mode (STREAMING)
      Sentence-level streaming with parallel synthesis
      Best for: Long responses, minimal latency
      ⚡ First audio plays in ~2-4 seconds
      ⚡ BT-7274's voice maintained throughout
```

### Command Line

```bash
# Standard mode
bt7274 assistant --performance-mode standard

# Performance / streaming mode
bt7274 assistant --performance-mode performance
```

### Configuration File

Edit `bt7274/bt7274_assistant/config.yaml`:
```yaml
performance_mode: performance  # Options: standard | performance
```

### Startup Script

The `start_bt7274.sh` script launches the full CLI and asks which mode to use:
```bash
./scripts/start_bt7274.sh
# Select mode [1-2] (default: 1):
```

## Testing

### Compare Both Modes

```bash
source venv/bin/activate
python bt7274/bt7274_assistant/scripts/test_performance_mode.py
```

This synthesizes the same test phrase in both modes and shows timing comparison.

### Test Streaming TTS

```bash
source venv/bin/activate
python bt7274/bt7274_assistant/scripts/test_tts_optimizations.py
```

Tests caching, text preprocessing, and cache management.

## Troubleshooting

### Performance Mode Issues

**Problem**: Audio stutters or sentences overlap
- **Solution**: Reduce `max_queue_size` in config.yaml to 2
- **Cause**: Too many sentences buffered ahead

**Problem**: First sentence takes too long
- **Solution**: Ensure model is warmed up (happens automatically)
- **Cause**: Cold start - first synthesis after loading is slower

**Problem**: Memory usage increases over time
- **Solution**: Say "clear tts cache" or restart assistant
- **Cause**: Audio cache accumulation

### Standard Mode Issues

**Problem**: Long wait for long responses
- **Solution**: Switch to Performance Mode
- **Cause**: Full synthesis required before playback

## Advanced Configuration

### Streaming Settings

In `config.yaml`:
```yaml
streaming:
  max_queue_size: 3        # Increase for smoother playback (uses more RAM)
  sentence_min_length: 20  # Decrease to split shorter sentences
  enable_metrics: true     # Set false to hide timing stats
```

### Cache Settings

In `tts_fast.py`:
```python
self._max_cache_size = 50  # Increase to cache more responses (uses more disk)
```

## Performance Tips

1. **Use Performance Mode for conversations**: Best when BT asks follow-up questions
2. **Use Standard Mode for short commands**: "Open Safari", "What's the time"
3. **Pre-generate standby clips**: Reduces latency for common responses
4. **Clear cache periodically**: Prevents disk space issues
5. **Monitor metrics**: Use `enable_metrics: true` to track performance

## Future Improvements

1. **Adaptive Mode**: Automatically switch between modes based on response length
2. **Word-level Streaming**: Even finer granularity for near-instant playback
3. **Predictive Synthesis**: Start synthesizing before LLM response is complete
4. **GPU Acceleration**: Use MPS (Metal) for faster synthesis on Apple Silicon

## Summary

Performance Mode provides:
- **2-4 second time-to-first-audio** (vs 6-15s in Standard Mode)
- **Same BT-7274 voice quality** maintained throughout
- **Parallel synthesis and playback** for maximum efficiency
- **Configurable settings** for different use cases
- **Easy switching** between modes at startup or via config

Choose Performance Mode for the most responsive BT-7274 experience!