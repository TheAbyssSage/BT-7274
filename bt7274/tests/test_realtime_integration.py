"""Integration smoke tests for the real-time YOLO vision pipeline."""

import sys
from pathlib import Path

_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import time
import numpy as np
import pytest

from bt7274.bt7274_perception import (
    YoloEngine,
    DetectionOverlay,
    RealtimeVision,
)
from bt7274.bt7274_perception.yolo_engine import Detection


class TestPipelineIntegration:
    """End-to-end smoke tests for the vision pipeline."""

    def test_yolo_to_overlay_pipeline(self):
        """YOLO detections → overlay produces annotated frame."""
        yolo = YoloEngine(model_path="models/yolov8n.pt", conf_threshold=0.5)
        overlay = DetectionOverlay(width=640, height=480)

        # Create a fake dark frame
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        frame[:, :] = (30, 30, 40)

        detections = yolo.detect(frame)
        result = overlay.draw(frame, detections)
        assert isinstance(result, np.ndarray)
        assert result.shape == (480, 640, 3)

    def test_overlay_with_multiple_detection_types(self):
        """Overlay handles multiple object types simultaneously."""
        overlay = DetectionOverlay(width=640, height=480)
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        frame[:, :] = (40, 40, 40)

        detections = [
            Detection(label="person", confidence=0.9, x1=100, y1=50, x2=200, y2=300),
            Detection(label="laptop", confidence=0.85, x1=400, y1=200, x2=550, y2=350),
            Detection(label="car", confidence=0.78, x1=50, y1=100, x2=300, y2=250),
        ]

        result = overlay.draw(frame, detections)
        assert isinstance(result, np.ndarray)
        assert result.shape == (480, 640, 3)

    def test_realtime_vision_lifecycle(self):
        """RealtimeVision starts and stops cleanly."""
        rv = RealtimeVision(
            camera_device="0",
            width=320,
            height=240,
        )
        rv.start()
        time.sleep(0.5)
        assert rv.is_running is True

        # Should eventually produce a frame
        frame = None
        for _ in range(20):
            frame = rv.get_annotated_frame()
            if frame is not None:
                break
            time.sleep(0.1)

        rv.stop()
        assert rv.is_running is False

    def test_vision_snapshot_summary(self):
        """VisionSnapshot produces readable summary text."""
        from bt7274.bt7274_perception.realtime_vision import VisionSnapshot

        snap = VisionSnapshot(
            timestamp=time.monotonic(),
            num_objects=2,
            objects_summary="person, dog",
            detections=[
                Detection(label="person", confidence=0.9, x1=0, y1=0, x2=10, y2=10),
                Detection(label="dog", confidence=0.8, x1=0, y1=0, x2=10, y2=10),
            ],
        )
        text = snap.summary_text
        assert "2 objects" in text
        assert "person" in text
        assert "dog" in text

    def test_realtime_vision_no_yolo_mode(self):
        """RealtimeVision works with YOLO disabled (camera-only)."""
        rv = RealtimeVision(
            camera_device="0",
            width=320,
            height=240,
            enable_yolo=False,
        )
        rv.start()
        time.sleep(0.5)
        assert rv.is_running is True

        frame = None
        for _ in range(20):
            frame = rv.get_annotated_frame()
            if frame is not None:
                break
            time.sleep(0.1)

        rv.stop()
        assert rv.is_running is False

    def test_detection_throttling(self):
        """Detection interval > 1 doesn't crash."""
        rv = RealtimeVision(
            camera_device="0",
            width=320,
            height=240,
            detection_interval=3,
        )
        rv.start()
        time.sleep(0.5)
        assert rv.is_running is True
        rv.stop()
        assert rv.is_running is False
