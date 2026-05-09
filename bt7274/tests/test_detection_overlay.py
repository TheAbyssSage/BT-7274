"""Tests for BT-7274 Detection Overlay renderer."""

import sys
from pathlib import Path

_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import numpy as np
import pytest
from PIL import Image

from bt7274.bt7274_perception.detection_overlay import DetectionOverlay
from bt7274.bt7274_perception.yolo_engine import Detection


class TestDetectionOverlay:
    def test_init(self):
        overlay = DetectionOverlay(width=640, height=480)
        assert overlay.width == 640
        assert overlay.height == 480

    def test_draw_returns_image_same_size(self):
        overlay = DetectionOverlay(width=320, height=240)
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        frame[:, :] = (40, 40, 40)

        detections = [
            Detection(label="person", confidence=0.92, x1=50, y1=30, x2=150, y2=200),
        ]

        result = overlay.draw(frame, detections)
        assert isinstance(result, np.ndarray)
        assert result.shape == (240, 320, 3)
        # Should not be identical to input (overlay was drawn)
        assert not np.array_equal(result, frame)

    def test_draw_empty_detections_adds_chrome(self):
        overlay = DetectionOverlay(width=320, height=240)
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        frame[:, :] = (40, 40, 40)

        result = overlay.draw(frame, [])
        assert isinstance(result, np.ndarray)
        assert result.shape == (240, 320, 3)

    def test_draw_with_pil_image_input(self):
        overlay = DetectionOverlay(width=320, height=240)
        frame_pil = Image.new("RGB", (320, 240), (40, 40, 40))

        detections = [
            Detection(label="cell phone", confidence=0.78, x1=200, y1=100, x2=260, y2=160),
        ]
        result = overlay.draw(frame_pil, detections)
        assert isinstance(result, np.ndarray)
        assert result.shape == (240, 320, 3)

    def test_draw_multiple_detections(self):
        overlay = DetectionOverlay(width=640, height=480)
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        frame[:, :] = (40, 40, 40)

        detections = [
            Detection(label="person", confidence=0.95, x1=100, y1=50, x2=200, y2=300),
            Detection(label="car", confidence=0.88, x1=300, y1=150, x2=500, y2=350),
            Detection(label="dog", confidence=0.72, x1=50, y1=300, x2=120, y2=400),
        ]
        result = overlay.draw(frame, detections)
        assert isinstance(result, np.ndarray)
        assert result.shape == (480, 640, 3)

    def test_detection_out_of_bounds_clamped(self):
        overlay = DetectionOverlay(width=320, height=240)
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        frame[:, :] = (40, 40, 40)

        detections = [
            Detection(label="person", confidence=0.9, x1=-10, y1=-10, x2=400, y2=300),
        ]
        result = overlay.draw(frame, detections)
        assert isinstance(result, np.ndarray)
        assert result.shape == (240, 320, 3)
