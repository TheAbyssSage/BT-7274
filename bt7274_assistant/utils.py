"""
Audio utilities for recording, playback, and processing.
"""

import os
import tempfile
import wave
import struct
from pathlib import Path
from typing import Optional

import numpy as np
import sounddevice as sd
import soundfile as sf


def play_audio(wav_path: str, device: Optional[int] = None):
    """Play a WAV audio file through the default output device."""
    try:
        data, samplerate = sf.read(wav_path)
        sd.play(data, samplerate, device=device)
        sd.wait()
    except Exception as e:
        print(f"  ✗ Audio playback error: {e}")
        # Fallback to afplay on macOS
        os.system(f'afplay "{wav_path}"')


def beep(frequency: int = 880, duration: float = 0.15, samplerate: int = 44100):
    """Play a simple beep tone."""
    t = np.linspace(0, duration, int(samplerate * duration), False)
    tone = np.sin(frequency * t * 2 * np.pi) * 0.3
    tone = np.concatenate([tone, np.zeros(int(samplerate * 0.1))])
    sd.play(tone, samplerate)
    sd.wait()


def _warmup_audio():
    """Pre-open and close a dummy stream to prevent macOS PortAudio alert beep."""
    try:
        with sd.InputStream(samplerate=16000, channels=1, dtype=np.float32, blocksize=1024):
            pass
    except Exception:
        pass


def record_until_silence(config: dict) -> Optional[str]:
    """
    Record audio from microphone until silence is detected.
    Includes a post-wake grace period so the mic stays open after the trigger word.
    Returns path to temporary WAV file.
    """
    sample_rate = config.get("sample_rate", 16000)
    silence_threshold = config.get("silence_threshold", 0.02)
    silence_duration = config.get("silence_duration", 1.5)
    max_record_seconds = config.get("max_record_seconds", 30)
    post_wake_grace = config.get("post_wake_grace", 1.5)

    # Warm up PortAudio to suppress macOS alert sound on first real stream open
    _warmup_audio()

    print("    Recording...")

    chunk_duration = 0.1  # 100ms chunks
    chunk_samples = int(sample_rate * chunk_duration)
    silence_chunks_needed = int(silence_duration / chunk_duration)
    grace_chunks = int(post_wake_grace / chunk_duration)
    max_chunks = int(max_record_seconds / chunk_duration)

    audio_buffer = []
    silence_counter = 0
    recording = True
    speech_detected = False
    grace_counter = 0

    def callback(indata, frames, time_info, status):
        nonlocal silence_counter, recording, speech_detected, grace_counter
        if not recording:
            return

        # Compute RMS energy
        rms = np.sqrt(np.mean(indata**2))
        audio_buffer.append(indata.copy())

        if rms < silence_threshold:
            silence_counter += 1
        else:
            silence_counter = 0
            if not speech_detected:
                speech_detected = True
                print("    🗣 Speech detected, holding channel open...")

        # Grace period: once speech is detected, require extra silence before stopping
        if speech_detected:
            if silence_counter >= silence_chunks_needed + grace_chunks and len(audio_buffer) > 10:
                recording = False
        else:
            # Before speech: normal silence detection (stop if ambient silence)
            if silence_counter >= silence_chunks_needed and len(audio_buffer) > 10:
                recording = False

    # Start recording
    stream = sd.InputStream(
        samplerate=sample_rate,
        channels=1,
        dtype=np.float32,
        blocksize=chunk_samples,
        callback=callback
    )

    with stream:
        import time
        start_time = time.time()
        while recording and (time.time() - start_time) < max_record_seconds:
            time.sleep(0.05)

    if len(audio_buffer) < 5:
        print("    ✗ Recording too short.")
        return None

    # Concatenate and save
    audio = np.concatenate(audio_buffer, axis=0).flatten()

    temp_path = tempfile.mktemp(suffix=".wav")
    sf.write(temp_path, audio, sample_rate)
    return temp_path


def resample_audio(input_path: str, output_path: str, target_sr: int = 22050):
    """Resample an audio file to target sample rate."""
    import librosa
    audio, sr = librosa.load(input_path, sr=target_sr, mono=True)
    sf.write(output_path, audio, target_sr)
