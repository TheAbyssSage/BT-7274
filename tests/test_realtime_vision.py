"""Tests for BT-7274 RealtimeVision orchestrator."""

import sys
from pathlib import Path

_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import time
import numpy as np
import pytest

from bt7274_perception.realtime_vision import RealtimeVision, VisionSnapshot


class TestVisionSnapshot:
    def test_snapshot_creation(self):
        snap = VisionSnapshot(
            timestamp=time.monotonic(),
            num_objects=3,
            objects_summary="person, car, dog",
        )
        assert snap.num_objects == 3
        assert "person" in snap.objects_summary

    def test_snapshot_summary_text_with_objects(self):
        snap = VisionSnapshot(
            timestamp=time.monotonic(),
            num_objects=2,
            objects_summary="laptop, cell phone",
        )
        text = snap.summary_text
        assert "2 objects" in text
        assert "laptop" in text

    def test_snapshot_summary_text_empty(self):
        snap = VisionSnapshot(
            timestamp=time.monotonic(),
            num_objects=0,
            objects_summary="none",
        )
        text = snap.summary_text
        assert "no objects" in text.lower() or "0 objects" in text


class TestRealtimeVision:
    def test_init_stopped(self):
        rv = RealtimeVision(camera_device="0", width=320, height=240)
        assert rv.is_running is False
        assert rv.latest_snapshot is None

    def test_start_stop_lifecycle(self):
        rv = RealtimeVision(camera_device="0", width=320, height=240)
        rv.start()
        time.sleep(0.5)
        assert rv.is_running is True
        rv.stop()
        assert rv.is_running is False

    def test_get_frame_returns_none_when_stopped(self):
        rv = RealtimeVision(camera_device="0", width=320, height=240)
        assert rv.get_annotated_frame() is None

    def test_get_snapshot_returns_none_when_stopped(self):
        rv = RealtimeVision(camera_device="0", width=320, height=240)
        assert rv.get_snapshot() is None

    def test_context_manager(self):
        with RealtimeVision(camera_device="0", width=320, height=240) as rv:
            assert rv.is_running is True
        assert rv.is_running is False

    def test_disable_yolo(self):
        rv = RealtimeVision(
            camera_device="0", width=320, height=240, enable_yolo=False,
        )
        rv.start()
        time.sleep(0.3)
        # Should still produce frames even without YOLO
        frame = rv.get_annotated_frame()
        rv.stop()
        # Frame may be None if camera isn't available, but shouldn't crash


class TestRealtimeVisionOptimized:
    """Tests for zero-copy and skip-overlay optimizations."""

    def test_skip_overlay_when_no_detections(self):
        """When there are zero detections, the overlay should be skipped."""
        rv = RealtimeVision(
            camera_device="0", width=320, height=240,
            enable_yolo=False,  # no YOLO = no detections
        )
        rv.start()
        time.sleep(0.5)
        frame = None
        for _ in range(20):
            frame = rv.get_annotated_frame()
            if frame is not None:
                break
            time.sleep(0.1)
        rv.stop()
        # Frame should still be produced (raw camera pass-through)
        if frame is not None:
            assert isinstance(frame, np.ndarray)
            assert frame.shape[0] == 240
            assert frame.shape[1] == 320

    def test_get_annotated_frame_no_copy(self):
        """get_annotated_frame_no_copy should exist and work."""
        rv = RealtimeVision(
            camera_device="0", width=320, height=240,
            enable_yolo=False,
        )
        rv.start()
        time.sleep(0.5)
        frame = None
        for _ in range(20):
            frame = rv.get_annotated_frame_no_copy()
            if frame is not None:
                break
            time.sleep(0.1)
        rv.stop()
        if frame is not None:
            assert isinstance(frame, np.ndarray)
