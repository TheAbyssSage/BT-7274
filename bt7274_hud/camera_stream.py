"""
Live camera stream — BT-7274 Pilot HUD
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Upgrades over v1:
  • Auto-reconnect with exponential back-off when the device drops
  • Actual FPS telemetry exposed as ``fps_actual`` property
  • Format negotiation: tries MJPEG first (lower CPU), falls back to raw
  • Frame-drop counter for diagnostics / HUD status display
  • ``get_frame_array()`` fast-path skips the PIL conversion when the
    renderer wants a raw NumPy array (avoids one copy)
  • Context-manager support kept; ``__repr__`` added for debugging
"""

import logging
import math
import threading
import time
from collections import deque
from typing import Optional

import cv2
import numpy as np
from PIL import Image

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

try:
    _PREFERRED_FOURCC = cv2.VideoWriter_fourcc(*"MJPG")   # lower CPU on most webcams
except AttributeError:
    _PREFERRED_FOURCC = 0  # headless OpenCV; MJPEG not available


def _try_mjpeg(cap: cv2.VideoCapture) -> bool:
    """Attempt to switch capture to MJPEG; return True if accepted."""
    if _PREFERRED_FOURCC == 0:
        return False
    old = cap.get(cv2.CAP_PROP_FOURCC)
    cap.set(cv2.CAP_PROP_FOURCC, _PREFERRED_FOURCC)
    return math.isclose(cap.get(cv2.CAP_PROP_FOURCC), _PREFERRED_FOURCC, rel_tol=1e-3)


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

class CameraStream:
    """
    Continuous camera capture using OpenCV VideoCapture.

    Provides a live frame buffer readable at any time by the render loop.
    Thread-safe; designed for ≥30 FPS with minimal latency.

    Parameters
    ----------
    device:
        Camera index (as string) or a file/RTSP URL.
    width, height:
        Requested capture resolution (device may not honour exactly).
    fps:
        Requested capture frame-rate.
    reconnect:
        If *True*, automatically try to reopen the device after a failure.
    reconnect_delay_s:
        Base delay between reconnect attempts; doubles each attempt (max 8 s).
    """

    def __init__(
        self,
        device: str = "0",
        width: int = 1280,
        height: int = 720,
        fps: int = 30,
        *,
        reconnect: bool = True,
        reconnect_delay_s: float = 0.5,
    ):
        # Try to parse as integer index; keep as string/URL otherwise
        try:
            self._device: int | str = int(device)
        except ValueError:
            self._device = device

        self.width = width
        self.height = height
        self.fps = fps
        self._reconnect = reconnect
        self._reconnect_delay_s = reconnect_delay_s

        self._cap: Optional[cv2.VideoCapture] = None
        self._latest_frame: Optional[np.ndarray] = None   # RGB, HxWx3 uint8
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        # Telemetry
        self._frame_count = 0
        self._drop_count = 0
        self._ts_ring: deque[float] = deque(maxlen=30)   # timestamps of last 30 frames

    # ------------------------------------------------------------------
    # Public control
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Open the camera and begin the background capture thread."""
        self._running = True
        self._thread = threading.Thread(
            target=self._capture_loop,
            name="camera-capture",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """Gracefully halt capture and release the device."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        self._release_cap()

    # ------------------------------------------------------------------
    # Frame access
    # ------------------------------------------------------------------

    def get_frame(self) -> Optional[Image.Image]:
        """
        Return the most recent camera frame as a PIL Image (RGB).

        Returns *None* until the first frame is captured or while the
        camera is reconnecting.
        """
        arr = self.get_frame_array()
        return Image.fromarray(arr) if arr is not None else None

    def get_frame_array(self) -> Optional[np.ndarray]:
        """
        Return the most recent frame as an RGB uint8 NumPy array.

        Faster than ``get_frame()`` when the caller (e.g. the renderer)
        can work directly with arrays.
        """
        with self._lock:
            if self._latest_frame is None:
                return None
            return self._latest_frame.copy()

    # ------------------------------------------------------------------
    # Telemetry
    # ------------------------------------------------------------------

    @property
    def fps_actual(self) -> float:
        """Measured capture rate over the last 30 frames (0 if no data)."""
        with self._lock:
            ring = list(self._ts_ring)
        if len(ring) < 2:
            return 0.0
        elapsed = ring[-1] - ring[0]
        return (len(ring) - 1) / elapsed if elapsed > 0 else 0.0

    @property
    def frame_count(self) -> int:
        """Total frames captured since *start()*."""
        return self._frame_count

    @property
    def drop_count(self) -> int:
        """Frames the device reported as lost."""
        return self._drop_count

    @property
    def is_alive(self) -> bool:
        """True if the capture thread is running."""
        return self._thread is not None and self._thread.is_alive()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _open_cap(self) -> Optional[cv2.VideoCapture]:
        """Open and configure the capture device; return *None* on failure."""
        cap = cv2.VideoCapture(self._device)
        if not cap.isOpened():
            log.warning("CameraStream: cannot open device %s", self._device)
            cap.release()
            return None

        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        cap.set(cv2.CAP_PROP_FPS, self.fps)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)   # minimal internal buffer → low latency

        if _try_mjpeg(cap):
            log.debug("CameraStream: MJPEG encoding accepted by device")
        else:
            log.debug("CameraStream: device does not support MJPEG; using raw")

        return cap

    def _release_cap(self) -> None:
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None

    def _capture_loop(self) -> None:
        """
        Background thread: tight read loop.

        On read failure → attempts reconnect if enabled, otherwise exits.
        Only the most recent frame is kept; old frames are silently dropped.
        """
        delay = self._reconnect_delay_s
        while self._running:
            # ---- open / reopen ----
            if self._cap is None:
                cap = self._open_cap()
                if cap is None:
                    if self._reconnect:
                        log.warning("CameraStream: retrying in %.1f s …", delay)
                        time.sleep(delay)
                        delay = min(delay * 2, 8.0)
                        continue
                    else:
                        log.error("CameraStream: giving up (reconnect=False)")
                        break
                self._cap = cap
                delay = self._reconnect_delay_s   # reset back-off after success
                log.info("CameraStream: device %s opened", self._device)

            # ---- read ----
            ret, frame = self._cap.read()
            if not ret:
                log.warning("CameraStream: read failed — device lost?")
                self._drop_count += 1
                self._release_cap()
                if not self._reconnect:
                    break
                continue

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            now = time.monotonic()

            with self._lock:
                self._latest_frame = rgb
                self._ts_ring.append(now)
            self._frame_count += 1

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> "CameraStream":
        self.start()
        return self

    def __exit__(self, *_) -> bool:
        self.stop()
        return False

    def __repr__(self) -> str:
        return (
            f"<CameraStream device={self._device!r} "
            f"{self.width}x{self.height}@{self.fps} "
            f"fps_actual={self.fps_actual:.1f} "
            f"frames={self._frame_count} drops={self._drop_count} "
            f"alive={self.is_alive}>"
        )

    @staticmethod
    def list_devices(max_index: int = 8) -> list[dict]:
        """
        Probe camera indices 0..max_index-1 and return available devices.

        Returns:
            List of dicts with ``index`` (int) and ``name`` (str) keys.
            Returns empty list if no cameras found or OpenCV unavailable.
        """
        devices: list[dict] = []
        for idx in range(max_index):
            try:
                cap = cv2.VideoCapture(idx)
                if cap.isOpened():
                    # Try to get a backend-specific name; fall back to generic label
                    backend = cap.getBackendName() if hasattr(cap, 'getBackendName') else ""
                    name = f"Camera {idx}"
                    if backend:
                        name = f"Camera {idx} ({backend})"
                    devices.append({"index": idx, "name": name})
                    cap.release()
                else:
                    cap.release()
            except Exception:
                continue
        return devices