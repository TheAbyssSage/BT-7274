"""Response helper methods: status clips, log clips, system status, BT+TTS playback."""

import threading
from pathlib import Path
from typing import Optional

from ui import status, clip_play, log_tts, warning
from utils import play_audio


class ResponseHelpersMixin:
    """Mixin for response helper methods."""

    def _get_status_response_clip(self) -> Optional[str]:
        """Get a BT-7274 original voice clip for status responses."""
        status_phrases = [
            "ready to proceed",
            "embark when ready",
            "please embark when ready",
            "get ready",
            "my systems are rebooting",
            "pilot my mapping systems have been restored",
            "still operational but unable to escape",
            "reinitializing critical systems",
            "standing by pilot climb onto my hand",
        ]
        import random
        # Try to find matching BT clips
        available_clips = []
        for phrase in status_phrases:
            key = self._normalize_phrase(phrase)
            if key in self.bt_clips:
                path = self.bt_clips[key]
                if Path(path).exists():
                    available_clips.append((phrase, path))

        if available_clips:
            phrase, path = random.choice(available_clips)
            clip_play(phrase, source="status")
            return path
        return None

    def _get_log_clip(self, action: str = "read") -> Optional[str]:
        """Get a pre-recorded voice clip for logging actions.
        
        Args:
            action: One of "read", "create", "delete"
            
        Returns:
            Path to the clip if found, None otherwise.
        """
        log_phrases = {
            "read": [
                "accessing logs",
                "retrieving data",
                "accessing database",
                "data retrieved",
            ],
            "create": [
                "data entry confirmed",
                "log updated",
                "entry confirmed",
                "data recorded",
            ],
            "delete": [
                "data purged",
                "logs cleared",
                "deletion confirmed",
                "data removed",
            ]
        }
        import random
        phrases = log_phrases.get(action, log_phrases["read"])
        available_clips = []
        for phrase in phrases:
            key = self._normalize_phrase(phrase)
            # Check standby clips first (these are generated BT voice clips)
            if key in self.standby_clips:
                path = self.standby_clips[key]
                if Path(path).exists():
                    available_clips.append((phrase, path))
            # Then check original BT clips
            elif key in self.bt_clips:
                path = self.bt_clips[key]
                if Path(path).exists():
                    available_clips.append((phrase, path))
        
        if available_clips:
            phrase, path = random.choice(available_clips)
            clip_play(phrase, source="log")
            return path
        return None

    def _get_system_status_summary(self) -> str:
        """Generate a TTS-friendly system status summary.
        
        Returns a concise status report about BT-7274's systems.
        """
        parts = []
        
        # TTS system status
        if self.tts:
            parts.append("Voice synthesis systems online.")
        else:
            parts.append("Voice synthesis systems offline.")
        
        # LLM status
        if self.llm:
            parts.append("Neural network operational.")
        else:
            parts.append("Neural network offline.")
        
        # Location status
        if self.location and self.location.location_str:
            parts.append(f"Navigation systems active. Current position: {self.location.location_str}.")
        else:
            parts.append("Navigation systems standby.")
        
        # VPN/Cloak status
        if self.vpn:
            vpn_state = self.vpn.get_status()
            if vpn_state.get("state") == "connected":
                parts.append("Cloak engaged. Network traffic obfuscated.")
            else:
                parts.append("Cloak disengaged.")
        
        # Weather monitor status
        if self.weather and self.weather.enabled:
            parts.append("Environmental monitoring active.")
        
        # Battery status (if available)
        try:
            if hasattr(self, 'battery') and self.battery:
                battery_level = self.battery.get_level()
                if battery_level is not None:
                    parts.append(f"Power reserves at {battery_level} percent.")
        except Exception:
            pass
        
        # Session info
        import time
        mission_time = time.time() - self.session_start_time
        hours = int(mission_time // 3600)
        minutes = int((mission_time % 3600) // 60)
        if hours > 0:
            parts.append(f"Mission elapsed time: {hours} hours {minutes} minutes.")
        else:
            parts.append(f"Mission elapsed time: {minutes} minutes.")
        
        return " ".join(parts)

    def _play_bt_clip_with_tts_followup(self, clip_search_text: str, tts_text: str) -> dict:
        """Play a BT original clip immediately, then follow up with TTS of the actual data.

        This provides the immersive BT-7274 voice experience while ensuring the pilot
        gets the actual information they requested.

        Returns a dict with playback info for logging:
            - clip_played: bool
            - clip_phrase: str | None
            - tts_synthesized: bool
            - tts_played: bool
        """
        import threading

        result = {
            "clip_played": False,
            "clip_phrase": None,
            "tts_synthesized": False,
            "tts_played": False,
        }

        # Find the best BT clip based on the response context
        clip_path = self._select_dynamic_clip(clip_search_text)

        if not clip_path or not Path(clip_path).exists():
            # No suitable clip found, just do TTS
            log_tts("No matching BT clip found, using TTS only...")
            wav = self.tts.speak(tts_text) if self.tts else None
            if wav:
                play_audio(wav)
                result["tts_synthesized"] = True
                result["tts_played"] = True
            return result

        # Determine clip phrase for logging
        clip_phrase = None
        for phrase, path in self.bt_clips.items():
            if path == clip_path:
                clip_phrase = phrase
                break

        if clip_phrase:
            clip_play(clip_phrase, source="BT-7274 original")
            result["clip_phrase"] = clip_phrase

        # Start TTS generation in background while the clip plays
        tts_result: list[Optional[str]] = [None]
        def generate_tts():
            try:
                if self.tts:
                    tts_result[0] = self.tts.speak(tts_text)
            except Exception as e:
                self._report_error("tts", "background_synthesis", e)

        tts_thread = threading.Thread(target=generate_tts)
        tts_thread.start()

        # Play the BT clip (blocking)
        try:
            play_audio(clip_path)
            result["clip_played"] = True
        except Exception as e:
            self._report_error("tts", "play_bt_clip", e, {"clip_path": clip_path})

        # Wait for background TTS to complete (with timeout)
        tts_thread.join(timeout=30)

        # Play the TTS follow-up
        if tts_result[0] and Path(tts_result[0]).exists():
            result["tts_synthesized"] = True
            log_tts("Playing synthesized follow-up...")
            try:
                play_audio(tts_result[0])
                result["tts_played"] = True
            except Exception as e:
                self._report_error("tts", "play_followup", e, {"tts_wav": tts_result[0]})
        else:
            warning("TTS follow-up not ready or failed.")

        return result

