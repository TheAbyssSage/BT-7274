"""
Speech-to-Text module using OpenAI Whisper.
"""

import os
import tempfile
from pathlib import Path
from typing import Optional

import whisper
import numpy as np
import soundfile as sf


class WhisperSTT:
    def __init__(self, config: dict):
        self.config = config
        self.model_name = config.get("model", "base.en")
        self.device = config.get("device", "cpu")
        self.language = config.get("language", "en")
        self._model = None

    @property
    def model(self):
        """Lazy-load the Whisper model."""
        if self._model is None:
            print(f"    Loading Whisper model '{self.model_name}' on {self.device}...")
            self._model = whisper.load_model(self.model_name).to(self.device)
        return self._model

    def transcribe(self, audio_path: str) -> dict:
        """Transcribe an audio file to text.
        
        Returns:
            dict with keys: text (str), confidence (float), language (str)
        """
        result = self.model.transcribe(
            audio_path,
            language=self.language,
            fp16=False  # M1 doesn't support fp16 well
        )
        text = result.get("text", "").strip()
        
        # Calculate confidence from segment probabilities
        segments = result.get("segments", [])
        if segments:
            avg_logprob = sum(s.get("avg_logprob", 0) for s in segments) / len(segments)
            # Convert logprob to approximate confidence (0-1 scale)
            confidence = min(1.0, max(0.0, 1.0 + avg_logprob))
        else:
            confidence = 0.0
        
        return {
            "text": text,
            "confidence": confidence,
            "language": result.get("language", self.language),
        }

    def transcribe_buffer(self, audio_buffer: np.ndarray, sample_rate: int = 16000) -> dict:
        """Transcribe from an in-memory audio buffer."""
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            sf.write(f.name, audio_buffer, sample_rate)
            result = self.transcribe(f.name)
            os.remove(f.name)
        return result

    def unload(self):
        """Free model from memory."""
        self._model = None
        import gc
        gc.collect()
