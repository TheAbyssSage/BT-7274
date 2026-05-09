"""Real-time HUD window for BT-7274.

Displays the live camera feed with YOLO detection bounding boxes,
labels, and Titanfall-style HUD chrome.
"""
from __future__ import annotations

import logging
import time
import tkinter as tk
from collections import deque
from typing import Optional

from PIL import Image, ImageTk

from bt7274.bt7274_perception.realtime_vision import RealtimeVision
from bt7274.bt7274_hud.terminal_log import TerminalLogBuffer
from bt7274.bt7274_hud.notification_stack import NotificationStack
from bt7274.bt7274_hud.telemetry_panel import TelemetryPanel

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

        # FPS counter
        self._frame_times: deque[float] = deque(maxlen=30)
        self._fps_text_id: Optional[int] = None

        # HUD UI box data sources
        self.terminal_log = TerminalLogBuffer(max_lines=200)
        self.notification_stack = NotificationStack(max_visible=6)
        self.telemetry_panel = TelemetryPanel()

        # Camera device list for switching
        from bt7274.bt7274_hud.camera_stream import CameraStream
        self._available_devices = CameraStream.list_devices()
        self._current_camera = camera_device

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
        self._root.bind("<Tab>", lambda _e: self._cycle_camera())
        self._root.bind("c", lambda _e: self._cycle_camera())
        self._root.bind("C", lambda _e: self._cycle_camera())

        self._canvas = tk.Canvas(
            self._root, bg="black", highlightthickness=0,
        )
        self._canvas.pack(fill=tk.BOTH, expand=True)

        # Camera device label (top-left corner)
        device_name = "No camera"
        for d in self._available_devices:
            if str(d["index"]) == str(self._current_camera):
                device_name = d["name"]
                break
        self._canvas.create_text(
            10, 10,
            text=f"CAM: {device_name}",
            fill="#00dcb4",
            font=("Courier", 10),
            anchor=tk.NW,
            tags=("camera_label",),
        )

    def _cycle_camera(self) -> None:
        """Switch to the next available camera device (wraps around)."""
        if len(self._available_devices) <= 1:
            return
        current_idx = next(
            (i for i, d in enumerate(self._available_devices)
             if str(d["index"]) == str(self._current_camera)),
            -1,
        )
        next_idx = (current_idx + 1) % len(self._available_devices)
        new_device = str(self._available_devices[next_idx]["index"])
        new_name = self._available_devices[next_idx]["name"]
        log.info("Switching camera: %s → %s (%s)",
                 self._current_camera, new_device, new_name)
        self._current_camera = new_device
        self._vision._camera.switch_device(new_device)
        # Update the on-screen label
        if self._canvas:
            self._canvas.delete("camera_label")
            self._canvas.create_text(
                10, 10,
                text=f"CAM: {new_name}",
                fill="#00dcb4",
                font=("Courier", 10),
                anchor=tk.NW,
                tags=("camera_label",),
            )

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
    # HUD UI Box drawing
    # ------------------------------------------------------------------

    def _draw_terminal_box(self) -> None:
        """Draw the bottom-left terminal output box.

        Shows the most recent 8 lines from ``terminal_log`` in a
        semi-transparent dark panel with cyan-tinted text.
        """
        if self._canvas is None:
            return

        tag = "terminal_box"
        self._canvas.delete(tag)

        cw = self._canvas.winfo_width()
        ch = self._canvas.winfo_height()
        if cw < 10 or ch < 10:
            return

        # Box geometry — anchored bottom-left
        box_w = min(520, cw // 2)
        box_h = min(160, ch // 4)
        pad = 10
        x0 = pad
        y0 = ch - box_h - pad
        x1 = x0 + box_w
        y1 = ch - pad

        # Background — dark semi-transparent
        self._canvas.create_rectangle(
            x0, y0, x1, y1,
            fill="#050f1e", outline="#00c8a0", width=1,
            tags=(tag,),
        )
        # Header label
        self._canvas.create_text(
            x0 + 8, y0 + 4,
            text="TERMINAL",
            fill="#00c8a0",
            font=("Courier", 9, "bold"),
            anchor=tk.NW,
            tags=(tag,),
        )

        # Log lines
        lines = self.terminal_log.get_visible(8)
        line_h = 14
        start_y = y0 + 20
        for i, log_line in enumerate(lines):
            display = log_line.text[:70]
            # Colour by level
            level_colors = {
                "SUCCESS": "#00dcb4",
                "WARN":    "#ffbe28",
                "ERROR":   "#ff3c3c",
                "INFO":    "#c8f0ff",
            }
            color = level_colors.get(log_line.level, "#c8f0ff")
            self._canvas.create_text(
                x0 + 10, start_y + i * line_h,
                text=display,
                fill=color,
                font=("Courier", 9),
                anchor=tk.NW,
                tags=(tag,),
            )

    def _draw_notification_box(self) -> None:
        """Draw the bottom-right notification stack.

        Notifications appear at the bottom and push older ones upward.
        Each fades out in its final second.  Max 6 visible.
        """
        if self._canvas is None:
            return

        tag = "notification_box"
        self._canvas.delete(tag)

        cw = self._canvas.winfo_width()
        ch = self._canvas.winfo_height()
        if cw < 10 or ch < 10:
            return

        # Box geometry — anchored bottom-right
        box_w = min(300, cw // 3)
        box_h = min(140, ch // 4)
        pad = 10
        x0 = cw - box_w - pad
        y0 = ch - box_h - pad
        x1 = cw - pad
        y1 = ch - pad

        # Background
        self._canvas.create_rectangle(
            x0, y0, x1, y1,
            fill="#050f1e", outline="#00c8a0", width=1,
            tags=(tag,),
        )
        # Header
        self._canvas.create_text(
            x0 + 8, y0 + 4,
            text="SYS LOG",
            fill="#00c8a0",
            font=("Courier", 9, "bold"),
            anchor=tk.NW,
            tags=(tag,),
        )

        # Notifications — draw bottom-up so newest is at the bottom
        visible = self.notification_stack.get_visible()
        line_h = 15
        # Start from the bottom of the box and go up
        base_y = y1 - 8
        for i, note in enumerate(reversed(visible)):
            y = base_y - i * line_h
            if y < y0 + 18:
                break  # don't draw above the header

            # Colour by category
            cat_colors = {
                "SYS":  "#c8f0ff",
                "OK":   "#00dcb4",
                "WARN": "#ffbe28",
                "ERR":  "#ff3c3c",
            }
            color = cat_colors.get(note.category, "#c8f0ff")

            # Apply alpha by dimming the colour
            alpha = note.alpha
            if alpha < 1.0:
                color = self._fade_color(color, alpha)

            display = note.text[:45]
            self._canvas.create_text(
                x0 + 10, y,
                text=display,
                fill=color,
                font=("Courier", 9),
                anchor=tk.SW,
                tags=(tag,),
            )

    @staticmethod
    def _fade_color(hex_color: str, alpha: float) -> str:
        """Dim a hex colour toward #050f1e by *alpha* factor."""
        if alpha >= 1.0:
            return hex_color
        hex_color = hex_color.lstrip("#")
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        # Interpolate toward the panel background #050f1e
        bg_r, bg_g, bg_b = 5, 15, 30
        r = int(bg_r + (r - bg_r) * alpha)
        g = int(bg_g + (g - bg_g) * alpha)
        b = int(bg_b + (b - bg_b) * alpha)
        return f"#{r:02x}{g:02x}{b:02x}"

    def _draw_telemetry_box(self) -> None:
        """Draw the top-right telemetry panel.

        Shows object count, FPS, camera name, detection model, and system
        status in a compact panel.
        """
        if self._canvas is None:
            return

        tag = "telemetry_box"
        self._canvas.delete(tag)

        cw = self._canvas.winfo_width()
        if cw < 10:
            return

        snap = self.telemetry_panel.snapshot()
        lines = snap.summary_lines

        # Box geometry — anchored top-right
        box_w = min(240, cw // 4)
        line_h = 14
        pad = 10
        box_h = len(lines) * line_h + 24
        x0 = cw - box_w - pad
        y0 = pad
        x1 = cw - pad
        y1 = y0 + box_h

        # Background
        self._canvas.create_rectangle(
            x0, y0, x1, y1,
            fill="#050f1e", outline="#00c8a0", width=1,
            tags=(tag,),
        )
        # Header
        self._canvas.create_text(
            x0 + 8, y0 + 4,
            text="TELEMETRY",
            fill="#00c8a0",
            font=("Courier", 9, "bold"),
            anchor=tk.NW,
            tags=(tag,),
        )

        # Data lines
        for i, line in enumerate(lines):
            self._canvas.create_text(
                x0 + 10, y0 + 20 + i * line_h,
                text=line,
                fill="#c8f0ff",
                font=("Courier", 9),
                anchor=tk.NW,
                tags=(tag,),
            )

    # ------------------------------------------------------------------
    # Convenience methods for assistant pipeline
    # ------------------------------------------------------------------

    def log_terminal(self, text: str, level: str = "INFO") -> None:
        """Push a line to the terminal log box.  Thread-safe."""
        self.terminal_log.add(text, level=level)

    def notify(self, text: str, category: str = "SYS", ttl: float = 6.0) -> None:
        """Push a notification to the bottom-right stack.  Thread-safe."""
        self.notification_stack.push(text, category=category, ttl=ttl)

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

        annotated = self._vision.get_annotated_frame_no_copy()
        if annotated is None:
            return

        # Track frame time for FPS counter
        now = time.monotonic()
        self._frame_times.append(now)

        # Convert numpy array → PIL → ImageTk
        pil_img = Image.fromarray(annotated)

        # Resize to current canvas size if needed
        cw = self._canvas.winfo_width()
        ch = self._canvas.winfo_height()
        if cw > 1 and ch > 1 and (cw, ch) != pil_img.size:
            pil_img = pil_img.resize(
                (cw, ch), Image.Resampling.NEAREST,  # NEAREST = fastest resize
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

        # Update FPS counter every frame
        if self._frame_times and len(self._frame_times) >= 2:
            elapsed = self._frame_times[-1] - self._frame_times[0]
            fps = (len(self._frame_times) - 1) / elapsed if elapsed > 0 else 0
            self.telemetry_panel.update_fps(fps)
            fps_text = f"{fps:.0f} FPS"
            if self._fps_text_id is None:
                self._fps_text_id = self._canvas.create_text(
                    self._canvas.winfo_width() - 10, 10,
                    text=fps_text,
                    fill="#00dcb4",
                    font=("Courier", 10),
                    anchor=tk.NE,
                    tags=("fps_counter",),
                )
            else:
                self._canvas.itemconfig(self._fps_text_id, text=fps_text)

        # Update telemetry from vision snapshot
        snap = self._vision.get_snapshot()
        if snap is not None:
            self.telemetry_panel.update_from_vision(
                object_count=snap.num_objects,
                objects_summary=snap.objects_summary,
            )

        # --- HUD UI boxes ---
        self.notification_stack.tick()
        self._draw_terminal_box()
        self._draw_notification_box()
        self._draw_telemetry_box()
