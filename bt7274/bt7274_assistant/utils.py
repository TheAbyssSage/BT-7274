"""
Audio utilities for recording, playback, and processing.
"""

import os
import sys
import tempfile
import time
import threading
from pathlib import Path
from typing import Optional
from contextlib import contextmanager

import numpy as np
import sounddevice as sd
import soundfile as sf
from bt7274.bt7274_assistant.ui import info, success, warning, error


@contextmanager
def suppress_stdout():
    """Temporarily suppress stdout (useful for noisy third-party libraries)."""
    import builtins
    original_stdout = sys.stdout
    original_print = builtins.print
    sys.stdout = open(os.devnull, 'w')
    builtins.print = lambda *args, **kwargs: None
    try:
        yield
    finally:
        sys.stdout.close()
        sys.stdout = original_stdout
        builtins.print = original_print


def play_audio(wav_path: str, device: Optional[int] = None):
    """Play a WAV audio file. Uses afplay on macOS for reliability."""
    import subprocess
    try:
        subprocess.run(["afplay", wav_path], check=True, capture_output=True)
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
    Optimized for continuous listening with minimal latency.
    """

    def __init__(self, config: dict):
        self.sample_rate = config.get("sample_rate", 16000)
        self.silence_threshold = config.get("silence_threshold", 0.02)
        self.silence_duration = config.get("silence_duration", 1.5)
        self.max_record_seconds = config.get("max_record_seconds", 30)
        self.post_wake_grace = config.get("post_wake_grace", 1.5)
        # Adaptive noise floor settings
        self.adaptive_noise_floor = True
        self.noise_floor_alpha = 0.1  # Balanced smoothing for adaptation
        self.current_noise_floor = self.silence_threshold
        # Performance optimization settings
        self.chunk_size = 0.05  # 50ms chunks for responsive detection
        self.max_buffer_size = 500  # Limit buffer size to prevent memory issues
        self.min_speech_chunks = 3  # Minimum chunks to qualify as speech

        self._stream: Optional[sd.InputStream] = None
        self._recording = False
        self._audio_buffer: list = []
        self._silence_counter = 0
        self._speech_detected = False
        self._speech_chunks = 0  # Counter for actual speech chunks
        self._ready_audio_segments: list = []  # Store completed audio segments
        self._lock = threading.Lock()
        self._last_callback_time = time.time()
        self._processing_queue = []  # Queue for segments being processed

    def _callback(self, indata, frames, time_info, status):
        # Performance optimization: Skip processing if called too frequently
        current_time = time.time()
        if current_time - self._last_callback_time < 0.005:  # Minimum 5ms between callbacks
            return
        self._last_callback_time = current_time
        
        with self._lock:
            rms = np.sqrt(np.mean(indata**2))
            self._audio_buffer.append(indata.copy())
            
            # Prevent buffer from growing too large
            if len(self._audio_buffer) > self.max_buffer_size:
                # Remove oldest chunks if buffer gets too large
                excess_chunks = len(self._audio_buffer) - self.max_buffer_size + 25
                self._audio_buffer = self._audio_buffer[excess_chunks:]

            # Update adaptive noise floor
            if self.adaptive_noise_floor:
                # Balanced adaptation
                self.current_noise_floor = (
                    self.noise_floor_alpha * rms + 
                    (1 - self.noise_floor_alpha) * self.current_noise_floor
                )
                # Ensure noise floor doesn't go below minimum threshold
                self.current_noise_floor = max(self.current_noise_floor, 0.005)
                # Dynamic threshold based on noise floor
                effective_threshold = max(self.silence_threshold, self.current_noise_floor * 2.0)
            else:
                effective_threshold = self.silence_threshold

            # Speech detection logic
            if rms >= effective_threshold:
                self._silence_counter = 0
                self._speech_chunks += 1
                if not self._speech_detected and self._speech_chunks >= self.min_speech_chunks:
                    self._speech_detected = True
            else:
                self._silence_counter += 1
                # Reset speech counter if silence is detected early
                if not self._speech_detected:
                    self._speech_chunks = 0

            # Adjusted timing for the smaller chunk size
            chunk_duration = self.chunk_size
            silence_chunks_needed = int(self.silence_duration / chunk_duration)
            grace_chunks = int(self.post_wake_grace / chunk_duration)

            # Check if we have a complete audio segment ready
            if self._speech_detected:
                # Require both silence and minimum speech duration
                if (self._silence_counter >= silence_chunks_needed + grace_chunks and 
                    len(self._audio_buffer) > 5 and 
                    self._speech_chunks > self.min_speech_chunks):
                    # Save the completed audio segment
                    self._ready_audio_segments.append(self._audio_buffer.copy())
                    # Reset for next recording
                    self._audio_buffer = []
                    self._speech_detected = False
                    self._silence_counter = 0
                    self._speech_chunks = 0

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
            self._speech_chunks = 0
            self._recording = True

        info("Recording...")
        start_time = time.time()
        max_record_seconds = max_seconds if max_seconds is not None else self.max_record_seconds
        while self._recording and (time.time() - start_time) < max_record_seconds:
            time.sleep(0.05)
        
        self._recording = False

        with self._lock:
            if len(self._audio_buffer) < 5:
                error("Recording too short.")
                return None
            audio = np.concatenate(self._audio_buffer, axis=0).flatten()

        temp_path = tempfile.mktemp(suffix=".wav")
        sf.write(temp_path, audio, self.sample_rate)
        return temp_path

    def is_audio_ready(self) -> bool:
        """Check if audio is ready to be processed without blocking."""
        with self._lock:
            # Audio is ready if we have completed segments
            return len(self._ready_audio_segments) > 0

    def get_ready_audio(self) -> Optional[str]:
        """Get audio that's ready to be processed, if any."""
        with self._lock:
            if not self._ready_audio_segments:
                return None
            # Get the first completed audio segment
            audio_buffer = self._ready_audio_segments.pop(0)
            
        if len(audio_buffer) < 2:  # Minimum buffer size for valid audio
            return None
            
        # More efficient audio concatenation with error handling
        try:
            # Pre-allocate array for better performance
            total_frames = sum(len(chunk) for chunk in audio_buffer)
            audio = np.empty((total_frames, 1), dtype=np.float32)
            offset = 0
            for chunk in audio_buffer:
                audio[offset:offset+len(chunk)] = chunk
                offset += len(chunk)
            audio = audio.flatten()
        except (ValueError, TypeError):
            # Fallback method for incompatible shapes
            try:
                audio = np.concatenate(audio_buffer, axis=0).flatten()
            except:
                # Last resort method
                audio = np.vstack(audio_buffer).flatten()
        
        # Use a more efficient temporary file creation with context manager
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
            temp_path = tmp_file.name
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
