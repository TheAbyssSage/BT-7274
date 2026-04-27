#!/usr/bin/env python3
"""
Generate pre-recorded standby phrases using macOS 'say' command.
No heavy TTS dependencies needed — just uses the built-in system voice.
Run: python bt7274_assistant/scripts/generate_standby_simple.py
"""

import subprocess
from pathlib import Path
import yaml


def load_phrases_from_config():
    """Load all standby phrases from config.yaml."""
    config_path = Path(__file__).parent.parent / "config.yaml"
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)

    pipeline = config.get("pipeline", {})
    phrases = []

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
    output_dir = Path(__file__).parent / "standby"
    output_dir.mkdir(exist_ok=True)

    phrases = load_phrases_from_config()
    print(f"Found {len(phrases)} unique standby phrases in config.")
    print("Generating using macOS 'say' command...\n")

    generated = 0
    skipped = 0

    for phrase in phrases:
        safe_name = "".join(c if c.isalnum() else "_" for c in phrase.lower())
        output_path = output_dir / f"{safe_name}.wav"

        if output_path.exists():
            print(f"  ⏭ Skipping: {phrase}")
            skipped += 1
            continue

        print(f"  → Generating: {phrase}")
        # Use macOS say command to generate AIFF, then convert to WAV
        aiff_path = output_dir / f"{safe_name}.aiff"
        try:
            # Generate with say command (using a deeper voice if available)
            subprocess.run(
                ["say", "-v", "Alex", "-o", str(aiff_path), phrase],
                check=True,
                capture_output=True
            )
            # Convert AIFF to WAV using afconvert
            subprocess.run(
                ["afconvert", "-f", "WAVE", "-d", "LEI16@24000", str(aiff_path), str(output_path)],
                check=True,
                capture_output=True
            )
            # Clean up AIFF
            aiff_path.unlink()
            print(f"    ✓ Saved: {output_path.name}")
            generated += 1
        except subprocess.CalledProcessError as e:
            print(f"    ✗ Failed: {phrase}")
            if e.stderr:
                print(f"      Error: {e.stderr.decode()}")

    print(f"\nDone! Generated: {generated}, Skipped: {skipped}")
    print(f"Pre-recorded standby phrases are in: {output_dir}")


if __name__ == "__main__":
    generate_standby_phrases()
