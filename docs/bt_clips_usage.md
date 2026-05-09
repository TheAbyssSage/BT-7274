# BT-7274 Original Voice Clips Usage Guide

This document explains how to use the newly integrated BT-7274 original voice clips for instant responses and TTS training.

## Overview

The BT-7274 assistant now includes all original voice lines from the Titanfall 2 game, providing authentic responses for common interactions. These clips are automatically loaded at startup and prioritized over generated responses.

## Features

### Instant Responses
- Over 885 original BT-7274 voice lines available for instant playback
- Automatic matching of user queries to appropriate pre-recorded responses
- Priority given to authentic BT voice over generated responses

### TTS Training
- Use the original clips as reference for voice training
- High-quality audio samples for fine-tuning TTS models
- Comprehensive coverage of BT's personality and vocabulary

## Technical Details

### File Structure
```
bt7274/BT-7274.Voicepack/
├── bt_clips/              # Individual WAV files
├── bt_clips_index.csv     # Mapping of lines to filenames
└── metadata.csv           # Additional metadata
```

### Integration Points
1. **Automatic Loading**: Clips are loaded during assistant initialization
2. **Phrase Matching**: Normalized text matching for accurate lookup
3. **Fallback System**: Generated responses used when no clip matches

## Usage Examples

### Instant Response Matching
Common phrases that will use BT's original voice:
- "Standing by, pilot. Climb onto my hand."
- "You're welcome, Pilot."
- "Copy that, Pilot. Stand by."
- "Understood, but I do recommend you move."
- "Be careful, pilot."

### TTS Training Applications
The clips can be used to:
1. Fine-tune voice models to match BT's exact tone
2. Create datasets for voice cloning
3. Improve pronunciation of game-specific terminology
4. Enhance emotional expression in synthetic speech

## Implementation Details

### Loading Process
1. CSV index file parsed at startup
2. Audio files validated for existence
3. Text normalized for matching
4. Mappings stored in memory for fast lookup

### Matching Algorithm
1. Exact phrase matching (normalized)
2. Partial phrase matching
3. Pattern-based matching for common responses
4. Fallback to generated speech if no match found

## Extending the System

### Adding New Mappings
To add custom phrase mappings:
1. Add entries to the bt_clips_index.csv file
2. Ensure corresponding audio files exist in bt_clips/
3. Restart the assistant to load new clips

### Custom Response Prioritization
Modify the `try_standby_for_response` method in `pipeline.py` to adjust matching priorities.

## Troubleshooting

### Missing Clips
If some clips aren't loading:
1. Verify audio files exist in bt7274/BT-7274.Voicepack/bt_clips/
2. Check that filenames match entries in bt_clips_index.csv
3. Ensure file permissions allow reading

### Matching Issues
If phrases aren't matching:
1. Check normalization in `_normalize_phrase` method
2. Verify phrase text matches exactly (case, punctuation)
3. Add custom variants to the matching algorithm

## Performance Benefits

Using original clips provides:
- Zero latency responses for matched phrases
- Perfect preservation of BT's voice characteristics
- Reduced computational load on TTS engine
- Enhanced authenticity of assistant experience