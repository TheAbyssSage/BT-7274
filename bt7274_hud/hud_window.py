"""
BT-7274 Camera Stream — clean, fast, no HUD.
"""

from __future__ import annotations

import logging
import tkinter as tk
from typing import Optional

from PIL import Image, ImageTk

from bt7274_hud.camera_stream import CameraStream

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

        self._camera = CameraStream(device=camera_device, width=width, height=height)
        self._preview_job: Optional[str] = None
        self._running = False

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

        self._canvas = tk.Canvas(self._root, bg="black", highlightthickness=0)
        self._canvas.pack(fill=tk.BOTH, expand=True)

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
    # Render loop — as fast as possible
    # ------------------------------------------------------------------

    def _schedule_frame(self) -> None:
        if not self._running or self._root is None:
            return
        self._update_frame()
        self._preview_job = self._root.after(1, self._schedule_frame)

    def _update_frame(self) -> None:
        try:
            frame = self._camera.get_frame()
            if frame is None:
                return

            if frame.size != (self.width, self.height):
                frame = frame.resize((self.width, self.height), Image.Resampling.LANCZOS)

            self._photo_image = ImageTk.PhotoImage(frame)

            if self._canvas is not None:
                if self._canvas_img_id is None:
                    self._canvas_img_id = self._canvas.create_image(
                        self.width // 2, self.height // 2,
                        image=self._photo_image,
                        anchor=tk.CENTER,
                    )
                else:
                    self._canvas.itemconfig(self._canvas_img_id, image=self._photo_image)

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