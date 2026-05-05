"""Tkinter window orchestrator for the BT-7274 Pilot HUD."""

import sys
import threading
import tkinter as tk
from pathlib import Path
from typing import Optional

# Ensure project root on path
_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from PIL import Image, ImageTk

from bt7274_hud.hud_data import HudState
from bt7274_hud.hud_renderer import HudRenderer
from bt7274_hud.camera_stream import CameraStream


class PilotHudWindow:
    """
    Dedicated Titanfall 2 pilot HUD window.
    Fullscreen or fixed-size window with live camera feed + HUD overlays.
    Uses OpenCV for real-time video streaming.
    """

    DEFAULT_WIDTH = 1280
    DEFAULT_HEIGHT = 720
    PREVIEW_INTERVAL_MS = 33  # ~30 FPS for smooth live video

    def __init__(
        self,
        camera_device: str = "0",
        width: int = DEFAULT_WIDTH,
        height: int = DEFAULT_HEIGHT,
        fullscreen: bool = False,
    ):
        self._camera_device = camera_device
        self.width = width
        self.height = height
        self._fullscreen = fullscreen

        self._root: Optional[tk.Tk] = None
        self._canvas: Optional[tk.Canvas] = None
        self._canvas_image_id: Optional[int] = None
        self._photo_image: Optional[ImageTk.PhotoImage] = None

        self._camera = CameraStream(device=camera_device, width=width, height=height)
        self._renderer = HudRenderer(width=width, height=height)
        self._state = HudState()

        self._preview_job: Optional[str] = None
        self._running = False
        self._last_frame_path: Optional[str] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def state(self) -> HudState:
        """Mutable HUD state — update this and the next frame will reflect it."""
        return self._state

    def start(self):
        """Launch the HUD window (blocks until closed)."""
        self._build_ui()
        self._running = True
        self._schedule_frame()
        assert self._root is not None
        self._root.mainloop()

    def start_nonblocking(self):
        """Launch without blocking the caller."""
        self._build_ui()
        self._running = True
        self._schedule_frame()
        assert self._root is not None
        threading.Thread(target=self._root.mainloop, daemon=True).start()

    def is_open(self) -> bool:
        return self._root is not None

    def stop(self):
        """Signal the window to close."""
        if self._root:
            self._root.after(0, self._on_close)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        self._root = tk.Tk()
        self._root.title("BT-7274  |  PILOT HUD")
        if self._fullscreen:
            self._root.attributes("-fullscreen", True)
            self.width = self._root.winfo_screenwidth()
            self.height = self._root.winfo_screenheight()
            self._renderer = HudRenderer(width=self.width, height=self.height)
            self._camera = CameraStream(device=self._camera_device, width=self.width, height=self.height)
        else:
            self._root.geometry(f"{self.width}x{self.height}")

        self._root.configure(bg="black")
        self._root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Bind keys
        self._root.bind("<Escape>", lambda e: self._on_close())
        self._root.bind("<F11>", lambda e: self._toggle_fullscreen())
        self._root.bind("q", lambda e: self._on_close())

        # Canvas fills the window
        self._canvas = tk.Canvas(self._root, bg="black", highlightthickness=0)
        self._canvas.pack(fill=tk.BOTH, expand=True)

        # Start the live camera stream
        self._camera.start()

    def _toggle_fullscreen(self):
        if self._root is None:
            return
        self._fullscreen = not self._fullscreen
        self._root.attributes("-fullscreen", self._fullscreen)
        # Restart camera with new resolution
        self._camera.stop()
        if self._fullscreen:
            self.width = self._root.winfo_screenwidth()
            self.height = self._root.winfo_screenheight()
        else:
            self.width = self.DEFAULT_WIDTH
            self.height = self.DEFAULT_HEIGHT
        self._renderer = HudRenderer(width=self.width, height=self.height)
        self._camera = CameraStream(device=self._camera_device, width=self.width, height=self.height)
        self._camera.start()

    # ------------------------------------------------------------------
    # Frame loop
    # ------------------------------------------------------------------

    def _schedule_frame(self):
        if not self._running or self._root is None:
            return
        self._update_frame()
        self._preview_job = self._root.after(self.PREVIEW_INTERVAL_MS, self._schedule_frame)

    def _update_frame(self):
        """Get latest frame from live stream, render HUD, and update canvas."""
        try:
            bg = self._camera.get_frame()
            if bg is None:
                return

            # Resize to match renderer if needed
            if bg.size != (self.width, self.height):
                bg = bg.resize((self.width, self.height), Image.Resampling.LANCZOS)

            # Composite HUD
            composited = self._renderer.composite(bg, self._state)

            # Convert to tkinter
            self._photo_image = ImageTk.PhotoImage(composited)

            # Update canvas
            if self._canvas is not None:
                if self._canvas_image_id is None:
                    self._canvas_image_id = self._canvas.create_image(
                        self.width // 2, self.height // 2, image=self._photo_image, anchor=tk.CENTER
                    )
                else:
                    self._canvas.itemconfig(self._canvas_image_id, image=self._photo_image)

        except Exception:
            # Swallow frame errors to keep loop alive
            pass

    def _on_close(self):
        self._running = False
        self._camera.stop()
        if self._preview_job and self._root:
            self._root.after_cancel(self._preview_job)
            self._preview_job = None
        if self._root:
            self._root.destroy()
            self._root = None
