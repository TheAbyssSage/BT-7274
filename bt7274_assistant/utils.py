"""
Audio utilities for recording, playback, and processing.
"""

import os
import tempfile
import time
import threading
from pathlib import Path
from typing import Optional

import numpy as np
import sounddevice as sd
import soundfile as sf
from ui import info, success, warning, error


def play_audio(wav_path: str, device: Optional[int] = None):
    """Play a WAV audio file through the default output device."""
    # Use afplay on macOS as primary (avoids PortAudio conflicts with recorder)
    if os.system(f'afplay "{wav_path}"') == 0:
        return
    # Fallback to sounddevice if afplay fails
    try:
        data, samplerate = sf.read(wav_path)
        sd.play(data, samplerate, device=device)
        sd.wait()
    except Exception as e:
        error(f"Audio playback error: {e}")


def beep(frequency: int = 880, duration: float = 0.15, samplerate: int = 44100):
    """Play a simple beep tone."""
    t = np.linspace(0, duration, int(samplerate * duration), False)
    tone = np.sin(frequency * t * 2 * np.pi) * 0.3
    tone = np.concatenate([tone, np.zeros(int(samplerate * 0.1))])
    sd.play(tone, samplerate)
    sd.wait()


class PersistentAudioRecorder:
    """
    Keeps the microphone stream open for the entire session.
    Eliminates PortAudio open/close overhead and macOS alert sounds.
    """

    def __init__(self, config: dict):
        self.sample_rate = config.get("sample_rate", 16000)
        self.silence_threshold = config.get("silence_threshold", 0.02)
        self.silence_duration = config.get("silence_duration", 1.5)
        self.max_record_seconds = config.get("max_record_seconds", 30)
        self.post_wake_grace = config.get("post_wake_grace", 1.5)
        # Adaptive noise floor settings
        self.adaptive_noise_floor = True
        self.noise_floor_alpha = 0.01  # Smoothing factor for noise floor estimation
        self.current_noise_floor = self.silence_threshold

        self._stream: Optional[sd.InputStream] = None
        self._recording = False
        self._audio_buffer: list = []
        self._silence_counter = 0
        self._speech_detected = False
        self._lock = threading.Lock()

    def _callback(self, indata, frames, time_info, status):
        with self._lock:
            if not self._recording:
                return
            rms = np.sqrt(np.mean(indata**2))
            self._audio_buffer.append(indata.copy())

            # Update adaptive noise floor
            if self.adaptive_noise_floor:
                # Exponential smoothing for noise floor estimation
                self.current_noise_floor = (
                    self.noise_floor_alpha * rms + 
                    (1 - self.noise_floor_alpha) * self.current_noise_floor
                )
                # Ensure noise floor doesn't go below minimum threshold
                self.current_noise_floor = max(self.current_noise_floor, 0.005)
                effective_threshold = max(self.silence_threshold, self.current_noise_floor * 2.0)
            else:
                effective_threshold = self.silence_threshold

            if rms < effective_threshold:
                self._silence_counter += 1
            else:
                self._silence_counter = 0
                if not self._speech_detected:
                    self._speech_detected = True
                    info("Speech detected, holding channel open...")

            chunk_duration = 0.1
            silence_chunks_needed = int(self.silence_duration / chunk_duration)
            grace_chunks = int(self.post_wake_grace / chunk_duration)

            if self._speech_detected:
                if self._silence_counter >= silence_chunks_needed + grace_chunks and len(self._audio_buffer) > 10:
                    self._recording = False
            else:
                if self._silence_counter >= silence_chunks_needed and len(self._audio_buffer) > 10:
                    self._recording = False

    def start(self):
        """Open the persistent input stream (call once at startup)."""
        if self._stream is not None:
            return
        chunk_samples = int(self.sample_rate * 0.1)
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype=np.float32,
            blocksize=chunk_samples,
            callback=self._callback
        )
        self._stream.start()

    def stop(self):
        """Close the persistent input stream."""
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def record(self, max_seconds: Optional[int] = None) -> Optional[str]:
        """Start a new recording using the already-open stream."""
        if self._stream is None:
            self.start()

        with self._lock:
            self._audio_buffer = []
            self._silence_counter = 0
            self._speech_detected = False
            self._recording = True

        info("Recording...")
        start_time = time.time()
        max_record_seconds = max_seconds if max_seconds is not None else self.max_record_seconds
        while self._recording and (time.time() - start_time) < max_record_seconds:
            time.sleep(0.05)

        with self._lock:
            if len(self._audio_buffer) < 5:
                error("Recording too short.")
                return None
            audio = np.concatenate(self._audio_buffer, axis=0).flatten()

        temp_path = tempfile.mktemp(suffix=".wav")
        sf.write(temp_path, audio, self.sample_rate)
        return temp_path


def record_until_silence(config: dict, max_seconds: Optional[int] = None) -> Optional[str]:
    """Legacy wrapper — kept for compatibility."""
    recorder = PersistentAudioRecorder(config)
    recorder.start()
    try:
        return recorder.record(max_seconds=max_seconds)
    finally:
        recorder.stop()


def resample_audio(input_path: str, output_path: str, target_sr: int = 22050):
    """Resample an audio file to target sample rate."""
    import librosa
    audio, sr = librosa.load(input_path, sr=target_sr, mono=True)
    sf.write(output_path, audio, target_sr)
