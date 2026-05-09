"""Tests for BT-7274 TelemetryPanel."""

import sys
from pathlib import Path

_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import pytest
from bt7274.bt7274_hud.telemetry_panel import TelemetryPanel, TelemetrySnapshot


class TestTelemetrySnapshot:
    def test_defaults(self):
        snap = TelemetrySnapshot()
        assert snap.object_count == 0
        assert snap.fps == 0.0
        assert snap.camera_name == ""
        assert snap.system_status == "ONLINE"

    def test_summary_lines(self):
        snap = TelemetrySnapshot(
            object_count=3,
            objects_summary="person, car, dog",
            fps=28.5,
            camera_name="FaceTime HD Camera",
            system_status="ONLINE",
            detection_model="yolov8n.pt",
        )
        lines = snap.summary_lines
        assert len(lines) >= 4
        assert any("OBJECTS: 3" in line for line in lines)
        assert any("28.5" in line for line in lines)
        assert any("FaceTime" in line for line in lines)

    def test_summary_lines_no_camera(self):
        snap = TelemetrySnapshot(object_count=0, fps=0.0)
        lines = snap.summary_lines
        assert any("OBJECTS: 0" in line for line in lines)
        assert any("FPS: 0.0" in line for line in lines)


class TestTelemetryPanel:
    def test_initial_snapshot(self):
        panel = TelemetryPanel()
        snap = panel.snapshot()
        assert snap.object_count == 0
        assert snap.fps == 0.0

    def test_update_from_vision(self):
        panel = TelemetryPanel()
        panel.update_from_vision(
            object_count=5,
            objects_summary="person, chair, laptop, cup, phone",
        )
        snap = panel.snapshot()
        assert snap.object_count == 5
        assert "person" in snap.objects_summary

    def test_update_fps(self):
        panel = TelemetryPanel()
        panel.update_fps(30.0)
        snap = panel.snapshot()
        assert snap.fps == 30.0

    def test_update_camera_name(self):
        panel = TelemetryPanel()
        panel.update_camera_name("USB Camera #2")
        snap = panel.snapshot()
        assert snap.camera_name == "USB Camera #2"

    def test_update_system_status(self):
        panel = TelemetryPanel()
        panel.update_system_status("DEGRADED")
        snap = panel.snapshot()
        assert snap.system_status == "DEGRADED"

    def test_update_detection_model(self):
        panel = TelemetryPanel()
        panel.update_detection_model("yolov8s.pt")
        snap = panel.snapshot()
        assert snap.detection_model == "yolov8s.pt"

    def test_multiple_updates_accumulate(self):
        panel = TelemetryPanel()
        panel.update_from_vision(3, "a, b, c")
        panel.update_fps(25.0)
        panel.update_camera_name("Cam 1")
        snap = panel.snapshot()
        assert snap.object_count == 3
        assert snap.fps == 25.0
        assert snap.camera_name == "Cam 1"
