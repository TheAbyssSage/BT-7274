"""Live camera stream using OpenCV for real-time video feed."""

import threading
from typing import Optional

import cv2
import numpy as np
from PIL import Image


class CameraStream:
    """
    Continuous camera capture using OpenCV VideoCapture.
    Provides a live frame buffer that can be read at any time.
    """

    def __init__(
        self,
        device: str = "0",
        width: int = 1280,
        height: int = 720,
        fps: int = 30,
    ):
        self.device = int(device)
        self.width = width
        self.height = height
        self.fps = fps

        self._cap: Optional[cv2.VideoCapture] = None
        self._latest_frame: Optional[np.ndarray] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def start(self):
        """Open the camera and start the capture thread."""
        cap = cv2.VideoCapture(self.device)
        if not cap.isOpened():
            raise RuntimeError(f"Cannot open camera device {self.device}")

        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        cap.set(cv2.CAP_PROP_FPS, self.fps)

        self._cap = cap
        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()

    def _capture_loop(self):
        """Background thread: continuously read frames from the camera."""
        while self._running and self._cap is not None:
            ret, frame = self._cap.read()
            if ret:
                # Convert BGR (OpenCV default) to RGB
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                with self._lock:
                    self._latest_frame = rgb

    def get_frame(self) -> Optional[Image.Image]:
        """
        Return the most recent frame as a PIL Image, or None if not available.
        """
        with self._lock:
            if self._latest_frame is None:
                return None
            # Make a copy so the caller doesn't hold the lock while processing
            arr = self._latest_frame.copy()
        return Image.fromarray(arr)

    def stop(self):
        """Stop the capture thread and release the camera."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
        return False
