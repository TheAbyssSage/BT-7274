"""
BT-7274 Perception Module — Camera Vision System.

Gives BT-7274 "eyes" to observe the real world through the Pilot's camera.
Captures frames, analyzes scenes via vision-capable LLMs, and logs
observations to logs/vision/.
"""

from .camera import CameraCapture
from .vision_engine import VisionEngine
from .vision_logger import VisionLogger
from .perception_manager import PerceptionManager

__all__ = ["CameraCapture", "VisionEngine", "VisionLogger", "PerceptionManager"]
