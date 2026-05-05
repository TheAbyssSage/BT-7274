"""Real-time HUD window for BT-7274.

Displays the live camera feed with YOLO detection bounding boxes,
labels, and Titanfall-style HUD chrome.
"""
from __future__ import annotations

import logging
import tkinter as tk
from typing import Optional

from PIL import Image, ImageTk

from bt7274_perception.realtime_vision import RealtimeVision

log = logging.getLogger(__name__)


class RealtimeHudWindow:
    """tkinter window showing the real-time YOLO detection feed.

    Usage:
        win = RealtimeHudWindow(camera_device="0", width=1280, height=720)
        win.start()   # blocks until window is closed
    """

    def __init__(
        self,
        camera_device: str = "0",
        width: int = 1280,
        height: int = 720,
        *,
        fullscreen: bool = False,
        yolo_model: str | None = None,
        yolo_conf: float = 0.5,
        yolo_iou: float = 0.45,
        enable_yolo: bool = True,
        detection_interval: int = 1,
    ):
        self.width = width
        self.height = height
        self._fullscreen = fullscreen

        self._vision = RealtimeVision(
            camera_device=camera_device,
            width=width,
            height=height,
            yolo_model=yolo_model,
            yolo_conf=yolo_conf,
            yolo_iou=yolo_iou,
            enable_yolo=enable_yolo,
            detection_interval=detection_interval,
        )

        self._root: Optional[tk.Tk] = None
        self._canvas: Optional[tk.Canvas] = None
        self._canvas_img_id: Optional[int] = None
        self._photo_image: Optional[ImageTk.PhotoImage] = None
        self._preview_job: Optional[str] = None
        self._running = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Launch the window. Blocks until closed."""
        self._build_ui()
        self._running = True
        self._vision.start()
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
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self._root = tk.Tk()
        self._root.title("BT-7274 Optical Sensors — Real-Time Detection")
        self._root.configure(bg="black")
        self._root.protocol("WM_DELETE_WINDOW", self._on_close)

        if self._fullscreen:
            self._root.attributes("-fullscreen", True)
            self.width = self._root.winfo_screenwidth()
            self.height = self._root.winfo_screenheight()
        else:
            self._root.geometry(f"{self.width}x{self.height}")

        # Key bindings
        self._root.bind("<Escape>", lambda _e: self._on_close())
        self._root.bind("q", lambda _e: self._on_close())
        self._root.bind("<F11>", lambda _e: self._toggle_fullscreen())

        self._canvas = tk.Canvas(
            self._root, bg="black", highlightthickness=0,
        )
        self._canvas.pack(fill=tk.BOTH, expand=True)

    def _toggle_fullscreen(self) -> None:
        if self._root is None:
            return
        self._fullscreen = not self._fullscreen
        self._root.attributes("-fullscreen", self._fullscreen)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _on_close(self) -> None:
        self._running = False
        self._vision.stop()
        if self._preview_job and self._root:
            self._root.after_cancel(self._preview_job)
            self._preview_job = None
        if self._root:
            self._root.destroy()
            self._root = None

    # ------------------------------------------------------------------
    # Render loop
    # ------------------------------------------------------------------

    def _schedule_frame(self) -> None:
        if not self._running or self._root is None:
            return
        self._update_frame()
        self._preview_job = self._root.after(10, self._schedule_frame)

    def _update_frame(self) -> None:
        if self._canvas is None:
            return

        annotated = self._vision.get_annotated_frame()
        if annotated is None:
            return

        # Convert numpy array → PIL → ImageTk
        pil_img = Image.fromarray(annotated)

        # Resize to current canvas size if needed
        cw = self._canvas.winfo_width()
        ch = self._canvas.winfo_height()
        if cw > 1 and ch > 1 and (cw, ch) != pil_img.size:
            pil_img = pil_img.resize(
                (cw, ch), Image.Resampling.LANCZOS,
            )

        self._photo_image = ImageTk.PhotoImage(pil_img)

        if self._canvas_img_id is None:
            self._canvas_img_id = self._canvas.create_image(
                0, 0, anchor=tk.NW, image=self._photo_image,
            )
        else:
            self._canvas.itemconfig(
                self._canvas_img_id, image=self._photo_image,
            )
