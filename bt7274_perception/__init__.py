"""
BT-7274 Perception Module — Camera Vision System.

Gives BT-7274 "eyes" to observe the real world through the Pilot's camera.
Supports snapshot-based vision (Ollama LLMs) and real-time detection
(Ultralytics YOLO + OpenCV).
"""

from .camera import CameraCapture
from .vision_engine import VisionEngine
from .vision_logger import VisionLogger
from .perception_manager import PerceptionManager
from .yolo_engine import YoloEngine, Detection
from .detection_overlay import DetectionOverlay
from .realtime_vision import RealtimeVision, VisionSnapshot

__all__ = [
    "CameraCapture",
    "VisionEngine",
    "VisionLogger",
    "PerceptionManager",
    "YoloEngine",
    "Detection",
    "DetectionOverlay",
    "RealtimeVision",
    "VisionSnapshot",
]
