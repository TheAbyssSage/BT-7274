"""
Interaction Logger for BT-7274 Voice Assistant.

Logs all exchanges between the Pilot and BT-7274 with timestamps,
storing them in daily JSONL files under the logs/bt-pilot_interactions/ directory.
"""

import json
import os
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional, Any


class InteractionLogger:
    """Logger for Pilot ↔ BT-7274 interactions."""

    def __init__(self, log_dir: Optional[str] = None):
        if log_dir is None:
            log_dir = str(Path(__file__).parent.parent / "logs" / "bt-pilot_interactions")
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.current_file = None
        self._update_current_file()
        # Deduplication: keep hashes of last 50 entries to prevent duplicates
        self._recent_hashes: set[str] = set()
        self._max_recent_hashes = 50

    def _get_entry_hash(self, pilot_message: str, bt_response: str) -> str:
        """Generate a hash for deduplication based on message content."""
        content = f"{pilot_message.strip().lower()}|{bt_response.strip().lower()}"
        return hashlib.md5(content.encode('utf-8')).hexdigest()[:16]

    def _is_duplicate(self, entry_hash: str) -> bool:
        """Check if this entry was recently logged (prevents duplicates)."""
        if entry_hash in self._recent_hashes:
            return True
        # Add to recent hashes
        self._recent_hashes.add(entry_hash)
        # Keep only the last N hashes to prevent memory bloat
        if len(self._recent_hashes) > self._max_recent_hashes:
            # Remove oldest entries (convert to list, slice, then back to set)
            self._recent_hashes = set(list(self._recent_hashes)[-self._max_recent_hashes:])
        return False

    def _update_current_file(self):
        """Update the current log file based on today's date."""
        today = datetime.now().strftime("%Y-%m-%d")
        self.current_file = self.log_dir / f"bt7274_interactions_{today}.jsonl"

    def log_interaction(
        self,
        pilot_message: str,
        bt_response: str,
        interaction_type: str = "voice",
        ai_mode: str = "local",
        performance_mode: str = "standard",
        tts_metrics: Optional[dict] = None,
        llm_response_time: Optional[float] = None,
        stt_confidence: Optional[float] = None,
        audio_file_path: Optional[str] = None,
        cache_hit: Optional[str] = None,
        token_usage: Optional[dict] = None,
        wake_word: Optional[str] = None,
        follow_up_depth: int = 0,
        session_id: Optional[str] = None,
        conversation_duration: Optional[float] = None,
        protocol_reference: str = "Protocol 1: Link to Pilot",
        pilot_trust_level: int = 1,
        mission_elapsed_time: Optional[float] = None,
        actions_executed: Optional[list] = None,
        errors: Optional[list] = None,
        location_context: Optional[str] = None,
        weather_context: Optional[str] = None,
        metadata: Optional[dict] = None,
    ):
        """Log a single interaction between Pilot and BT-7274."""
        self._update_current_file()

        # Deduplication check
        entry_hash = self._get_entry_hash(pilot_message, bt_response)
        if self._is_duplicate(entry_hash):
            return  # Skip duplicate entry

        now = datetime.now()
        entry: dict[str, Any] = {
            "timestamp": now.isoformat(),
            "date": now.strftime("%Y-%m-%d"),
            "time": now.strftime("%H:%M:%S"),
            "interaction_type": interaction_type,
            "ai_mode": ai_mode,
            "performance_mode": performance_mode,
            "pilot_message": pilot_message,
            "bt_response": bt_response,
        }

        if llm_response_time is not None:
            entry["llm_response_time"] = round(llm_response_time, 3)
        if stt_confidence is not None:
            entry["stt_confidence"] = round(stt_confidence, 4)
        if audio_file_path:
            entry["audio_file_path"] = audio_file_path
        if cache_hit:
            entry["cache_hit"] = cache_hit
        if token_usage:
            entry["token_usage"] = token_usage
        if wake_word:
            entry["wake_word"] = wake_word
        if follow_up_depth > 0:
            entry["follow_up_depth"] = follow_up_depth
        if session_id:
            entry["session_id"] = session_id
        if conversation_duration is not None:
            entry["conversation_duration"] = round(conversation_duration, 3)
        if protocol_reference:
            entry["protocol_reference"] = protocol_reference
        if pilot_trust_level > 0:
            entry["pilot_trust_level"] = pilot_trust_level
        if mission_elapsed_time is not None:
            entry["mission_elapsed_time"] = round(mission_elapsed_time, 3)
        if actions_executed:
            entry["actions_executed"] = actions_executed
        if errors:
            entry["errors"] = errors
        if location_context:
            entry["location_context"] = location_context
        if weather_context:
            entry["weather_context"] = weather_context
        if tts_metrics:
            entry["tts_metrics"] = tts_metrics
        if metadata:
            entry["metadata"] = metadata

        # Enhanced matching and personality logging
        if metadata is not None:
            if "match_type" in metadata:
                entry["match_type"] = metadata["match_type"]
            if "match_score" in metadata:
                entry["match_score"] = metadata["match_score"]
            if "personality_weights" in metadata:
                entry["personality_weights"] = metadata["personality_weights"]
            if "dialogue_state" in metadata:
                entry["dialogue_state"] = metadata["dialogue_state"]
            if "emotion_detected" in metadata:
                entry["emotion_detected"] = metadata["emotion_detected"]
            if "user_emotion" in metadata:
                entry["user_emotion"] = metadata["user_emotion"]
            if "context_topic" in metadata:
                entry["context_topic"] = metadata["context_topic"]
            if "clip_source" in metadata:
                entry["clip_source"] = metadata["clip_source"]
            if "clip_phrase" in metadata:
                entry["clip_phrase"] = metadata["clip_phrase"]
            if "tts_triggered" in metadata:
                entry["tts_triggered"] = metadata["tts_triggered"]
            if "bt_running" in metadata:
                entry["bt_running"] = metadata["bt_running"]

        if self.current_file is None:
            self._update_current_file()
        if self.current_file is None:
            return  # Cannot log without a valid file path

        with open(self.current_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        # Also log detailed per-interaction info to pilot_logs
        self._log_interaction_details(entry)

    def _log_interaction_details(self, entry: dict):
        """Log detailed interaction info to pilot_logs directory."""
        pilot_logs_dir = self.log_dir.parent / "pilot_logs"
        pilot_logs_dir.mkdir(parents=True, exist_ok=True)
        
        today = datetime.now().strftime("%Y-%m-%d")
        details_file = pilot_logs_dir / f"interaction_details_{today}.jsonl"
        
        with open(details_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def get_today_log(self) -> list:
        """Get all interactions from today."""
        self._update_current_file()
        if self.current_file is None or not self.current_file.exists():
            return []

        interactions = []
        with open(self.current_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    interactions.append(json.loads(line))
        return interactions

    def get_log_files(self) -> list:
        """Get all log files sorted by date (oldest first)."""
        return sorted(self.log_dir.glob("bt7274_interactions_*.jsonl"))

    def get_log_summary(self, days: int = 7) -> dict:
        """Get a summary of recent interactions."""
        files = self.get_log_files()
        recent_files = files[-days:] if len(files) > days else files

        total_interactions = 0
        for log_file in recent_files:
            with open(log_file, "r", encoding="utf-8") as f:
                total_interactions += sum(1 for _ in f if _.strip())

        return {
            "total_log_files": len(files),
            "recent_files_checked": len(recent_files),
            "total_interactions": total_interactions,
            "log_directory": str(self.log_dir),
        }
