"""
High-speed TTS using Piper Python API.
Piper synthesizes speech in <0.3s vs XTTS v2's 16s.
"""

import os
import re
import time
import hashlib
from pathlib import Path
from typing import Optional, Dict

import numpy as np
import soundfile as sf

from bt7274.bt7274_assistant.ui import info, success, warning, error, cache_hit
from bt7274.bt7274_workstation.session_cache_manager import get_tts_output_dir


class FastPiperTTS:
    """Ultra-fast TTS using Piper Python API for sub-second synthesis."""

    def __init__(self, config: dict):
        self.config = config
        self.model_path = config.get(
            "piper_model",
            "bt7274_assistant/piper_models/en_US-lessac-medium.onnx",
        )
        self.output_dir = Path(config.get("output_dir", str(get_tts_output_dir())))
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._response_cache: Dict[str, str] = {}
        self._max_cache_size = 100
        self._last_metrics: Dict[str, float | str | bool] = {}
        self._voice = None

        # Fix espeak-ng data path for Piper (it has a hardcoded build-machine path)
        self._espeak_data = config.get(
            "piper_espeak_data",
            "venv/lib/python3.11/site-packages/piper/espeak-ng-data",
        )
        if not os.path.isabs(self._espeak_data):
            self._espeak_data = str(Path(self._espeak_data).resolve())

        # Verify model exists
        if not os.path.exists(self.model_path):
            warning(f"Piper model not found at {self.model_path}")

    def _is_ready(self) -> bool:
        """Check if Piper is available."""
        return os.path.exists(self.model_path)

    def ensure_ready(self):
        """Load the Piper voice model (lazy, near-instant)."""
        if self._voice is not None:
            return
        if not self._is_ready():
            warning("Piper TTS not available — model missing")
            return
        try:
            import piper
            self._voice = piper.PiperVoice.load(
                self.model_path,
                espeak_data_dir=self._espeak_data,
            )
            info("Piper TTS ready (sub-millisecond startup)")
        except Exception as e:
            warning(f"Piper TTS failed to load: {e}")

    def get_metrics(self) -> dict:
        """Return performance metrics from the last synthesis."""
        return self._last_metrics.copy()

    def _get_text_hash(self, text: str) -> str:
        """Generate a hash for caching purposes."""
        return hashlib.md5(text.encode("utf-8")).hexdigest()[:12]

    def _preprocess_text(self, text: str) -> str:
        """Preprocess text for better TTS pronunciation."""
        text = re.sub(r"BT[-\s]?7274", "BT seven two seven four", text, flags=re.IGNORECASE)
        text = re.sub(r"\b7274\b", "seven two seven four", text)
        text = re.sub(r"\bAPI\b", "A P I", text)
        text = re.sub(r"\bURL\b", "U R L", text)
        text = re.sub(r"\bHTTP\b", "H T T P", text)
        text = re.sub(r"\bAI\b", "A I", text)
        return text

    def speak(self, text: str) -> Optional[str]:
        """Synthesize speech and return the output WAV path.

        Returns None if synthesis fails or Piper is unavailable.
        """
        if not text or not text.strip():
            return None

        if not self._is_ready():
            return None

        # Clean text
        text = text.strip()
        text = re.sub(r"```json.*?```", "", text, flags=re.DOTALL)
        text = re.sub(r'\{[^{}]*"action"[^{}]*\}', "", text)
        text = text.strip()

        if not text:
            return None

        # Preprocess for correct pronunciation
        text = self._preprocess_text(text)

        # Check cache
        text_hash = self._get_text_hash(text)
        cache_key = f"piper_{text_hash}"
        if cache_key in self._response_cache:
            cached_path = self._response_cache[cache_key]
            if cached_path and os.path.exists(cached_path):
                cache_hit("Using cached Piper response")
                self._last_metrics = {
                    "engine": "piper",
                    "cached": True,
                    "synthesis_time": 0.0,
                    "text_length": len(text),
                }
                return cached_path

        # Ensure voice is loaded
        if self._voice is None:
            self.ensure_ready()
        if self._voice is None:
            return None

        # Synthesize with Piper Python API
        start_time = time.time()
        output_path = str(self.output_dir / f"bt7274_piper_{text_hash}.wav")

        try:
            # Collect raw 16-bit PCM audio chunks
            audio_bytes = b"".join(
                chunk.audio_int16_bytes for chunk in self._voice.synthesize(text)
            )
            audio = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0

            # Write WAV file
            sf.write(output_path, audio, 22050)

            synthesis_time = time.time() - start_time

            # Cache the result
            self._response_cache[cache_key] = output_path
            if len(self._response_cache) > self._max_cache_size:
                keys = list(self._response_cache.keys())[:20]
                for k in keys:
                    old_path = self._response_cache.pop(k, None)
                    if old_path and os.path.exists(old_path):
                        try:
                            os.remove(old_path)
                        except Exception:
                            pass

            self._last_metrics = {
                "engine": "piper",
                "cached": False,
                "synthesis_time": synthesis_time,
                "text_length": len(text),
            }

            return output_path

        except Exception as e:
            error(f"Piper synthesis error: {e}")
            return None
