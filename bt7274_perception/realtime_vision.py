"""Real-time vision orchestrator for BT-7274 Perception.

Ties together CameraStream → YoloEngine → DetectionOverlay in a background
thread. Produces annotated frames and structured snapshots that the assistant
can query at any time.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np

from bt7274_hud.camera_stream import CameraStream
from bt7274_perception.yolo_engine import YoloEngine, Detection
from bt7274_perception.detection_overlay import DetectionOverlay

logger = logging.getLogger(__name__)


@dataclass
class VisionSnapshot:
    """A point-in-time summary of what BT-7274's optical sensors see.

    Thread-safe: populated under lock by the vision thread, read by the
    assistant thread.
    """
    timestamp: float = 0.0
    num_objects: int = 0
    objects_summary: str = ""
    detections: List[Detection] = field(default_factory=list)

    @property
    def summary_text(self) -> str:
        """A concise natural-language summary for the LLM/voice response."""
        if self.num_objects > 0:
            return (
                f"I detect {self.num_objects} objects: "
                f"{self.objects_summary}."
            )
        return "I detect no objects of interest."


class RealtimeVision:
    """Background vision pipeline: camera → YOLO → overlay.

    Usage:
        rv = RealtimeVision(camera_device="0", width=1280, height=720)
        rv.start()

        # From the render loop:
        frame = rv.get_annotated_frame()

        # From the assistant:
        snap = rv.get_snapshot()
        print(snap.summary_text)

        rv.stop()
    """

    def __init__(
        self,
        camera_device: str = "0",
        width: int = 1280,
        height: int = 720,
        *,
        yolo_model: str | None = None,
        yolo_conf: float = 0.5,
        yolo_iou: float = 0.45,
        enable_yolo: bool = True,
        detection_interval: int = 1,
    ):
        self.width = width
        self.height = height
        self._detection_interval = detection_interval

        # Subsystems
        self._camera = CameraStream(
            device=camera_device, width=width, height=height,
        )
        self._yolo: Optional[YoloEngine] = None
        if enable_yolo:
            self._yolo = YoloEngine(
                model_path=yolo_model,
                conf_threshold=yolo_conf,
                iou_threshold=yolo_iou,
            )
        self._overlay = DetectionOverlay(width=width, height=height)

        # Threading
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._lock = threading.Lock()

        # Latest outputs (thread-safe)
        self._annotated_frame: Optional[np.ndarray] = None
        self._snapshot: Optional[VisionSnapshot] = None

        # Frame counter for detection throttling
        self._frame_count: int = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def latest_snapshot(self) -> Optional[VisionSnapshot]:
        with self._lock:
            return self._snapshot

    def start(self) -> None:
        """Begin the background vision pipeline."""
        if self._running:
            return
        self._running = True
        self._camera.start()
        self._thread = threading.Thread(
            target=self._vision_loop,
            name="bt-realtime-vision",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            "RealtimeVision started (%dx%d)", self.width, self.height,
        )

    def stop(self) -> None:
        """Halt the vision pipeline and release resources."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        self._camera.stop()
        logger.info("RealtimeVision stopped")

    def get_annotated_frame(self) -> Optional[np.ndarray]:
        """Return the most recent annotated frame (with overlays drawn).

        Returns None if the pipeline hasn't produced a frame yet.
        """
        with self._lock:
            if self._annotated_frame is None:
                return None
            return self._annotated_frame.copy()

    def get_annotated_frame_no_copy(self) -> Optional[np.ndarray]:
        """Return the most recent annotated frame WITHOUT copying.

        WARNING: Do NOT mutate the returned array. The vision thread
        will overwrite it on the next loop iteration.
        """
        with self._lock:
            return self._annotated_frame

    def get_snapshot(self) -> Optional[VisionSnapshot]:
        """Return the most recent vision snapshot for assistant queries."""
        with self._lock:
            return self._snapshot

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> RealtimeVision:
        self.start()
        return self

    def __exit__(self, *args) -> None:
        self.stop()

    # ------------------------------------------------------------------
    # Vision loop
    # ------------------------------------------------------------------

    def _vision_loop(self) -> None:
        """Main loop: grab frame → detect → overlay → publish."""
        while self._running:
            # Grab raw frame (zero-copy — we finish before next capture)
            raw = self._camera.get_frame_array_no_copy()
            if raw is None:
                time.sleep(0.001)
                continue

            self._frame_count += 1

            # Run YOLO detection (throttled by detection_interval)
            detections: List[Detection] = []
            if (
                self._yolo is not None
                and self._frame_count % self._detection_interval == 0
            ):
                try:
                    detections = self._yolo.detect(raw)
                except Exception as exc:
                    logger.warning("YOLO detection error: %s", exc)

            # Draw overlay — skip PIL roundtrip when there's nothing to draw
            if detections:
                try:
                    annotated = self._overlay.draw(raw, detections)
                except Exception as exc:
                    logger.warning("Overlay drawing error: %s", exc)
                    annotated = raw
            else:
                # No detections — pass raw frame through with zero overhead.
                # Only draw the static HUD chrome (corner brackets, status bar)
                # once every 30 frames to avoid the PIL roundtrip on every frame.
                if self._frame_count % 30 == 0:
                    try:
                        annotated = self._overlay.draw(raw, [])
                    except Exception as exc:
                        logger.warning("Overlay drawing error: %s", exc)
                        annotated = raw
                else:
                    annotated = raw

            # Build snapshot
            snapshot = self._build_snapshot(detections)

            # Publish under lock
            with self._lock:
                self._annotated_frame = annotated
                self._snapshot = snapshot

    def _build_snapshot(
        self, detections: List[Detection],
    ) -> VisionSnapshot:
        """Build a VisionSnapshot from current detections."""
        if detections:
            obj_labels = [d.label for d in detections[:10]]
            objects_summary = ", ".join(obj_labels)
        else:
            objects_summary = "none"

        return VisionSnapshot(
            timestamp=time.monotonic(),
            num_objects=len(detections),
            objects_summary=objects_summary,
            detections=detections,
        )
