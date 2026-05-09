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

    def analyze_that(
        self,
        pilot_query: Optional[str] = None,
        include_web_lookup: bool = True,
    ) -> dict:
        """
        Tactical object analysis — detect, classify, and assess threat/relevance.

        Captures a frame and uses a specialized prompt to:
          - List all detected objects with labels
          - Assign threat level (none/low/medium/high/critical)
          - Assign relevance to Pilot's mission (none/low/medium/high)
          - Suggest web lookups for unknown or interesting objects

        Args:
            pilot_query: The Pilot's exact words that triggered the analysis.
            include_web_lookup: If True, the prompt asks for web lookup suggestions.

        Returns:
            Dict with keys:
                - success (bool)
                - description (str) — full tactical analysis
                - objects (list[dict]) — parsed object list with labels/threat/relevance
                - web_lookups (list[str]) — suggested search queries
                - image_path (str|None)
                - model (str)
                - response_time (float)
                - error (str|None)
                - log_file (str)
        """
        ANALYSIS_PROMPT = (
            "You are BT-7274, a Vanguard-class Titan. Analyze this image through your "
            "optical sensors and provide a TACTICAL OBJECT ANALYSIS.\n\n"
            "Respond in this EXACT format:\n"
            "SUMMARY: 1-2 sentence tactical overview of the scene.\n"
            "OBJECTS:\n"
            "- [label]: confidence=high/medium/low, threat=none/low/medium/high/critical, "
            "relevance=none/low/medium/high (brief reason)\n"
            "- [label]: ...\n"
        )
        if include_web_lookup:
            ANALYSIS_PROMPT += (
                "WEB_LOOKUPS: (suggested search queries for unknown/interesting objects, "
                "one per line, or 'none')\n"
            )
        ANALYSIS_PROMPT += (
            "\nThreat assessment guide:\n"
            "- none: harmless everyday object\n"
            "- low: could be mildly hazardous (stairs, hot surfaces)\n"
            "- medium: potential danger if mishandled (tools, vehicles)\n"
            "- high: immediate hazard (weapons, fire, unstable structures)\n"
            "- critical: life-threatening (explosives, active combatants)\n\n"
            "Relevance assessment guide:\n"
            "- none: background clutter\n"
            "- low: everyday item, no mission impact\n"
            "- medium: potentially useful or noteworthy\n"
            "- high: directly relevant to Pilot's safety or mission\n\n"
            "Be thorough. List ALL visible objects of interest. "
            "Address the user as 'Pilot' in the summary."
        )

        # 1. Capture
        image_path = self.camera.capture()
        if image_path is None:
            return {
                "success": False,
                "description": "",
                "objects": [],
                "web_lookups": [],
                "image_path": None,
                "model": self.engine.vision_model,
                "response_time": 0.0,
                "error": "Camera capture failed. Check camera permissions and ffmpeg.",
                "log_file": str(self.logger._current_log_file) if self.logger._current_log_file else "",
            }

        # 2. Analyze with tactical prompt
        analysis = self.engine.analyze(image_path, prompt=ANALYSIS_PROMPT, use_bt_personality=False)

        # 3. Parse structured output from the description
        objects = []
        web_lookups = []
        summary = ""

        if analysis["success"]:
            raw = analysis["description"]
            # Parse SUMMARY section
            import re
            summary_match = re.search(r'SUMMARY:\s*(.+?)(?:\n\n|\nOBJECTS:)', raw, re.DOTALL | re.IGNORECASE)
            if summary_match:
                summary = summary_match.group(1).strip()

            # Parse OBJECTS section
            objects_match = re.search(r'OBJECTS:\s*\n(.*?)(?:\n\n|\nWEB_LOOKUPS:|\Z)', raw, re.DOTALL | re.IGNORECASE)
            if objects_match:
                for line in objects_match.group(1).strip().split('\n'):
                    line = line.strip()
                    if not line or not line.startswith('-'):
                        continue
                    # Parse: "- [label]: confidence=X, threat=Y, relevance=Z (reason)"
                    obj_match = re.match(
                        r'-\s*\[?([^\]:]+?)\]?\s*:\s*'
                        r'confidence\s*=\s*(\w+)'
                        r'.*?threat\s*=\s*(\w+)'
                        r'.*?relevance\s*=\s*(\w+)'
                        r'(?:\s*\((.+?)\))?\s*$',
                        line, re.IGNORECASE
                    )
                    if obj_match:
                        objects.append({
                            "label": obj_match.group(1).strip(),
                            "confidence": obj_match.group(2).strip().lower(),
                            "threat": obj_match.group(3).strip().lower(),
                            "relevance": obj_match.group(4).strip().lower(),
                            "reason": obj_match.group(5).strip() if obj_match.group(5) else "",
                        })
                    else:
                        # Fallback: simpler parse
                        simple_match = re.match(r'-\s*\[?([^\]:]+?)\]?\s*:?\s*(.*)', line)
                        if simple_match:
                            label = simple_match.group(1).strip()
                            rest = simple_match.group(2).strip()
                            objects.append({
                                "label": label,
                                "confidence": "unknown",
                                "threat": "unknown",
                                "relevance": "unknown",
                                "reason": rest if rest else "",
                            })

            # Parse WEB_LOOKUPS section
            web_match = re.search(r'WEB_LOOKUPS:\s*\n(.*?)(?:\n\n|\Z)', raw, re.DOTALL | re.IGNORECASE)
            if web_match:
                for line in web_match.group(1).strip().split('\n'):
                    line = line.strip().lstrip('- ').strip()
                    if line and line.lower() != 'none':
                        web_lookups.append(line)

            # If parsing failed, use the raw description as summary
            if not summary:
                summary = raw

        # 4. Log with enhanced metadata
        log_result = self.logger.log_observation(
            description=analysis["description"],
            image_path=image_path,
            model=analysis["model"],
            response_time=analysis["response_time"],
            trigger="analyze_that",
            pilot_query=pilot_query,
            metadata={
                "success": analysis["success"],
                "error": analysis["error"],
                "object_count": len(objects),
                "objects": objects,
                "web_lookups": web_lookups,
                "analysis_type": "tactical_object_analysis",
            },
        )

        result = {
            "success": analysis["success"],
            "description": summary or analysis["description"],
            "objects": objects,
            "web_lookups": web_lookups,
            "image_path": log_result.get("archived_image_path") or image_path,
            "model": analysis["model"],
            "response_time": analysis["response_time"],
            "error": analysis["error"],
            "log_file": log_result.get("log_file", ""),
        }
        self._last_result = result
        return result

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
