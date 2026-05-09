"""
Voice Telemetry for BT-7274.

Logs voice-related metadata:
- Wake-word detection events (trigger, confidence, latency)
- STT confidence per utterance
- Command classification (intent, action triggered)
- TTS metrics (generation time, cache hits)
- Audio energy / noise floor snapshots

Stores JSONL entries under logs/telemetry/voice/.
"""

import time
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from bt7274.bt7274_workstation.log_manager import get_telemetry_voice_dir, daily_jsonl_path, append_jsonl
from bt7274.bt7274_assistant.ui import info, error, status


class VoiceTelemetry:
    """Monitors and logs voice pipeline metrics."""

    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}
        self.enabled = self.config.get("enabled", True)
        self._log_dir = get_telemetry_voice_dir()
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._session_start = time.time()
        self._utterance_count = 0

    def log_wake_event(
        self,
        wake_word: str,
        confidence: Optional[float] = None,
        latency_ms: Optional[float] = None,
        audio_energy: Optional[float] = None,
        noise_floor: Optional[float] = None,
    ):
        """Log a wake-word detection event."""
        if not self.enabled:
            return
        entry = {
            "timestamp": datetime.now().isoformat(),
            "event": "wake_word",
            "wake_word": wake_word,
            "confidence": confidence,
            "latency_ms": latency_ms,
            "audio_energy": audio_energy,
            "noise_floor": noise_floor,
            "session_elapsed_seconds": round(time.time() - self._session_start, 3),
        }
        log_file = daily_jsonl_path(self._log_dir, "voice_telemetry")
        append_jsonl(log_file, entry)

    def log_stt_event(
        self,
        transcript: str,
        confidence: Optional[float] = None,
        model: Optional[str] = None,
        duration_seconds: Optional[float] = None,
        language: Optional[str] = None,
    ):
        """Log an STT transcription event."""
        if not self.enabled:
            return
        self._utterance_count += 1
        entry = {
            "timestamp": datetime.now().isoformat(),
            "event": "stt",
            "transcript": transcript,
            "confidence": confidence,
            "model": model,
            "duration_seconds": duration_seconds,
            "language": language,
            "utterance_index": self._utterance_count,
        }
        log_file = daily_jsonl_path(self._log_dir, "voice_telemetry")
        append_jsonl(log_file, entry)

    def log_intent_event(
        self,
        intent: str,
        confidence: Optional[float] = None,
        action_triggered: Optional[str] = None,
        fallback_to_llm: bool = False,
    ):
        """Log intent classification result."""
        if not self.enabled:
            return
        entry = {
            "timestamp": datetime.now().isoformat(),
            "event": "intent",
            "intent": intent,
            "confidence": confidence,
            "action_triggered": action_triggered,
            "fallback_to_llm": fallback_to_llm,
        }
        log_file = daily_jsonl_path(self._log_dir, "voice_telemetry")
        append_jsonl(log_file, entry)

    def log_tts_event(
        self,
        text: str,
        generation_time_ms: Optional[float] = None,
        cache_hit: bool = False,
        model: Optional[str] = None,
        streaming: bool = False,
    ):
        """Log a TTS synthesis event."""
        if not self.enabled:
            return
        entry = {
            "timestamp": datetime.now().isoformat(),
            "event": "tts",
            "text_length": len(text),
            "generation_time_ms": generation_time_ms,
            "cache_hit": cache_hit,
            "model": model,
            "streaming": streaming,
        }
        log_file = daily_jsonl_path(self._log_dir, "voice_telemetry")
        append_jsonl(log_file, entry)

    def log_pipeline_error(
        self,
        stage: str,
        error_type: str,
        message: str,
        context: Optional[dict] = None,
    ):
        """Log a voice pipeline error."""
        if not self.enabled:
            return
        entry = {
            "timestamp": datetime.now().isoformat(),
            "event": "error",
            "stage": stage,
            "error_type": error_type,
            "message": message,
            "context": context,
        }
        log_file = daily_jsonl_path(self._log_dir, "voice_telemetry")
        append_jsonl(log_file, entry)

    def get_status(self) -> dict:
        return {
            "enabled": self.enabled,
            "utterance_count": self._utterance_count,
            "session_elapsed_seconds": round(time.time() - self._session_start, 3),
        }
