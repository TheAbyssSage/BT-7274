# bt7274_perception/yolo_engine.py
"""Ultralytics YOLO real-time object detection engine."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List

import numpy as np

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Detection:
    """A single detected object."""
    label: str
    confidence: float
    x1: int
    y1: int
    x2: int
    y2: int

    @property
    def width(self) -> int:
        return self.x2 - self.x1

    @property
    def height(self) -> int:
        return self.y2 - self.y1

    @property
    def center(self) -> tuple[int, int]:
        return (self.x1 + self.width // 2, self.y1 + self.height // 2)


class YoloEngine:
    """Thin wrapper around Ultralytics YOLO for frame-by-frame inference."""

    DEFAULT_MODEL = "yolov8n.pt"
    DEFAULT_CONF = 0.5
    DEFAULT_IOU = 0.45

    def __init__(
        self,
        model_path: str | None = None,
        conf_threshold: float = DEFAULT_CONF,
        iou_threshold: float = DEFAULT_IOU,
        device: str | None = None,
    ):
        from ultralytics import YOLO

        self.conf_threshold = conf_threshold
        self.iou_threshold = iou_threshold
        self.device = device or self._auto_device()

        path = model_path or self.DEFAULT_MODEL
        if not Path(path).exists() and not str(path).endswith(".pt"):
            path = self.DEFAULT_MODEL

        logger.info("Loading YOLO model: %s on %s", path, self.device)
        self._model = YOLO(path)
        self._model.to(self.device)

    @staticmethod
    def _auto_device() -> str:
        import torch
        if torch.backends.mps.is_available():
            return "mps"
        if torch.cuda.is_available():
            return "cuda"
        return "cpu"

    def detect(self, frame: np.ndarray) -> List[Detection]:
        """Run inference on a single BGR or RGB numpy frame."""
        results = self._model.predict(
            source=frame,
            conf=self.conf_threshold,
            iou=self.iou_threshold,
            verbose=False,
            device=self.device,
        )
        return self._parse_results(results[0])

    @staticmethod
    def _parse_results(result) -> List[Detection]:
        detections: List[Detection] = []
        if result.boxes is None:
            return detections

        boxes = result.boxes.xyxy.cpu().numpy().astype(int)
        confs = result.boxes.conf.cpu().numpy()
        clses = result.boxes.cls.cpu().numpy().astype(int)
        names = result.names

        for (x1, y1, x2, y2), conf, cls_id in zip(boxes, confs, clses):
            detections.append(
                Detection(
                    label=names.get(cls_id, str(cls_id)),
                    confidence=float(conf),
                    x1=int(x1),
                    y1=int(y1),
                    x2=int(x2),
                    y2=int(y2),
                )
            )
        return detections
