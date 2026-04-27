"""
Text-to-Speech module using Coqui XTTS v2 for BT-7274 voice cloning.
"""

import os
import tempfile
import time
from pathlib import Path
from typing import Optional, Dict
from functools import lru_cache
import hashlib

from ui import info, success, warning, error, cache_hit

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
from ui import info, success, warning, error, cache_hit


class XTTSClient:
    def __init__(self, config: dict):
        self.config = config
        self.model_name = config.get("model", "tts_models/multilingual/multi-dataset/xtts_v2")
        self.reference_wav = config.get("reference_wav", "bt7274_assistant/dataset/reference_speaker.wav")
        self.language = config.get("language", "en")
        self.speed = config.get("speed", 1.0)
        self.output_dir = Path(config.get("output_dir", "bt7274_assistant/outputs"))
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._model = None
        self._gpt_cond_latent = None
        self._speaker_embedding = None
        # Cache for generated responses to avoid re-synthesis
        self._response_cache: Dict[str, str] = {}
        # Maximum cache size
        self._max_cache_size = 50
        # Performance metrics (last synthesis)
        self._last_metrics: Dict[str, float | str | bool] = {}

    def get_metrics(self) -> dict:
        """Return performance metrics from the last synthesis."""
        return self._last_metrics.copy()

    def ensure_ready(self):
        """Ensure model is loaded and ready."""
        _ = self.model

    @property
    def model(self):
        """Lazy-load the XTTS v2 model."""
        if self._model is None:
            info("Loading XTTS v2 model...")
            info("(This may take 30-60 seconds on first run)")
            self._model = TTS(self.model_name)
            self._warmup()
        return self._model

    def _warmup(self):
        """Pre-compute speaker latents and do a dummy synthesis to warm up the model."""
        info("Warming up TTS (caching speaker voice)...")
        try:
            # Cache speaker conditioning latents
            if self._model and hasattr(self._model, 'synthesizer') and \
               self._model.synthesizer and hasattr(self._model.synthesizer, 'tts_model') and \
               self._model.synthesizer.tts_model and \
               hasattr(self._model.synthesizer.tts_model, "get_conditioning_latents"):
                self._gpt_cond_latent, self._speaker_embedding = \
                    self._model.synthesizer.tts_model.get_conditioning_latents(
                        audio_path=[self.reference_wav]
                    )
            # Dummy synthesis to warm up
            if self._model and hasattr(self._model, 'tts'):
                try:
                    _ = self._model.tts(
                        text="Ready.",
                        speaker_wav=self.reference_wav,
                        language=self.language
                    )
                except Exception as e:
                    warning(f"TTS warmup synthesis failed: {e}")
            success("TTS warmed up and ready.")
        except Exception as e:
            warning(f"TTS warmup warning: {e}")

    def _preprocess_text(self, text: str) -> str:
        """Preprocess text for better TTS pronunciation."""
        import re

        # Convert BT-7274 to spelled-out digits for correct pronunciation
        # BT-7274 -> BT seven two seven four (keep BT together, spell out digits)
        text = re.sub(r'BT[-\s]?7274', 'BT seven two seven four', text, flags=re.IGNORECASE)

        # Also handle standalone 7274 references
        text = re.sub(r'\b7274\b', 'seven two seven four', text)

        # Handle common abbreviations for better pronunciation
        text = re.sub(r'\bAPI\b', 'A P I', text)
        text = re.sub(r'\bURL\b', 'U R L', text)
        text = re.sub(r'\bHTTP\b', 'H T T P', text)
        text = re.sub(r'\bAI\b', 'A I', text)

        return text

    def _get_text_hash(self, text: str) -> str:
        """Generate a hash for caching purposes."""
        return hashlib.md5(text.encode('utf-8')).hexdigest()[:12]

    def _is_cache_valid(self, file_path: str) -> bool:
        """Check if cached file exists and is valid."""
        return bool(file_path and os.path.exists(file_path))

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

        # Preprocess for correct pronunciation
        text = self._preprocess_text(text)

        # Check cache first
        text_hash = self._get_text_hash(text)
        cache_key = f"tts_{text_hash}"
        if cache_key in self._response_cache:
            cached_path = self._response_cache[cache_key]
            if self._is_cache_valid(cached_path):
                cache_hit("Using cached TTS response")
                self._last_metrics = {
                    "processing_time": 0.0,
                    "real_time_factor": 0.0,
                    "audio_duration": 0.0,
                    "mode": "standard",
                    "cached": True,
                }
                return cached_path

        # Truncate very long responses to avoid slow synthesis
        # But preserve sentence boundaries for better listening experience
        max_chars = 600
        if len(text) > max_chars:
            # Try to truncate at sentence boundary
            truncated = text[:max_chars]
            last_sentence_end = truncated.rfind('.')
            if last_sentence_end > max_chars * 0.7:  # If we have a reasonably long sentence
                text = truncated[:last_sentence_end + 1]
            else:
                # If no good sentence boundary, just cut at max and add ellipsis
                text = truncated.rsplit('.', 1)[0] + '...'

        output_path = self.output_dir / f"bt7274_{text_hash}.wav"

        # If file already exists, use it
        if self._is_cache_valid(str(output_path)):
            cache_hit("Using existing TTS file")
            self._response_cache[cache_key] = str(output_path)
            # Maintain cache size
            if len(self._response_cache) > self._max_cache_size:
                # Remove oldest entries
                keys_to_remove = list(self._response_cache.keys())[:10]
                for key in keys_to_remove:
                    del self._response_cache[key]
            self._last_metrics = {
                "processing_time": 0.0,
                "real_time_factor": 0.0,
                "audio_duration": 0.0,
                "mode": "standard",
                "cached": True,
            }
            return str(output_path)

        try:
            start_time = time.time()
            # Use the standard TTS API (cached latents path is unstable on some setups)
            wav = self.model.tts(
                text=text,
                speaker_wav=self.reference_wav,
                language=self.language
            )
            synthesis_time = time.time() - start_time
            sf.write(str(output_path), wav, 24000)

            # Estimate audio duration for real-time factor (~24k samples/sec, mono)
            audio_duration = len(wav) / 24000.0 if hasattr(wav, '__len__') else 0.0
            rt_factor = audio_duration / synthesis_time if synthesis_time > 0 else 0.0

            self._last_metrics = {
                "processing_time": round(synthesis_time, 3),
                "real_time_factor": round(rt_factor, 3),
                "audio_duration": round(audio_duration, 3),
                "mode": "standard",
                "cached": False,
            }
            
            # Add to cache
            self._response_cache[cache_key] = str(output_path)
            # Maintain cache size
            if len(self._response_cache) > self._max_cache_size:
                # Remove oldest entries
                keys_to_remove = list(self._response_cache.keys())[:10]
                for key in keys_to_remove:
                    del self._response_cache[key]
            
            return str(output_path)
        except Exception as e:
            error(f"TTS error: {e}")
            # Log error for debugging
            import logging
            logging.error(f"TTS Synthesis Error: {e}", exc_info=True)
            self._last_metrics = {"error": str(e)}
            return None

    def unload(self):
        """Free model from memory."""
        self._model = None
        self._gpt_cond_latent = None
        self._speaker_embedding = None
        # Clear cache but keep the cache structure
        self._response_cache.clear()
        import gc
        gc.collect()
