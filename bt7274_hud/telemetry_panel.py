"""Telemetry data aggregator for BT-7274 HUD top-right panel.

Collects object counts, FPS, camera info, and system status into a
structured snapshot that the HUD renderer reads each frame.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class TelemetrySnapshot:
    """Point-in-time telemetry for the top-right HUD panel."""

    object_count: int = 0
    objects_summary: str = ""
    fps: float = 0.0
    camera_name: str = ""
    system_status: str = "ONLINE"
    detection_model: str = ""

    @property
    def summary_lines(self) -> List[str]:
        """Return formatted lines for display in the top-right box."""
        lines: List[str] = []
        lines.append(f"OBJECTS: {self.object_count}")
        if self.objects_summary:
            lines.append(f"  {self.objects_summary[:40]}")
        lines.append(f"FPS: {self.fps:.1f}")
        if self.camera_name:
            lines.append(f"CAM: {self.camera_name[:25]}")
        if self.detection_model:
            lines.append(f"MODEL: {self.detection_model}")
        lines.append(f"SYS: {self.system_status}")
        return lines


class TelemetryPanel:
    """Mutable collector for telemetry data.

    The vision thread calls ``update_from_vision()`` and the HUD render
    loop calls ``update_fps()``.  ``snapshot()`` returns a consistent
    read of all fields.
    """

    def __init__(self):
        self._object_count = 0
        self._objects_summary = ""
        self._fps = 0.0
        self._camera_name = ""
        self._system_status = "ONLINE"
        self._detection_model = ""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_from_vision(self, object_count: int, objects_summary: str) -> None:
        """Called by the vision thread when new detections are available."""
        self._object_count = object_count
        self._objects_summary = objects_summary

    def update_fps(self, fps: float) -> None:
        """Called by the HUD render loop each frame."""
        self._fps = fps

    def update_camera_name(self, name: str) -> None:
        """Set the active camera display name."""
        self._camera_name = name

    def update_system_status(self, status: str) -> None:
        """Set system status: ``"ONLINE"``, ``"DEGRADED"``, ``"OFFLINE"``."""
        self._system_status = status

    def update_detection_model(self, model: str) -> None:
        """Set the YOLO model name (e.g. ``"yolov8n.pt"``)."""
        self._detection_model = model

    def snapshot(self) -> TelemetrySnapshot:
        """Return a consistent read of all current telemetry values."""
        return TelemetrySnapshot(
            object_count=self._object_count,
            objects_summary=self._objects_summary,
            fps=self._fps,
            camera_name=self._camera_name,
            system_status=self._system_status,
            detection_model=self._detection_model,
        )
