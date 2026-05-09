"""
BT-7274 Camera Stream — clean, fast, no HUD.
"""

from __future__ import annotations

import logging
import time
import tkinter as tk
from collections import deque
from typing import Optional

import numpy as np
from PIL import Image, ImageTk

from bt7274.bt7274_hud.camera_stream import CameraStream

log = logging.getLogger(__name__)


class CameraWindow:
    """Bare-metal camera stream window.  No overlays, no state, max FPS."""

    def __init__(
        self,
        camera_device: str = "0",
        width: int = 1280,
        height: int = 720,
        *,
        fullscreen: bool = False,
    ):
        self._camera_device = camera_device
        self.width = width
        self.height = height
        self._fullscreen = fullscreen

        self._root: Optional[tk.Tk] = None
        self._canvas: Optional[tk.Canvas] = None
        self._canvas_img_id: Optional[int] = None
        self._photo_image: Optional[ImageTk.PhotoImage] = None

        # Enumerate available cameras
        self._available_devices = CameraStream.list_devices()
        if not self._available_devices:
            log.warning("No cameras detected; stream will fail to start")

        self._camera = CameraStream(device=camera_device, width=width, height=height)
        self._preview_job: Optional[str] = None
        self._running = False

        # FPS counter state
        self._frame_times: deque[float] = deque(maxlen=30)
        self._fps_text_id: Optional[int] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Launch the window.  Blocks until closed."""
        self._build_ui()
        self._running = True
        self._camera.start()
        self._schedule_frame()
        assert self._root is not None
        self._root.mainloop()

    def stop(self) -> None:
        """Signal the window to close."""
        if self._root:
            self._root.after(0, self._on_close)

    @property
    def is_open(self) -> bool:
        return self._root is not None

    # ------------------------------------------------------------------
    # Camera selection
    # ------------------------------------------------------------------

    def _cycle_camera(self) -> None:
        """Switch to the next available camera device (wraps around)."""
        if len(self._available_devices) <= 1:
            return
        current_idx = next(
            (i for i, d in enumerate(self._available_devices)
             if str(d["index"]) == self._camera_device),
            -1,
        )
        next_idx = (current_idx + 1) % len(self._available_devices)
        new_device = str(self._available_devices[next_idx]["index"])
        self._switch_camera(new_device)

    def _switch_camera(self, new_device: str) -> None:
        """Stop current stream, start new one on *new_device*."""
        if new_device == self._camera_device:
            return
        log.info("Switching camera: %s → %s", self._camera_device, new_device)
        self._camera_device = new_device
        self._camera.stop()
        self._camera = CameraStream(
            device=new_device, width=self.width, height=self.height
        )
        if self._running:
            self._camera.start()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self._root = tk.Tk()
        self._root.title("BT-7274 Camera")
        self._root.configure(bg="black")
        self._root.protocol("WM_DELETE_WINDOW", self._on_close)

        if self._fullscreen:
            self._root.attributes("-fullscreen", True)
            self.width = self._root.winfo_screenwidth()
            self.height = self._root.winfo_screenheight()
        else:
            self._root.geometry(f"{self.width}x{self.height}")

        self._root.bind("<Escape>", lambda _e: self._on_close())
        self._root.bind("q", lambda _e: self._on_close())
        self._root.bind("<F11>", lambda _e: self._toggle_fullscreen())

        # Camera cycling — Tab or C key
        self._root.bind("<Tab>", lambda _e: self._cycle_camera())
        self._root.bind("c", lambda _e: self._cycle_camera())
        self._root.bind("C", lambda _e: self._cycle_camera())

        self._canvas = tk.Canvas(self._root, bg="black", highlightthickness=0)
        self._canvas.pack(fill=tk.BOTH, expand=True)

        # Camera device label (top-left corner)
        device_name = "No camera"
        for d in self._available_devices:
            if str(d["index"]) == self._camera_device:
                device_name = d["name"]
                break
        self._canvas.create_text(
            10, 10,
            text=f"CAM: {device_name}",
            fill="#00ff88",
            font=("Courier", 10),
            anchor=tk.NW,
            tags=("camera_label",),
        )

    # ------------------------------------------------------------------
    # Fullscreen toggle
    # ------------------------------------------------------------------

    def _toggle_fullscreen(self) -> None:
        if self._root is None:
            return
        self._fullscreen = not self._fullscreen
        self._root.attributes("-fullscreen", self._fullscreen)
        if self._fullscreen:
            self.width = self._root.winfo_screenwidth()
            self.height = self._root.winfo_screenheight()
        else:
            self.width = 1280
            self.height = 720
            self._root.geometry(f"{self.width}x{self.height}")
        self._camera.stop()
        self._camera = CameraStream(device=self._camera_device, width=self.width, height=self.height)
        self._camera.start()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _on_close(self) -> None:
        self._running = False
        self._camera.stop()
        if self._preview_job and self._root:
            self._root.after_cancel(self._preview_job)
            self._preview_job = None
        if self._root:
            self._root.destroy()
            self._root = None

    # ------------------------------------------------------------------
    # Render loop — zero-copy, minimal latency
    # ------------------------------------------------------------------

    def _schedule_frame(self) -> None:
        """Schedule next frame for minimal queuing delay."""
        if not self._running or self._root is None:
            return
        self._update_frame()
        self._preview_job = self._root.after(1, self._schedule_frame)

    def _update_frame(self) -> None:
        """Grab latest frame and push to canvas with zero unnecessary copies."""
        try:
            arr = self._camera.get_frame_array()
            if arr is None:
                return

            h, w = arr.shape[:2]

            # Only convert to PIL if dimensions differ (avoid resize cost when matched)
            if (w, h) != (self.width, self.height):
                img = Image.fromarray(arr).resize(
                    (self.width, self.height), Image.Resampling.NEAREST
                )
            else:
                img = Image.fromarray(arr, mode="RGB")

            self._photo_image = ImageTk.PhotoImage(img)

            if self._canvas is not None:
                if self._canvas_img_id is None:
                    self._canvas_img_id = self._canvas.create_image(
                        self.width // 2, self.height // 2,
                        image=self._photo_image,
                        anchor=tk.CENTER,
                    )
                else:
                    self._canvas.itemconfig(self._canvas_img_id, image=self._photo_image)

            # FPS tracking
            now = time.monotonic()
            self._frame_times.append(now)

            # FPS counter overlay (bottom-right corner, small green text)
            if len(self._frame_times) >= 2 and self._canvas is not None:
                elapsed = self._frame_times[-1] - self._frame_times[0]
                fps = (len(self._frame_times) - 1) / elapsed if elapsed > 0 else 0
                fps_text = f"{fps:.0f} FPS"

                if self._fps_text_id is None:
                    self._fps_text_id = self._canvas.create_text(
                        self.width - 60, self.height - 20,
                        text=fps_text,
                        fill="#00ff88",
                        font=("Courier", 12, "bold"),
                        anchor=tk.SE,
                    )
                else:
                    self._canvas.itemconfig(self._fps_text_id, text=fps_text)

        except Exception:
            pass  # suppress transient frame errors


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    parser = argparse.ArgumentParser(description="BT-7274 Camera Stream")
    parser.add_argument("--camera", default="0", help="Camera index or URL")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--fullscreen", action="store_true")
    args = parser.parse_args()

    window = CameraWindow(
        camera_device=args.camera,
        width=args.width,
        height=args.height,
        fullscreen=args.fullscreen,
    )
    window.start()