#!/usr/bin/env python3
"""
Dataset preparation script for BT-7274 voice cloning.
Converts audio to the format required by XTTS v2 and creates a reference speaker file.
"""

import os
import sys
import argparse
import csv
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf
import librosa


def ensure_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)


def convert_to_wav(input_path: Path, output_path: Path, target_sr: int = 22050):
    """Convert any audio file to mono WAV at target sample rate."""
    try:
        audio, sr = librosa.load(str(input_path), sr=target_sr, mono=True)
        sf.write(str(output_path), audio, target_sr, subtype='PCM_16')
        return True
    except Exception as e:
        print(f"  ✗ Failed to convert {input_path.name}: {e}")
        return False


def normalize_audio(audio: np.ndarray) -> np.ndarray:
    """Normalize audio to -1 dB peak."""
    peak = np.max(np.abs(audio))
    if peak > 0:
        audio = audio / peak * 0.9
    return audio


def create_reference_speaker(wav_dir: Path, output_path: Path, target_duration: float = 45.0):
    """
    Concatenate clean clips to create a reference speaker file.
    Selects clips from the middle of the dataset (often cleaner than first/last).
    """
    wav_files = sorted(wav_dir.glob("*.wav"))
    if not wav_files:
        print("No WAV files found for reference speaker.")
        return

    print(f"\nCreating reference speaker file from {len(wav_files)} clips...")

    segments = []
    total_duration = 0.0

    # Prioritize shorter, cleaner clips; skip very long ones
    for wav_file in wav_files:
        try:
            audio, sr = sf.read(str(wav_file))
            duration = len(audio) / sr
            if 1.0 <= duration <= 10.0:
                segments.append((audio, sr, duration))
                total_duration += duration
                if total_duration >= target_duration:
                    break
        except Exception as e:
            print(f"  ✗ Skipping {wav_file.name}: {e}")

    if not segments:
        print("No suitable clips found for reference speaker.")
        return

    # Resample all to the same rate
    target_sr = segments[0][1]
    combined = []
    for audio, sr, _ in segments:
        if sr != target_sr:
            audio = librosa.resample(audio.astype(np.float32), orig_sr=sr, target_sr=target_sr)
        combined.append(audio)

    # Add small silence between clips
    silence = np.zeros(int(target_sr * 0.3), dtype=np.float32)
    final_audio = np.concatenate([np.concatenate([seg, silence]) for seg in combined])
    final_audio = normalize_audio(final_audio)

    sf.write(str(output_path), final_audio, target_sr, subtype='PCM_16')
    print(f"  ✓ Reference speaker saved: {output_path} ({total_duration:.1f}s)")


def prepare_dataset(input_dir: Path, output_dir: Path, metadata_path: Path):
    """Main dataset preparation pipeline."""
    ensure_dir(output_dir)
    wav_output_dir = output_dir / "wavs"
    ensure_dir(wav_output_dir)

    # Read metadata
    lines = []
    if metadata_path.exists():
        with open(metadata_path, 'r', encoding='utf-8') as f:
            lines = [line.strip() for line in f if line.strip()]
        print(f"Loaded {len(lines)} entries from metadata.csv")
    else:
        print("Warning: metadata.csv not found. Processing all audio files.")

    # Find all audio files
    audio_extensions = {'.wav', '.mp3', '.flac', '.ogg', '.m4a'}
    audio_files = [f for f in input_dir.iterdir() if f.suffix.lower() in audio_extensions]
    print(f"Found {len(audio_files)} audio files in {input_dir}")

    converted = 0
    for audio_file in audio_files:
        output_wav = wav_output_dir / f"{audio_file.stem}.wav"
        if output_wav.exists():
            print(f"  ⏭ Skipping {audio_file.name} (already converted)")
            converted += 1
            continue

        print(f"  → Converting {audio_file.name}...")
        if convert_to_wav(audio_file, output_wav, target_sr=22050):
            converted += 1

    print(f"\n✓ Converted {converted}/{len(audio_files)} files to {wav_output_dir}")

    # Create reference speaker
    ref_path = output_dir / "reference_speaker.wav"
    create_reference_speaker(wav_output_dir, ref_path, target_duration=45.0)

    print("\nDataset preparation complete!")
    print(f"  WAV files: {wav_output_dir}")
    print(f"  Reference: {ref_path}")


def main():
    parser = argparse.ArgumentParser(description="Prepare BT-7274 voice dataset")
    parser.add_argument("--input", type=Path, default=Path("bt7274/BT-7274.Voicepack/raw"),
                        help="Input directory with raw audio files")
    parser.add_argument("--output", type=Path, default=Path("bt7274/bt7274_assistant/dataset"),
                        help="Output directory for processed dataset")
    parser.add_argument("--metadata", type=Path, default=Path("bt7274/BT-7274.Voicepack/metadata.csv"),
                        help="Path to metadata.csv")
    parser.add_argument("--create-reference", action="store_true",
                        help="Only create reference speaker from existing wavs")
    args = parser.parse_args()

    if args.create_reference:
        wav_dir = args.output / "wavs"
        ref_path = args.output / "reference_speaker.wav"
        create_reference_speaker(wav_dir, ref_path)
    else:
        prepare_dataset(args.input, args.output, args.metadata)


if __name__ == "__main__":
    main()
