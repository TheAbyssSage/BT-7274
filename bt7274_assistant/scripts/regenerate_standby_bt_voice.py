#!/usr/bin/env python3
"""
Regenerate all standby phrases using BT-7274's voice.
Run: source venv/bin/activate && python bt7274_assistant/scripts/regenerate_standby_bt_voice.py
"""

import sys
import argparse
from pathlib import Path
import yaml
import shutil

# Add the project directory to the path
project_dir = Path(__file__).parent.parent
sys.path.insert(0, str(project_dir))

from tts import XTTSClient


def load_phrases_from_config():
    """Load all standby phrases from config.yaml."""
    config_path = project_dir / "config.yaml"
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)

    pipeline = config.get("pipeline", {})
    phrases = []

    # Collect all standby phrase lists (generic + task-specific)
    for key in pipeline:
        if key.startswith("standby_phrases"):
            phrases.extend(pipeline[key])

    # Add common response patterns for better caching coverage
    common_responses = [
        "Processing complete, Pilot.",
        "Operation complete, Pilot.",
        "Task completed, Pilot.",
        "Execution successful, Pilot.",
        "Sequence complete, Pilot.",
        "Protocol fulfilled, Pilot.",
        "Mission accomplished, Pilot.",
        "Objective achieved, Pilot.",
        "Analysis complete, Pilot.",
        "Calculation finished, Pilot.",
        "Diagnostic concluded, Pilot.",
        "Scan completed, Pilot."
    ]
    phrases.extend(common_responses)

    # Remove duplicates while preserving order
    seen = set()
    unique_phrases = []
    for p in phrases:
        if p not in seen:
            seen.add(p)
            unique_phrases.append(p)

    return unique_phrases


def regenerate_standby_phrases(force_regenerate: bool = False):
    config = {
        "model": "tts_models/multilingual/multi-dataset/xtts_v2",
        "reference_wav": "bt7274_assistant/dataset/reference_speaker.wav",
        "language": "en",
        "speed": 1.0,
        "output_dir": "bt7274_assistant/standby",
    }

    tts = XTTSClient(config)
    output_dir = project_dir / "standby"
    output_dir.mkdir(exist_ok=True)

    phrases = load_phrases_from_config()
    print(f"Found {len(phrases)} unique standby phrases in config.")
    if force_regenerate:
        print("Regenerating ALL standby phrases with BT's voice...\n")
    else:
        print("Generating missing standby phrases with BT's voice...\n")

    generated = 0
    skipped = 0
    failed = 0

    for phrase in phrases:
        safe_name = "".join(c if c.isalnum() or c in [' ', '-'] else "_" for c in phrase.lower())
        safe_name = safe_name.replace(" ", "_").replace("-", "_")
        output_path = output_dir / f"{safe_name}.wav"

        if output_path.exists() and not force_regenerate:
            print(f"  ⏭ Skipping: {phrase}")
            skipped += 1
            continue

        print(f"  → Generating: {phrase}")
        try:
            wav_path = tts.speak(phrase)
            if wav_path:
                # Remove old file if exists
                if output_path.exists():
                    output_path.unlink()
                shutil.move(wav_path, str(output_path))
                print(f"    ✓ Saved: {output_path.name}")
                generated += 1
            else:
                print(f"    ✗ Failed: {phrase}")
                failed += 1
        except Exception as e:
            print(f"    ✗ Error generating '{phrase}': {e}")
            failed += 1

    print(f"\nDone! Generated: {generated}, Skipped: {skipped}, Failed: {failed}")
    print(f"All standby phrases are now in BT's voice: {output_dir}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Regenerate standby phrases with BT's voice")
    parser.add_argument("--force", action="store_true", 
                        help="Force regenerate ALL clips even if they exist")
    args = parser.parse_args()
    
    regenerate_standby_phrases(force_regenerate=args.force)
