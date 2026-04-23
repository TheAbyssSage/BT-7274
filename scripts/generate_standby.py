#!/usr/bin/env python3
"""
Generate pre-recorded standby phrases using BT-7274's voice.
Run once after TTS model is set up.
Reads phrases from bt7274_assistant/config.yaml (generic + task-specific)
"""

import sys
from pathlib import Path
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent / "bt7274_assistant"))
from tts import XTTSClient


def load_phrases_from_config():
    """Load all standby phrases from config.yaml."""
    config_path = Path(__file__).parent.parent / "bt7274_assistant" / "config.yaml"
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)

    pipeline = config.get("pipeline", {})
    phrases = []

    # Collect all standby phrase lists (generic + task-specific)
    for key in pipeline:
        if key.startswith("standby_phrases"):
            phrases.extend(pipeline[key])

    # Remove duplicates while preserving order
    seen = set()
    unique_phrases = []
    for p in phrases:
        if p not in seen:
            seen.add(p)
            unique_phrases.append(p)

    return unique_phrases


def generate_standby_phrases():
    config = {
        "model": "tts_models/multilingual/multi-dataset/xtts_v2",
        "reference_wav": "dataset/reference_speaker.wav",
        "language": "en",
        "speed": 1.0,
        "output_dir": "standby",
    }

    tts = XTTSClient(config)
    output_dir = Path(__file__).parent.parent / "standby"
    output_dir.mkdir(exist_ok=True)

    phrases = load_phrases_from_config()
    print(f"Found {len(phrases)} unique standby phrases in config.")

    print("Generating standby phrases...")
    generated = 0
    skipped = 0
    failed = 0

    for phrase in phrases:
        safe_name = "".join(c if c.isalnum() else "_" for c in phrase.lower())
        output_path = output_dir / f"{safe_name}.wav"

        if output_path.exists():
            print(f"  ⏭ Skipping: {phrase}")
            skipped += 1
            continue

        print(f"  → Generating: {phrase}")
        wav_path = tts.speak(phrase)
        if wav_path:
            import shutil
            shutil.move(wav_path, str(output_path))
            print(f"    ✓ Saved: {output_path}")
            generated += 1
        else:
            print(f"    ✗ Failed: {phrase}")
            failed += 1

    print(f"\nDone! Generated: {generated}, Skipped: {skipped}, Failed: {failed}")
    print(f"Pre-recorded standby phrases are in: {output_dir}")


if __name__ == "__main__":
    generate_standby_phrases()
