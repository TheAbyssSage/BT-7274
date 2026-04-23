"""
Text-to-Speech module using Coqui XTTS v2 for BT-7274 voice cloning.
"""

import os
import tempfile
from pathlib import Path
from typing import Optional

# Patch for PyTorch 2.6+ weights_only loading with XTTS
# XTTS model checkpoints were created before weights_only=True became default
import torch
_original_torch_load = torch.load
def _patched_torch_load(*args, **kwargs):
    kwargs.setdefault('weights_only', False)
    return _original_torch_load(*args, **kwargs)
torch.load = _patched_torch_load

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
        self._gpt_cond_latent = None
        self._speaker_embedding = None

    @property
    def model(self):
        """Lazy-load the XTTS v2 model."""
        if self._model is None:
            print(f"    Loading XTTS v2 model...")
            print("    (This may take 30-60 seconds on first run)")
            self._model = TTS(self.model_name)
            self._warmup()
        return self._model

    def _warmup(self):
        """Pre-compute speaker latents and do a dummy synthesis to warm up the model."""
        print("    Warming up TTS (caching speaker voice)...")
        try:
            # Cache speaker conditioning latents
            if hasattr(self._model.synthesizer.tts_model, "get_conditioning_latents"):
                self._gpt_cond_latent, self._speaker_embedding = \
                    self._model.synthesizer.tts_model.get_conditioning_latents(
                        audio_path=[self.reference_wav]
                    )
            # Dummy synthesis to warm up
            _ = self._model.tts(
                text="Ready.",
                speaker_wav=self.reference_wav,
                language=self.language
            )
            print("    ✓ TTS warmed up and ready.")
        except Exception as e:
            print(f"    ⚠ TTS warmup warning: {e}")

    def speak(self, text: str) -> Optional[str]:
        """Synthesize speech and return the output WAV path."""
        if not text or not text.strip():
            return None

        # Clean text for TTS
        text = text.strip()
        import re
        text = re.sub(r'```json.*?```', '', text, flags=re.DOTALL)
        text = re.sub(r'\{[^{}]*"action"[^{}]*\}', '', text)
        text = text.strip()

        if not text:
            return None

        # Truncate very long responses to avoid slow synthesis
        max_chars = 250
        if len(text) > max_chars:
            text = text[:max_chars].rsplit('.', 1)[0] + '.'

        output_path = self.output_dir / f"bt7274_{os.urandom(4).hex()}.wav"

        try:
            # Use the standard TTS API (cached latents path is unstable on some setups)
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
        self._gpt_cond_latent = None
        self._speaker_embedding = None
        import gc
        gc.collect()
