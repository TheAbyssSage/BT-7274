"""
Text-to-Speech module using Coqui XTTS v2 for BT-7274 voice cloning.
"""

import os
import tempfile
from pathlib import Path
from typing import Optional

from TTS.api import TTS
import soundfile as sf


class XTTSClient:
    def __init__(self, config: dict):
        self.config = config
        self.model_name = config.get("model", "tts_models/multilingual/multi-dataset/xtts_v2")
        self.reference_wav = config.get("reference_wav", "dataset/reference_speaker.wav")
        self.language = config.get("language", "en")
        self.speed = config.get("speed", 1.0)
        self.output_dir = Path(config.get("output_dir", "outputs"))
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._model = None

    @property
    def model(self):
        """Lazy-load the XTTS v2 model."""
        if self._model is None:
            print(f"    Loading XTTS v2 model...")
            print("    (This may take 30-60 seconds on first run)")
            self._model = TTS(self.model_name)
        return self._model

    def speak(self, text: str) -> Optional[str]:
        """Synthesize speech and return the output WAV path."""
        if not text or not text.strip():
            return None

        # Clean text for TTS
        text = text.strip()
        # Remove action JSON blocks
        import re
        text = re.sub(r'```json.*?```', '', text, flags=re.DOTALL)
        text = re.sub(r'\{[^{}]*"action"[^{}]*\}', '', text)
        text = text.strip()

        if not text:
            return None

        # Generate output path
        output_path = self.output_dir / f"bt7274_{os.urandom(4).hex()}.wav"

        try:
            wav = self.model.tts(
                text=text,
                speaker_wav=self.reference_wav,
                language=self.language
            )
            sf.write(str(output_path), wav, 24000)
            return str(output_path)
        except Exception as e:
            print(f"    ✗ TTS error: {e}")
            return None

    def unload(self):
        """Free model from memory."""
        self._model = None
        import gc
        gc.collect()
