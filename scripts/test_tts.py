#!/usr/bin/env python3
"""
Quick test script for BT-7274 TTS voice cloning.
"""

import argparse
import sys
from pathlib import Path

from TTS.api import TTS
import soundfile as sf


def test_tts(text: str, reference_wav: Path, output_path: Path, model_name: str = "tts_models/multilingual/multi-dataset/xtts_v2"):
    """Generate a test audio file using XTTS v2."""
    print(f"Loading TTS model: {model_name}")
    print("(First run will download ~1.8 GB model files)")

    tts = TTS(model_name)

    print(f"\nGenerating speech for: \"{text}\"")
    print(f"Using reference speaker: {reference_wav}")

    # Generate audio
    wav = tts.tts(
        text=text,
        speaker_wav=str(reference_wav),
        language="en"
    )

    sf.write(str(output_path), wav, 24000)
    print(f"\n✓ Saved to: {output_path}")
    print("Play it with: afplay test_output.wav")


def main():
    parser = argparse.ArgumentParser(description="Test BT-7274 TTS voice cloning")
    parser.add_argument("--text", type=str, default="Pilot, I am standing by.",
                        help="Text to synthesize")
    parser.add_argument("--reference", type=Path, default=Path("dataset/reference_speaker.wav"),
                        help="Path to reference speaker WAV")
    parser.add_argument("--output", type=Path, default=Path("test_output.wav"),
                        help="Output WAV file path")
    args = parser.parse_args()

    if not args.reference.exists():
        print(f"Error: Reference speaker not found: {args.reference}")
        print("Run: python scripts/prepare_dataset.py")
        sys.exit(1)

    test_tts(args.text, args.reference, args.output)


if __name__ == "__main__":
    main()
