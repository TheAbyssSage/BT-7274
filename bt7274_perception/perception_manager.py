"""
Perception Manager for BT-7274.

High-level orchestrator that ties CameraCapture, VisionEngine, and VisionLogger
together into a single "look" operation the assistant can invoke.
"""

import os
import tempfile
import time
from pathlib import Path
from typing import Optional

from .camera import CameraCapture
from .vision_engine import VisionEngine
from .vision_logger import VisionLogger


class PerceptionManager:
    """
    One-stop interface for BT-7274's visual perception.

    Usage:
        pm = PerceptionManager()
        result = pm.look(trigger="voice_command", pilot_query="What do you see?")
        print(result["description"])
    """

    def __init__(
        self,
        camera_device: str = "0",
        ollama_url: str = "http://localhost:11434",
        vision_model: str = "llava",
        log_dir: Optional[str] = None,
    ):
        self.camera = CameraCapture(device=camera_device)
        self.engine = VisionEngine(ollama_url=ollama_url, vision_model=vision_model)
        self.logger = VisionLogger(log_dir=log_dir)
        self._last_result: Optional[dict] = None

    def look(
        self,
        trigger: str = "manual",
        pilot_query: Optional[str] = None,
        custom_prompt: Optional[str] = None,
        save_image: bool = True,
    ) -> dict:
        """
        Capture a frame, analyze it, log it, and return the result.

        Args:
            trigger: What triggered the look (e.g. 'voice_command', 'auto_scan').
            pilot_query: The Pilot's exact words, if any.
            custom_prompt: Override the default vision prompt.
            save_image: If True, archive the captured image.

        Returns:
            Dict with keys:
                - success (bool)
                - description (str)
                - image_path (str|None)
                - model (str)
                - response_time (float)
                - error (str|None)
                - log_file (str)
        """
        # 1. Capture
        image_path = self.camera.capture()
        if image_path is None:
            return {
                "success": False,
                "description": "",
                "image_path": None,
                "model": self.engine.vision_model,
                "response_time": 0.0,
                "error": "Camera capture failed. Check camera permissions and ffmpeg.",
                "log_file": str(self.logger._current_log_file) if self.logger._current_log_file else "",
            }

        # 2. Analyze
        analysis = self.engine.analyze(image_path, prompt=custom_prompt)

        # 3. Log
        log_result = self.logger.log_observation(
            description=analysis["description"],
            image_path=image_path if save_image else None,
            model=analysis["model"],
            response_time=analysis["response_time"],
            trigger=trigger,
            pilot_query=pilot_query,
            metadata={"success": analysis["success"], "error": analysis["error"]},
        )

        # 4. Clean up temp image if not saving
        if not save_image:
            try:
                os.remove(image_path)
            except Exception:
                pass

        result = {
            "success": analysis["success"],
            "description": analysis["description"],
            "image_path": log_result.get("archived_image_path") or image_path,
            "model": analysis["model"],
            "response_time": analysis["response_time"],
            "error": analysis["error"],
            "log_file": log_result.get("log_file", ""),
        }
        self._last_result = result
        return result

    def look_quick(self, pilot_query: Optional[str] = None) -> str:
        """
        Quick look — returns just the description string.

        Returns:
            Description on success, error message on failure.
        """
        result = self.look(trigger="voice_command", pilot_query=pilot_query)
        if result["success"]:
            return result["description"]
        return f"Optical sensors offline, Pilot. {result['error']}"

    def get_last_description(self) -> str:
        """Return the description from the most recent look."""
        if self._last_result and self._last_result.get("success"):
            return self._last_result["description"]
        return "No recent visual data."

    def get_recent(self, count: int = 5) -> list[dict]:
        """Return recent observations from the log."""
        return self.logger.get_recent_observations(count=count)

    def get_today_summary(self) -> str:
        """Return a human-readable summary of today's observations."""
        return self.logger.get_today_summary()

    def is_ready(self) -> bool:
        """Check if the perception system is ready (camera + vision model)."""
        # Quick camera test
        test_path = self.camera.capture()
        camera_ok = test_path is not None
        if test_path:
            try:
                os.remove(test_path)
            except Exception:
                pass
        vision_ok = self.engine.is_vision_model_available()
        return camera_ok and vision_ok

    def status(self) -> dict:
        """Return detailed status of the perception subsystem."""
        return {
            "camera_ready": self.camera.capture() is not None,
            "vision_model_available": self.engine.is_vision_model_available(),
            "vision_model": self.engine.vision_model,
            "observations_today": self.logger.get_observation_count_today(),
            "last_description": self.get_last_description(),
        }
