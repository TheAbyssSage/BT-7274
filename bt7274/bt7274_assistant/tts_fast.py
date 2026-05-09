"""
High-Performance Streaming TTS for BT-7274.

Uses sentence-level streaming with parallel synthesis and playback
for near-instant voice responses while maintaining BT-7274's voice.

Architecture:
    LLM Stream → Sentence Buffer → Synthesis Queue → Audio Queue → Speaker
                      ↑                ↑                ↑
                   Thread 1        Thread 2        Thread 3
"""

import os
import re
import time
import queue
import threading
import hashlib
from pathlib import Path
from typing import Any, Optional, Callable, List, Dict
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import sounddevice as sd

from bt7274.bt7274_assistant.ui import info, success, warning, error, cache_hit, log_tts, loading_bar
import soundfile as sf

from bt7274.bt7274_workstation.session_cache_manager import (
    get_tts_output_dir,
    load_tts_cache_index,
    save_tts_cache_index,
    save_speaker_latents,
    load_speaker_latents,
)

# Patch for PyTorch 2.6+ weights_only loading with XTTS
import torch
_original_torch_load = torch.load
def _patched_torch_load(*args, **kwargs):
    kwargs.setdefault('weights_only', False)
    return _original_torch_load(*args, **kwargs)
torch.load = _patched_torch_load

from TTS.api import TTS


@dataclass
class AudioChunk:
    """Represents a chunk of audio ready for playback."""
    audio: np.ndarray
    sample_rate: int
    text: str
    is_final: bool = False


class StreamingXTTSClient:
    """
    High-performance streaming TTS that synthesizes and plays audio
    sentence-by-sentence for minimal latency.
    """

    def __init__(self, config: dict):
        self.config = config
        self.model_name = config.get("model", "tts_models/multilingual/multi-dataset/xtts_v2")
        self.language = config.get("language", "en")
        self.output_dir = Path(config.get("output_dir", str(get_tts_output_dir())))
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Resolve reference_wav: single file, list of files, or directory
        raw_ref = config.get("reference_wav", "bt7274_assistant/dataset/reference_speaker.wav")
        self.reference_wav = self._resolve_references(raw_ref)

        # Model state
        self._model: Any = None
        self._model_lock = threading.Lock()
        self._is_ready = False

        # Streaming state
        self._synthesis_queue = queue.Queue(maxsize=3)
        self._audio_queue = queue.Queue(maxsize=5)
        self._streaming = False
        self._threads: List[threading.Thread] = []

        # Cache for complete responses
        self._response_cache: Dict[str, str] = load_tts_cache_index()
        self._max_cache_size = 50
        self._cache_lock = threading.Lock()

        # Audio playback state
        self._current_audio = None
        self._playback_lock = threading.Lock()
        self._playback_stream = None

        # Performance metrics
        self._metrics = {
            'sentences_synthesized': 0,
            'sentences_played': 0,
            'total_synthesis_time': 0.0,
            'total_playback_time': 0.0,
        }

        # Last metrics for external retrieval
        self._last_metrics: Dict[str, float | str | bool] = {}

    def _resolve_references(self, raw_ref) -> list[str]:
        """Resolve reference_wav config to a list of WAV file paths.

        Supports:
          - Single file path (string)
          - List of file paths
          - Directory path (auto-discover *.wav files)
        """
        import glob

        if isinstance(raw_ref, list):
            refs = [str(Path(p).resolve()) for p in raw_ref if Path(p).exists()]
            if not refs:
                raise FileNotFoundError(f"None of the reference WAVs exist: {raw_ref}")
            return refs

        path = Path(raw_ref)
        if path.is_dir():
            wavs = sorted(path.glob("*.wav"))
            if not wavs:
                raise FileNotFoundError(f"No WAV files found in reference directory: {path}")
            refs = [str(p.resolve()) for p in wavs]
            info(f"Using {len(refs)} BT reference clips from directory: {path}")
            return refs

        if path.exists():
            return [str(path.resolve())]

        raise FileNotFoundError(f"Reference WAV not found: {path}")

    # ─── Model Management ────────────────────────────────────────────

    @property
    def model(self):
        """Thread-safe lazy model loading."""
        with self._model_lock:
            if self._model is None:
                loading_bar("Loading XTTS v2 model (performance mode)", 1, 3)
                from bt7274.bt7274_assistant.utils import suppress_stdout
                with suppress_stdout():
                    self._model = TTS(self.model_name)
                loading_bar("Loading XTTS v2 model (performance mode)", 2, 3)
                self._warmup()
                loading_bar("Loading XTTS v2 model (performance mode)", 3, 3)
                self._is_ready = True
            return self._model

    def _warmup(self):
        """Pre-compute speaker latents and do a dummy synthesis."""
        info("Warming up TTS (caching speaker voice)...")
        try:
            # Try to load cached speaker latents first (with reference validation)
            cached_latents, cached_embedding = load_speaker_latents(self.reference_wav)
            if cached_latents is not None and cached_embedding is not None:
                self._gpt_cond_latent = cached_latents
                self._speaker_embedding = cached_embedding
                info("Loaded cached speaker latents from session cache.")
            elif self._model and hasattr(self._model, 'synthesizer') and \
               self._model.synthesizer and hasattr(self._model.synthesizer, 'tts_model') and \
               self._model.synthesizer.tts_model and \
               hasattr(self._model.synthesizer.tts_model, "get_conditioning_latents"):
                self._gpt_cond_latent, self._speaker_embedding = \
                    self._model.synthesizer.tts_model.get_conditioning_latents(
                        audio_path=self.reference_wav
                    )
                save_speaker_latents(
                    self._gpt_cond_latent,
                    self._speaker_embedding,
                    reference_paths=self.reference_wav,
                )
            # Dummy synthesis to warm up
            if self._model and hasattr(self._model, 'tts'):
                try:
                    from bt7274.bt7274_assistant.utils import suppress_stdout
                    with suppress_stdout():
                        _ = self._model.tts(  # type: ignore[operator]
                            text="Ready.",
                            speaker_wav=self.reference_wav,  # type: ignore[arg-type]
                            language=self.language
                        )
                except Exception as e:
                    warning(f"TTS warmup synthesis failed: {e}")
            success("TTS warmed up and ready for streaming.")
        except Exception as e:
            warning(f"TTS warmup warning: {e}")

    def ensure_ready(self):
        """Ensure model is loaded and ready."""
        if not self._is_ready:
            _ = self.model

    # ─── Text Processing ─────────────────────────────────────────────

    def _preprocess_text(self, text: str) -> str:
        """Preprocess text for better TTS pronunciation."""
        # Convert BT-7274 to spelled-out digits
        text = re.sub(r'BT[-\s]?7274', 'BT seven two seven four', text, flags=re.IGNORECASE)
        text = re.sub(r'\b7274\b', 'seven two seven four', text)
        # Handle common abbreviations
        text = re.sub(r'\bAPI\b', 'A P I', text)
        text = re.sub(r'\bURL\b', 'U R L', text)
        text = re.sub(r'\bHTTP\b', 'H T T P', text)
        text = re.sub(r'\bAI\b', 'A I', text)
        return text

    def _clean_for_tts(self, text: str) -> str:
        """Clean text for TTS by removing markdown and JSON."""
        text = re.sub(r'```json.*?```', '', text, flags=re.DOTALL)
        text = re.sub(r'\{[^{}]*"action"[^{}]*\}', '', text)
        text = re.sub(r'#{1,6}\s+.*', '', text)
        text = re.sub(r'---+', '', text)
        text = re.sub(r'\*\*.*?\*\*', '', text)
        return text.strip()

    def _split_into_sentences(self, text: str) -> List[str]:
        """Split text into sentences for streaming synthesis."""
        # Clean first
        text = self._clean_for_tts(text)
        text = self._preprocess_text(text)

        if not text:
            return []

        # Split on sentence boundaries, keeping punctuation
        sentences = re.split(r'(?<=[.!?])\s+', text)

        # Filter empty and merge very short sentences
        result = []
        current = ""
        for s in sentences:
            s = s.strip()
            if not s:
                continue
            if len(s) < 20 and current:
                current += " " + s
            else:
                if current:
                    result.append(current)
                current = s
        if current:
            result.append(current)

        return result

    # ─── Synthesis ───────────────────────────────────────────────────

    def _synthesize_sentence(self, text: str) -> Optional[AudioChunk]:
        """Synthesize a single sentence into an AudioChunk."""
        if not text or not text.strip():
            return None

        # Check cache
        text_hash = self._get_text_hash(text)
        cache_key = f"tts_{text_hash}"

        with self._cache_lock:
            if cache_key in self._response_cache:
                cached_path = self._response_cache[cache_key]
                if cached_path and os.path.exists(cached_path):
                    try:
                        audio, sr = sf.read(cached_path)
                        return AudioChunk(audio=audio, sample_rate=sr, text=text)
                    except Exception:
                        pass

        try:
            start_time = time.time()

            # Use standard TTS API for reliable synthesis
            from bt7274.bt7274_assistant.utils import suppress_stdout
            with suppress_stdout():
                wav: Any = self.model.tts(  # type: ignore[operator]
                    text=text,
                    speaker_wav=self.reference_wav,  # type: ignore[arg-type]
                    language=self.language
                )

            # Convert to numpy if needed
            if wav is not None:
                try:
                    if hasattr(wav, 'cpu') and callable(getattr(wav, 'cpu', None)):
                        wav = wav.cpu().numpy()
                    if hasattr(wav, 'ndim') and wav.ndim > 1:
                        wav = wav.squeeze() if hasattr(wav, 'squeeze') and callable(getattr(wav, 'squeeze', None)) else wav
                    elif isinstance(wav, dict):
                        # Handle dict output - extract the waveform
                        if 'wav' in wav:
                            wav = wav['wav']
                        elif 'audio' in wav:
                            wav = wav['audio']
                        else:
                            error(f"Unexpected TTS output format: {type(wav)}")
                            return None
                except Exception as e:
                    warning(f"Audio conversion failed: {e}")
                    return None
            else:
                error("TTS synthesis returned None")
                return None

            synthesis_time = time.time() - start_time
            self._metrics['sentences_synthesized'] += 1
            self._metrics['total_synthesis_time'] += synthesis_time

            # Cache the result
            output_path = self.output_dir / f"bt7274_{text_hash}.wav"
            try:
                sf.write(str(output_path), wav, 24000)
            except Exception as e:
                warning(f"Failed to write audio file: {e}")
                return None

            with self._cache_lock:
                self._response_cache[cache_key] = str(output_path)
                # Maintain cache size
                if len(self._response_cache) > self._max_cache_size:
                    keys = list(self._response_cache.keys())[:10]
                    for k in keys:
                        cached_file = self._response_cache.pop(k, None)
                        if cached_file and os.path.exists(cached_file):
                            try:
                                os.remove(cached_file)
                            except Exception:
                                pass
                # Persist cache index
                save_tts_cache_index(self._response_cache)

            # Ensure wav is a numpy array before creating AudioChunk
            if isinstance(wav, (list, tuple)):
                wav = np.array(wav, dtype=np.float32)
            elif not isinstance(wav, np.ndarray):
                wav = np.array([wav] if wav is not None else [], dtype=np.float32)
                
            return AudioChunk(audio=wav, sample_rate=24000, text=text)

        except Exception as e:
            error(f"TTS synthesis error: {e}")
            import traceback
            traceback.print_exc()
            # Log error for debugging
            import logging
            logging.error(f"TTS Fast Synthesis Error: {e}", exc_info=True)
            return None

    def _get_text_hash(self, text: str) -> str:
        """Generate a hash for caching purposes."""
        return hashlib.md5(text.encode('utf-8')).hexdigest()[:12]

    # ─── Streaming Workers ───────────────────────────────────────────

    def _synthesis_worker(self):
        """Worker thread that synthesizes sentences from the queue."""
        while self._streaming:
            try:
                text = self._synthesis_queue.get(timeout=0.5)
                if text is None:  # Sentinel value
                    self._audio_queue.put(None)
                    break

                chunk = self._synthesize_sentence(text)
                if chunk:
                    self._audio_queue.put(chunk)
            except queue.Empty:
                continue
            except Exception as e:
                error(f"Synthesis worker error: {e}")

    def _playback_worker(self):
        """Worker thread that plays audio chunks as they become ready."""
        while self._streaming:
            try:
                chunk = self._audio_queue.get(timeout=0.5)
                if chunk is None:  # Sentinel value
                    break

                self._play_audio_chunk(chunk)
                self._metrics['sentences_played'] += 1

            except queue.Empty:
                continue
            except Exception as e:
                error(f"Playback worker error: {e}")

    def _play_audio_chunk(self, chunk: AudioChunk):
        """Play a single audio chunk using sounddevice."""
        try:
            start_time = time.time()

            with self._playback_lock:
                # Ensure audio is float32 and proper shape
                audio = np.asarray(chunk.audio, dtype=np.float32)
                if audio.ndim == 1:
                    audio = audio.reshape(-1, 1)

                # Normalize if needed
                max_val = np.max(np.abs(audio))
                if max_val > 1.0:
                    audio = audio / max_val

                # Play audio
                sd.play(audio, chunk.sample_rate)
                sd.wait()

            self._metrics['total_playback_time'] += time.time() - start_time

        except Exception as e:
            error(f"Audio playback error: {e}")

    # ─── Public API ──────────────────────────────────────────────────

    def speak_streaming(self, text: str) -> bool:
        """
        Synthesize and play text using streaming for minimal latency.
        Returns True if successful.
        """
        if not text or not text.strip():
            return False

        sentences = self._split_into_sentences(text)
        if not sentences:
            return False

        log_tts(f"Streaming TTS: {len(sentences)} sentence(s) to synthesize")

        # Start streaming workers
        self._streaming = True
        self._threads = []

        # Start synthesis worker
        synth_thread = threading.Thread(target=self._synthesis_worker, daemon=True)
        synth_thread.start()
        self._threads.append(synth_thread)

        # Start playback worker
        playback_thread = threading.Thread(target=self._playback_worker, daemon=True)
        playback_thread.start()
        self._threads.append(playback_thread)

        # Feed sentences to synthesis queue
        total_start = time.time()
        first_sentence_time = None

        for i, sentence in enumerate(sentences):
            # Wait if queue is full (backpressure)
            while self._synthesis_queue.qsize() >= 3 and self._streaming:
                time.sleep(0.05)

            if not self._streaming:
                break

            self._synthesis_queue.put(sentence)

            # Track time to first sentence synthesis
            if i == 0:
                # Wait for first audio chunk
                try:
                    first_chunk = self._audio_queue.get(timeout=30)
                    if first_chunk:
                        first_sentence_time = time.time() - total_start
                        info(f"First audio ready in {first_sentence_time:.2f}s")
                        # Put it back for playback worker
                        self._audio_queue.put(first_chunk)
                except queue.Empty:
                    error("Timeout waiting for first sentence")
                    self._streaming = False
                    break

        # Signal end of stream
        self._synthesis_queue.put(None)

        # Wait for workers to finish
        for t in self._threads:
            t.join(timeout=60)

        self._streaming = False

        total_time = time.time() - total_start
        success(f"Streaming complete in {total_time:.2f}s")
        info(f"Metrics: {self._metrics['sentences_synthesized']} synthesized, "
              f"{self._metrics['sentences_played']} played")

        # Store last metrics for external retrieval
        self._last_metrics = {
            "processing_time": round(total_time, 3),
            "sentences_synthesized": self._metrics['sentences_synthesized'],
            "sentences_played": self._metrics['sentences_played'],
            "total_synthesis_time": round(self._metrics['total_synthesis_time'], 3),
            "total_playback_time": round(self._metrics['total_playback_time'], 3),
            "mode": "streaming",
            "cached": False,
        }

        return True

    def speak(self, text: str) -> Optional[str]:
        """
        Legacy non-streaming synthesis for short responses.
        Returns the output WAV path.
        """
        if not text or not text.strip():
            return None

        text = self._clean_for_tts(text)
        text = self._preprocess_text(text)

        if not text:
            return None

        # Check cache
        text_hash = self._get_text_hash(text)
        cache_key = f"tts_{text_hash}"

        with self._cache_lock:
            if cache_key in self._response_cache:
                cached_path = self._response_cache[cache_key]
                if cached_path and os.path.exists(cached_path):
                    return cached_path

        # Truncate very long responses
        max_chars = 600
        if len(text) > max_chars:
            truncated = text[:max_chars]
            last_sentence_end = truncated.rfind('.')
            if last_sentence_end > max_chars * 0.7:
                text = truncated[:last_sentence_end + 1]
            else:
                text = truncated.rsplit('.', 1)[0] + '...'

        output_path = self.output_dir / f"bt7274_{text_hash}.wav"

        # If file already exists, use it
        if output_path.exists():
            with self._cache_lock:
                self._response_cache[cache_key] = str(output_path)
            return str(output_path)

        try:
            from bt7274.bt7274_assistant.utils import suppress_stdout
            with suppress_stdout():
                wav: Any = self.model.tts(  # type: ignore[operator]
                    text=text,
                    speaker_wav=self.reference_wav,  # type: ignore[arg-type]
                    language=self.language
                )
            sf.write(str(output_path), wav, 24000)

            with self._cache_lock:
                self._response_cache[cache_key] = str(output_path)
                if len(self._response_cache) > self._max_cache_size:
                    keys = list(self._response_cache.keys())[:10]
                    for k in keys:
                        del self._response_cache[k]

            return str(output_path)
        except Exception as e:
            error(f"TTS error: {e}")
            return None

    def unload(self):
        """Free model from memory and stop streaming."""
        self._streaming = False

        # Clear queues
        while not self._synthesis_queue.empty():
            try:
                self._synthesis_queue.get_nowait()
            except queue.Empty:
                break

        while not self._audio_queue.empty():
            try:
                self._audio_queue.get_nowait()
            except queue.Empty:
                break

        # Wait for threads
        for t in self._threads:
            if t.is_alive():
                t.join(timeout=2)

        self._threads = []

        # Clear model
        with self._model_lock:
            self._model: Any = None
            self._is_ready = False

        with self._cache_lock:
            self._response_cache.clear()

        import gc
        gc.collect()

    def get_metrics(self) -> dict:
        """Return performance metrics."""
        metrics = self._metrics.copy()
        if metrics['sentences_synthesized'] > 0:
            metrics['avg_synthesis_time'] = (
                metrics['total_synthesis_time'] / metrics['sentences_synthesized']
            )
        if metrics['sentences_played'] > 0:
            metrics['avg_playback_time'] = (
                metrics['total_playback_time'] / metrics['sentences_played']
            )
        return metrics
