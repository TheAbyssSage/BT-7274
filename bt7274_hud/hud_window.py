"""
Tkinter window orchestrator — BT-7274 Pilot HUD
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Upgrades over v1:
  • ``dt``-based render loop: elapsed wall-clock time is measured each tick
    and passed to ``state.tick(dt)`` so cooldowns and TTLs are frame-rate
    independent (works at 10 FPS or 60 FPS equally correctly)
  • ``state.camera_fps`` is updated from ``CameraStream.fps_actual`` every
    frame so the renderer can display live telemetry
  • ``_build_demo_state()`` populates a realistic default state (abilities,
    comms panel, markers, notifications) so the HUD looks correct on first
    launch without external data
  • Graceful fallback: if no camera is found the window shows a dark
    placeholder so the HUD layout is still visible / testable
  • ``F11`` fullscreen toggle now correctly restarts both the camera and
    the renderer with the new resolution
  • ``_on_camera_change()`` cancels the pending frame job before swapping
    streams to avoid a brief double-render
  • Module no longer imports from a ``bt7274_hud`` package prefix, so it
    works when the files live flat in the same directory
  • Comprehensive docstrings and type hints throughout
"""

from __future__ import annotations

import logging
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Optional

import cv2
from PIL import Image, ImageTk

# ---------------------------------------------------------------------------
# Local imports (flat layout — files in same directory as this script)
# ---------------------------------------------------------------------------
from bt7274_hud.camera_stream import CameraStream
from bt7274_hud.hud_data import (
    AbilityIcon,
    AbilitySize,
    CardCategory,
    CommsState,
    EventCard,
    HudState,
    Marker,
    MarkerKind,
    SystemStatus,
    VitalState,
    WeaponReadout,
)
from bt7274_hud.hud_renderer import HudRenderer

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Placeholder frame (used when no camera is available)
# ---------------------------------------------------------------------------

def _make_placeholder(width: int, height: int) -> Image.Image:
    """Dark gradient placeholder used when the camera feed is unavailable."""
    from PIL import ImageDraw
    img  = Image.new("RGB", (width, height), (5, 12, 22))
    draw = ImageDraw.Draw(img)
    # Subtle grid
    for x in range(0, width, 80):
        draw.line([(x, 0), (x, height)], fill=(0, 40, 60), width=1)
    for y in range(0, height, 80):
        draw.line([(0, y), (width, y)], fill=(0, 40, 60), width=1)
    # Centre label
    draw.text(
        (width // 2, height // 2),
        "NO CAMERA SIGNAL",
        fill=(0, 100, 80),
        anchor="mm",
    )
    return img


# ---------------------------------------------------------------------------
# Demo state builder
# ---------------------------------------------------------------------------

def _build_demo_state(state: HudState) -> None:
    """
    Populate *state* with Titanfall 2–style demo data.
    """
    from bt7274_hud.hud_data import (
        AbilityIcon,
        AbilitySize,
        CallBox,
        CallContext,
        InfoFeedMessage,
        Notification,
        StatusIcon,
        StatusIconKind,
        TitanMeter,
    )

    state.pilot_callsign   = "SPECTRE-7"
    state.faction          = "MILITIA"
    state.compass_heading  = 45.0
    state.system_status    = SystemStatus.ONLINE

    # Vitals
    state.vitals = VitalState(
        health=0.78, shield=0.55, titan_link=0.91,
        health_max=1.0, shield_max=1.0,
    )

    # Minimap markers
    state.markers = [
        Marker(x=0.35, y=0.40, label="BT",    kind=MarkerKind.ALLY),
        Marker(x=0.60, y=0.55, label="MRVN",  kind=MarkerKind.ALLY),
        Marker(x=0.70, y=0.30, label="IMC-1", kind=MarkerKind.THREAT),
        Marker(x=0.25, y=0.65, label="BCNB",  kind=MarkerKind.OBJECTIVE),
    ]

    # --- Titanmeter (bottom-left) ---
    state.titanmeter = TitanMeter(progress=0.62, label="TITANFALL")

    # --- Status icons (right of titanmeter) ---
    state.status_icons = [
        StatusIcon(
            name="STIM", kind=StatusIconKind.ABILITY, key="Q",
            icon_glyph="⚡", cooldown_total=8.0, cooldown_remaining=0.0,
        ),
        StatusIcon(
            name="GRAPPLE", kind=StatusIconKind.ABILITY, key="LB",
            icon_glyph="⬡", cooldown_total=12.0, cooldown_remaining=4.5,
        ),
        StatusIcon(
            name="CLOAK", kind=StatusIconKind.ABILITY, key="RB",
            icon_glyph="◈", cooldown_total=15.0, cooldown_remaining=0.0,
        ),
        StatusIcon(
            name="FRAG", kind=StatusIconKind.ORDNANCE, key="G",
            icon_glyph="💣", cooldown_total=10.0, cooldown_remaining=7.2,
        ),
    ]

    # --- Call box (top-right, active) ---
    state.call_box = CallBox(
        active=True,
        pilot_name="BT-7274",
        voice_line="Transferring control to Pilot.",
        context=CallContext.COMBAT,
        signal_strength=0.85,
    )

    # --- Info feed (bottom-right) ---
    state.info_feed = [
        InfoFeedMessage(text="Enemy pilot detected NE sector", color="#ff4444", ttl=3600),
        InfoFeedMessage(text="Uplink channel secured", color="#00aaff", ttl=3600),
        InfoFeedMessage(text="Titanfall 62% charged", color="#ff8c00", ttl=3600),
        InfoFeedMessage(text="Ally BT-7274 linked", color="#00aaff", ttl=3600),
    ]

    # Legacy abilities (kept for backward compat)
    state.abilities = [
        AbilityIcon(name="STIM",    key="Q", color="#ff4444",
                    size=AbilitySize.MAIN,     cooldown_total=8.0,  cooldown_remaining=0.0,
                    icon_glyph="⚡"),
        AbilityIcon(name="GRAPPLE", key="LB", color="#00aaff",
                    size=AbilitySize.TACTICAL,  cooldown_total=12.0, cooldown_remaining=4.5,
                    icon_glyph="⬡"),
        AbilityIcon(name="CLOAK",   key="RB", color="#00cc88",
                    size=AbilitySize.TACTICAL,  cooldown_total=15.0, cooldown_remaining=0.0,
                    icon_glyph="◈"),
        AbilityIcon(name="PULSE",   key="LT", color="#ffaa22",
                    size=AbilitySize.PASSIVE,   cooldown_total=6.0,  cooldown_remaining=1.2,
                    icon_glyph="◉"),
    ]

    # Legacy weapon
    state.weapon = WeaponReadout(
        name="XO-16 CHAINGUN",
        ammo_current=28,
        ammo_reserve=96,
        mag_size=40,
        fire_mode="AUTO",
    )

    # Legacy event cards
    state.event_cards = [
        EventCard(label="CALLSIGN",  value="SPECTRE-7",        category=CardCategory.INFO,    ttl=0),
        EventCard(label="STATUS",    value="Target Marked",     category=CardCategory.SUCCESS, ttl=0),
        EventCard(label="INTEL",     value="IMC Patrol Nearby", category=CardCategory.WARNING, ttl=0),
    ]

    # Legacy notification feed
    state.notifications = [
        Notification(text="⬡ Ally BT-7274 linked",        color="#00aaff", ttl=3600),
        Notification(text="▲ Threat detected NE sector",   color="#ff6644", ttl=3600),
        Notification(text="✔ Uplink channel secured",      color="#00ff88", ttl=3600),
    ]


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class PilotHudWindow:
    """
    Dedicated Titanfall 2–style pilot HUD window.

    Orchestrates the camera stream, renderer, and Tkinter event loop.
    Frame timing is wall-clock based: ``state.tick(dt)`` receives true
    elapsed seconds so animations are frame-rate independent.

    Parameters
    ----------
    camera_device:
        Integer camera index (as a string) or a file/RTSP URL.
    width, height:
        Desired window and render resolution.
    fullscreen:
        Open in fullscreen mode immediately.
    demo_mode:
        If *True*, pre-populate a rich demo HUD state on startup.
    """

    DEFAULT_WIDTH  = 1280
    DEFAULT_HEIGHT = 720
    TARGET_FPS     = 30
    _FRAME_MS      = 1000 // TARGET_FPS   # ≈ 33 ms between frames

    def __init__(
        self,
        camera_device: str = "0",
        width: int = DEFAULT_WIDTH,
        height: int = DEFAULT_HEIGHT,
        *,
        fullscreen: bool = False,
        demo_mode: bool = True,
    ):
        self._camera_device = camera_device
        self.width  = width
        self.height = height
        self._fullscreen = fullscreen

        self._root:          Optional[tk.Tk]               = None
        self._canvas:        Optional[tk.Canvas]           = None
        self._canvas_img_id: Optional[int]                 = None
        self._photo_image:   Optional[ImageTk.PhotoImage]  = None
        self._camera_combo:  Optional[ttk.Combobox]        = None

        self._camera   = CameraStream(device=camera_device, width=width, height=height)
        self._renderer = HudRenderer(width=width, height=height)
        self._state    = HudState()

        if demo_mode:
            _build_demo_state(self._state)

        self._preview_job: Optional[str] = None
        self._running  = False
        self._last_ts  = 0.0   # monotonic timestamp of previous frame

        # Placeholder image used when camera has no frame yet
        self._placeholder = _make_placeholder(width, height)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def state(self) -> HudState:
        """Mutable HUD state — mutate from any thread; renderer reads it."""
        return self._state

    def start(self) -> None:
        """Launch the HUD window.  Blocks until the window is closed."""
        self._build_ui()
        self._running = True
        self._camera.start()
        self._last_ts = time.monotonic()
        self._schedule_frame()
        assert self._root is not None
        self._root.mainloop()

    def start_nonblocking(self) -> None:
        """Launch the HUD in a background thread."""
        self._build_ui()
        self._running = True
        self._camera.start()
        self._last_ts = time.monotonic()
        self._schedule_frame()
        assert self._root is not None
        threading.Thread(target=self._root.mainloop, daemon=True).start()

    def stop(self) -> None:
        """Signal the window to close."""
        if self._root:
            self._root.after(0, self._on_close)

    @property
    def is_open(self) -> bool:
        return self._root is not None

    # ------------------------------------------------------------------
    # Camera discovery
    # ------------------------------------------------------------------

    @staticmethod
    def _list_cameras(max_index: int = 8) -> list[dict]:
        devices = []
        for i in range(max_index):
            cap = cv2.VideoCapture(i)
            if cap.isOpened():
                devices.append({"index": str(i), "name": f"Camera {i}"})
                cap.release()
        return devices

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self._root = tk.Tk()
        self._root.title("BT-7274  |  PILOT HUD")
        self._root.configure(bg="black")
        self._root.protocol("WM_DELETE_WINDOW", self._on_close)

        if self._fullscreen:
            self._root.attributes("-fullscreen", True)
            self._apply_resolution(
                self._root.winfo_screenwidth(),
                self._root.winfo_screenheight(),
            )
        else:
            self._root.geometry(f"{self.width}x{self.height}")

        # Key bindings
        self._root.bind("<Escape>", lambda _e: self._on_close())
        self._root.bind("<F11>",    lambda _e: self._toggle_fullscreen())
        self._root.bind("q",        lambda _e: self._on_close())
        self._root.bind("<F5>",     lambda _e: self._reload_demo())

        # Camera selector bar (windowed mode only)
        if not self._fullscreen:
            self._build_camera_bar()

        # Main canvas
        self._canvas = tk.Canvas(self._root, bg="black", highlightthickness=0)
        self._canvas.pack(fill=tk.BOTH, expand=True)

    def _build_camera_bar(self) -> None:
        bar = tk.Frame(self._root, bg="#050f1a")
        bar.pack(fill=tk.X, side=tk.TOP)

        tk.Label(bar, text="CAMERA:", font=("Courier", 9),
                 fg="#00ff88", bg="#050f1a").pack(side=tk.LEFT, padx=(10, 4))

        devices      = self._list_cameras()
        device_names = [f"[{d['index']}] {d['name']}" for d in devices]
        if not device_names:
            device_names = ["[0] Default"]

        self._camera_combo = ttk.Combobox(
            bar, values=device_names, state="readonly",
            width=22, font=("Courier", 9),
        )
        # Pre-select current device
        for i, name in enumerate(device_names):
            if name.startswith(f"[{self._camera_device}]"):
                self._camera_combo.current(i)
                break
        else:
            self._camera_combo.current(0)

        self._camera_combo.pack(side=tk.LEFT, padx=(0, 10))
        self._camera_combo.bind("<<ComboboxSelected>>", self._on_camera_change)

        tk.Label(bar, text="F11=Fullscreen  F5=Demo  Q=Quit",
                 font=("Courier", 8), fg="#336655", bg="#050f1a").pack(side=tk.RIGHT, padx=10)

    # ------------------------------------------------------------------
    # Resolution helpers
    # ------------------------------------------------------------------

    def _apply_resolution(self, new_w: int, new_h: int) -> None:
        """Resize renderer and restart camera at a new resolution."""
        self.width  = new_w
        self.height = new_h
        self._renderer    = HudRenderer(width=new_w, height=new_h)
        self._placeholder = _make_placeholder(new_w, new_h)
        self._camera.stop()
        self._camera = CameraStream(device=self._camera_device, width=new_w, height=new_h)
        self._camera.start()

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_camera_change(self, _event=None) -> None:
        if self._camera_combo is None:
            return
        sel = self._camera_combo.get()
        idx_end = sel.find("]")
        if idx_end == -1:
            return
        new_dev = sel[1:idx_end]
        if new_dev == self._camera_device:
            return
        self._camera_device = new_dev
        # Cancel pending frame job before swapping streams
        if self._preview_job and self._root:
            self._root.after_cancel(self._preview_job)
            self._preview_job = None
        self._camera.stop()
        self._camera = CameraStream(
            device=self._camera_device, width=self.width, height=self.height
        )
        self._camera.start()
        self._schedule_frame()

    def _toggle_fullscreen(self) -> None:
        if self._root is None:
            return
        self._fullscreen = not self._fullscreen
        self._root.attributes("-fullscreen", self._fullscreen)
        if self._fullscreen:
            self._apply_resolution(
                self._root.winfo_screenwidth(),
                self._root.winfo_screenheight(),
            )
        else:
            self._apply_resolution(self.DEFAULT_WIDTH, self.DEFAULT_HEIGHT)
            self._root.geometry(f"{self.DEFAULT_WIDTH}x{self.DEFAULT_HEIGHT}")

    def _reload_demo(self) -> None:
        """Re-populate demo state (useful for testing without a live feed)."""
        _build_demo_state(self._state)
        log.info("Demo state reloaded via F5")

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
    # Render loop
    # ------------------------------------------------------------------

    def _schedule_frame(self) -> None:
        if not self._running or self._root is None:
            return
        self._update_frame()
        self._preview_job = self._root.after(self._FRAME_MS, self._schedule_frame)

    def _update_frame(self) -> None:
        """
        Core per-frame work:
          1. Measure elapsed time (dt)
          2. Advance HUD state via ``state.tick(dt)``
          3. Grab latest camera frame (or placeholder)
          4. Composite HUD overlay
          5. Push result to the canvas
        """
        now = time.monotonic()
        dt  = now - self._last_ts
        self._last_ts = now

        # Inject live telemetry from the camera stream into state
        self._state.camera_fps = self._camera.fps_actual
        if not self._camera.is_alive:
            self._state.system_status = SystemStatus.DEGRADED

        # Tick time-based state (cooldowns, TTLs)
        self._state.tick(dt)

        try:
            bg = self._camera.get_frame()
            if bg is None:
                bg = self._placeholder

            if bg.size != (self.width, self.height):
                bg = bg.resize((self.width, self.height), Image.Resampling.LANCZOS)

            composited = self._renderer.composite(bg, self._state)

            self._photo_image = ImageTk.PhotoImage(composited)

            if self._canvas is not None:
                if self._canvas_img_id is None:
                    self._canvas_img_id = self._canvas.create_image(
                        self.width // 2, self.height // 2,
                        image=self._photo_image,
                        anchor=tk.CENTER,
                    )
                else:
                    self._canvas.itemconfig(self._canvas_img_id, image=self._photo_image)

        except Exception as exc:
            log.debug("Frame error (suppressed): %s", exc)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    parser = argparse.ArgumentParser(description="BT-7274 Pilot HUD")
    parser.add_argument("--camera",     default="0",   help="Camera index or URL")
    parser.add_argument("--width",      type=int, default=1280)
    parser.add_argument("--height",     type=int, default=720)
    parser.add_argument("--fullscreen", action="store_true")
    parser.add_argument("--no-demo",    action="store_true", help="Skip demo state")
    args = parser.parse_args()

    window = PilotHudWindow(
        camera_device=args.camera,
        width=args.width,
        height=args.height,
        fullscreen=args.fullscreen,
        demo_mode=not args.no_demo,
    )
    window.start()