"""
Vision Viewer for BT-7274 Perception.

A tkinter window that shows what BT-7274's optical sensors see:
  - Live camera preview (tkinter-safe, no background threads)
  - Camera selector dropdown for multiple devices
  - Last captured frame with analysis overlay
  - Recent observation history
  - Manual "Look" trigger with progress feedback

Usage:
    python vision_viewer.py
    python -m bt7274_perception.vision_viewer

    # or from the assistant:
    from bt7274_perception.vision_viewer import VisionViewerWindow
    viewer = VisionViewerWindow()
    viewer.start()
"""

import os
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Optional

# Ensure project root on path for imports
_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from bt7274_perception.camera import CameraCapture
from bt7274_perception.vision_engine import VisionEngine
from bt7274_perception.vision_logger import VisionLogger

try:
    from bt7274_hud import PilotHudWindow
    _HAS_HUD = True
except Exception:
    _HAS_HUD = False


class VisionViewerWindow:
    """Tkinter window for BT-7274's camera vision."""

    # Base preview settings (power-efficient)
    PREVIEW_WIDTH = 160
    PREVIEW_HEIGHT = 120
    CAPTURE_WIDTH = 640
    CAPTURE_HEIGHT = 480
    PREVIEW_INTERVAL_MS = 1000  # Start slow, adapt based on visibility

    def __init__(
        self,
        camera_device: str = "0",
        ollama_url: str = "http://localhost:11434",
        vision_model: str = "llava",
        log_dir: Optional[str] = None,
    ):
        self._camera_device = camera_device
        self._ollama_url = ollama_url
        self._vision_model = vision_model
        self._log_dir = log_dir

        # Power management
        self._power_saving_mode = False
        self._window_visible = True
        self._last_window_check = 0
        self._adaptive_interval = self.PREVIEW_INTERVAL_MS

        # Single shared camera with lock — prevents preview and LOOK from fighting
        self._camera_lock = threading.Lock()
        self._shared_camera: Optional[CameraCapture] = None
        self._rebuild_camera()

        self.engine = VisionEngine(ollama_url=ollama_url, vision_model=vision_model)
        self.logger = VisionLogger(log_dir=log_dir)

        self._root: Optional[tk.Tk] = None
        self._preview_label: Optional[tk.Label] = None
        self._capture_label: Optional[tk.Label] = None
        self._desc_text: Optional[tk.Text] = None
        self._history_text: Optional[tk.Text] = None
        self._status_var: Optional[tk.StringVar] = None
        self._look_btn: Optional[tk.Button] = None
        self._camera_combo: Optional[ttk.Combobox] = None
        self._progress_var: Optional[tk.DoubleVar] = None
        self._progress_bar: Optional[ttk.Progressbar] = None
        self._power_btn: Optional[tk.Button] = None

        self._preview_job: Optional[str] = None
        self._preview_running = False
        self._last_preview_path: Optional[str] = None
        self._last_capture_path: Optional[str] = None

        self._has_pil = False
        try:
            from PIL import Image, ImageTk
            self._has_pil = True
        except Exception:
            pass

    def _rebuild_camera(self):
        """Rebuild the single shared camera instance."""
        with self._camera_lock:
            # Use lower resolution for shared camera to reduce bandwidth
            self._shared_camera = CameraCapture(
                device=self._camera_device,
                width=self.CAPTURE_WIDTH if not self._power_saving_mode else self.PREVIEW_WIDTH,
                height=self.CAPTURE_HEIGHT if not self._power_saving_mode else self.PREVIEW_HEIGHT,
            )

    def _capture_locked(self, for_preview: bool = False) -> Optional[str]:
        """Capture a frame using the shared camera (thread-safe)."""
        with self._camera_lock:
            if self._shared_camera is None:
                return None
            # For preview captures, use lower resolution
            if for_preview:
                temp_camera = CameraCapture(
                    device=self._camera_device,
                    width=self.PREVIEW_WIDTH,
                    height=self.PREVIEW_HEIGHT,
                )
                return temp_camera.capture()
            return self._shared_camera.capture()

    def _build_ui(self):
        """Construct the tkinter UI."""
        self._root = tk.Tk()
        self._root.title("BT-7274  |  Optical Sensors")
        self._root.geometry("950x750")
        self._root.configure(bg="#1a1a1a")
        self._root.protocol("WM_DELETE_WINDOW", self._on_close)

        # ── Header ──────────────────────────────────────────────
        header = tk.Label(
            self._root,
            text="BT-7274  OPTICAL  SENSORS",
            font=("Courier", 16, "bold"),
            fg="#00ff88",
            bg="#1a1a1a",
        )
        header.pack(pady=(10, 5))

        # ── Top bar: Camera selector + Status ───────────────────
        top_bar = tk.Frame(self._root, bg="#1a1a1a")
        top_bar.pack(fill=tk.X, padx=20, pady=(0, 5))

        # Camera selector
        cam_label = tk.Label(
            top_bar,
            text="Camera:",
            font=("Courier", 10),
            fg="#aaaaaa",
            bg="#1a1a1a",
        )
        cam_label.pack(side=tk.LEFT)

        devices = CameraCapture.list_devices()
        device_names = [f"[{d['index']}] {d['name']}" for d in devices]
        self._camera_combo = ttk.Combobox(
            top_bar,
            values=device_names,
            state="readonly",
            width=40,
            font=("Courier", 10),
        )
        if device_names:
            current_idx = 0
            for i, name in enumerate(device_names):
                if name.startswith(f"[{self._camera_device}]"):
                    current_idx = i
                    break
            self._camera_combo.current(current_idx)
        self._camera_combo.pack(side=tk.LEFT, padx=(5, 20))
        self._camera_combo.bind("<<ComboboxSelected>>", self._on_camera_change)

        # Status
        self._status_var = tk.StringVar(value="Standby")
        status_bar = tk.Label(
            top_bar,
            textvariable=self._status_var,
            font=("Courier", 10),
            fg="#aaaaaa",
            bg="#1a1a1a",
            anchor="w",
        )
        status_bar.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # ── Main content frame ──────────────────────────────────
        content = tk.Frame(self._root, bg="#1a1a1a")
        content.pack(fill=tk.BOTH, expand=True, padx=20, pady=5)

        # Left: Preview + Capture
        left_frame = tk.Frame(content, bg="#1a1a1a")
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Live preview
        preview_frame = tk.LabelFrame(
            left_frame,
            text=" LIVE PREVIEW ",
            font=("Courier", 10),
            fg="#00ff88",
            bg="#1a1a1a",
        )
        preview_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        self._preview_label = tk.Label(
            preview_frame,
            bg="#0a0a0a",
            text="[No signal]",
            fg="#444444",
            font=("Courier", 12),
        )
        self._preview_label.pack(padx=10, pady=10)

        # Last capture
        capture_frame = tk.LabelFrame(
            left_frame,
            text=" LAST CAPTURE ",
            font=("Courier", 10),
            fg="#00ff88",
            bg="#1a1a1a",
        )
        capture_frame.pack(fill=tk.BOTH, expand=True)

        self._capture_label = tk.Label(
            capture_frame,
            bg="#0a0a0a",
            text="[No capture]",
            fg="#444444",
            font=("Courier", 12),
        )
        self._capture_label.pack(padx=10, pady=10)

        # Right: Controls + Description + History
        right_frame = tk.Frame(content, bg="#1a1a1a", width=340)
        right_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=(10, 0))
        right_frame.pack_propagate(False)

        # Controls
        ctrl_frame = tk.Frame(right_frame, bg="#1a1a1a")
        ctrl_frame.pack(fill=tk.X, pady=(0, 10))

        self._look_btn = tk.Button(
            ctrl_frame,
            text="LOOK",
            font=("Courier", 12, "bold"),
            bg="#00ff88",
            fg="#1a1a1a",
            activebackground="#00cc66",
            command=self._on_look,
        )
        self._look_btn.pack(fill=tk.X, pady=(0, 5))

        # Power saving toggle
        self._power_btn = tk.Button(
            ctrl_frame,
            text="POWER SAVING: OFF",
            font=("Courier", 10),
            bg="#333333",
            fg="#ffffff",
            command=self._toggle_power_saving,
        )
        self._power_btn.pack(fill=tk.X, pady=(0, 5))

        # Progress bar
        self._progress_var = tk.DoubleVar(value=0.0)
        self._progress_bar = ttk.Progressbar(
            ctrl_frame,
            variable=self._progress_var,
            maximum=100,
            mode="determinate",
        )
        self._progress_bar.pack(fill=tk.X, pady=(0, 5))

        refresh_btn = tk.Button(
            ctrl_frame,
            text="Refresh History",
            font=("Courier", 10),
            bg="#333333",
            fg="#ffffff",
            command=self._refresh_history,
        )
        refresh_btn.pack(fill=tk.X)

        # Description
        desc_frame = tk.LabelFrame(
            right_frame,
            text=" ANALYSIS ",
            font=("Courier", 10),
            fg="#00ff88",
            bg="#1a1a1a",
        )
        desc_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        self._desc_text = tk.Text(
            desc_frame,
            wrap=tk.WORD,
            font=("Courier", 10),
            bg="#0a0a0a",
            fg="#cccccc",
            height=8,
            state=tk.DISABLED,
        )
        self._desc_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # History
        hist_frame = tk.LabelFrame(
            right_frame,
            text=" OBSERVATION LOG ",
            font=("Courier", 10),
            fg="#00ff88",
            bg="#1a1a1a",
        )
        hist_frame.pack(fill=tk.BOTH, expand=True)

        self._history_text = tk.Text(
            hist_frame,
            wrap=tk.WORD,
            font=("Courier", 9),
            bg="#0a0a0a",
            fg="#888888",
            height=10,
            state=tk.DISABLED,
        )
        self._history_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # ── Footer ──────────────────────────────────────────────
        footer = tk.Label(
            self._root,
            text="Select camera above  |  Press LOOK to capture and analyze  |  Close window to exit",
            font=("Courier", 9),
            fg="#555555",
            bg="#1a1a1a",
        )
        footer.pack(pady=(5, 10))

    def _set_status(self, msg: str):
        if self._status_var:
            self._status_var.set(msg)
        if self._root:
            self._root.update_idletasks()

    def _set_progress(self, value: float):
        if self._progress_var and self._root:
            self._progress_var.set(value)
            self._root.update_idletasks()

    def _update_text(self, widget: tk.Text | None, text: str):
        """Safely update a disabled Text widget."""
        if widget is None or self._root is None:
            return
        self._root.after(0, lambda: self._do_update_text(widget, text))

    def _do_update_text(self, widget: tk.Text | None, text: str):
        if widget is None:
            return
        widget.config(state=tk.NORMAL)
        widget.delete("1.0", tk.END)
        widget.insert("1.0", text)
        widget.config(state=tk.DISABLED)

    def _update_image(self, label: tk.Label | None, path: str):
        """Update a Label with an image from path."""
        if label is None or self._root is None:
            return
        self._root.after(0, lambda: self._do_update_image(label, path))

    def _do_update_image(self, label: tk.Label | None, path: str):
        if label is None:
            return
        try:
            if self._has_pil:
                from PIL import Image, ImageTk
                # Use faster loading for previews
                if label == self._preview_label:
                    img = Image.open(path)
                    # Fast resize for preview
                    img.thumbnail((self.PREVIEW_WIDTH, self.PREVIEW_HEIGHT), Image.Resampling.LANCZOS)
                    photo = ImageTk.PhotoImage(img)
                else:
                    # Full quality for capture
                    img = Image.open(path)
                    label_w = max(label.winfo_width(), self.PREVIEW_WIDTH)
                    label_h = max(label.winfo_height(), self.PREVIEW_HEIGHT)
                    img.thumbnail((label_w - 20, label_h - 20), Image.Resampling.LANCZOS)
                    photo = ImageTk.PhotoImage(img)
                label.config(image=photo, text="", bg="#0a0a0a")
                label.image = photo  # type: ignore[attr-defined]
            else:
                photo = tk.PhotoImage(file=path)
                label.config(image=photo, text="", bg="#0a0a0a")
                label.image = photo  # type: ignore[attr-defined]
        except Exception as e:
            label.config(text=f"[Image error: {e}]", image="")

    def _schedule_preview(self):
        """Schedule the next preview frame using tkinter's after."""
        if not self._preview_running or self._root is None:
            return
        
        # Adaptive preview rate based on window visibility and power mode
        self._update_adaptive_interval()
        self._capture_preview_frame()
        self._preview_job = self._root.after(self._adaptive_interval, self._schedule_preview)

    def _update_adaptive_interval(self):
        """Adjust preview interval based on window visibility and power mode."""
        import time
        current_time = time.time()
        
        # Check window visibility every 5 seconds
        if current_time - self._last_window_check > 5.0:
            self._last_window_check = current_time
            try:
                # Simple heuristic: if window is minimized, it's not visible
                assert self._root is not None
                self._window_visible = self._root.winfo_viewable()
            except Exception:
                self._window_visible = True  # Assume visible if check fails
        
        # Base interval
        interval = self.PREVIEW_INTERVAL_MS
        
        # Slow down if window not visible
        if not self._window_visible:
            interval *= 4  # 4x slower when hidden
        
        # Power saving mode
        if self._power_saving_mode:
            interval *= 2  # 2x slower in power saving mode
        
        self._adaptive_interval = min(interval, 10000)  # Cap at 10 seconds

    def _toggle_power_saving(self):
        """Toggle power saving mode."""
        self._power_saving_mode = not self._power_saving_mode
        mode_text = "ON" if self._power_saving_mode else "OFF"
        if self._power_btn:
            self._power_btn.config(text=f"POWER SAVING: {mode_text}")
        self._set_status(f"Power saving mode {'enabled' if self._power_saving_mode else 'disabled'}")

    def _capture_preview_frame(self):
        """Capture one preview frame and update the label."""
        try:
            path = self._capture_locked(for_preview=True)
            if path:
                self._last_preview_path = path
                self._update_image(self._preview_label, path)
                def cleanup():
                    try:
                        os.remove(path)
                    except Exception:
                        pass
                if self._root:
                    self._root.after(100, cleanup)
        except Exception:
            pass

    def _on_camera_change(self, event=None):
        """Handle camera selection change."""
        if self._camera_combo is None:
            return
        selection = self._camera_combo.get()
        if not selection:
            return
        idx_end = selection.find("]")
        if idx_end == -1:
            return
        new_device = selection[1:idx_end]
        if new_device == self._camera_device:
            return
        self._camera_device = new_device
        self._rebuild_camera()
        self._set_status(f"Switched to camera {new_device}")
        if self._capture_label:
            self._capture_label.config(text="[No capture]", image="")

    def _on_look(self):
        """Trigger a full capture + vision analysis."""
        if self._look_btn:
            self._look_btn.config(state=tk.DISABLED, text="SCANNING...")
        self._set_progress(10)
        self._set_status("Capturing high-resolution frame...")

        def look_thread():
            try:
                self._set_progress(20)

                image_path = self._capture_locked(for_preview=False)
                if image_path is None:
                    self._set_progress(0)
                    self._set_status("Camera capture failed")
                    self._update_text(self._desc_text, "Camera capture failed. Check permissions.")
                    return

                self._last_capture_path = image_path
                self._set_progress(40)
                self._set_status("Analyzing visual data...")

                result = self.engine.analyze(image_path)
                self._set_progress(80)

                self.logger.log_observation(
                    description=result["description"],
                    image_path=image_path,
                    model=result["model"],
                    response_time=result["response_time"],
                    trigger="manual_viewer",
                    metadata={"success": result["success"], "error": result["error"]},
                )

                self._update_image(self._capture_label, image_path)
                if result["success"]:
                    self._set_progress(100)
                    self._set_status(f"Analysis complete ({result['response_time']:.1f}s)")
                    self._update_text(
                        self._desc_text,
                        f"[{result['model']}]  {result['response_time']:.1f}s\n\n{result['description']}",
                    )
                else:
                    self._set_progress(0)
                    self._set_status(f"Analysis failed: {result['error']}")
                    self._update_text(
                        self._desc_text,
                        f"VISION ERROR\n{result['error']}",
                    )

                self._refresh_history()

            except Exception as e:
                self._set_progress(0)
                self._set_status(f"Error: {e}")
                self._update_text(self._desc_text, f"System error: {e}")
            finally:
                if self._look_btn and self._root:
                    btn = self._look_btn
                    self._root.after(0, lambda: btn.config(state=tk.NORMAL, text="LOOK"))
                if self._root:
                    self._root.after(2000, lambda: self._set_progress(0))

        threading.Thread(target=look_thread, daemon=True).start()

    def _refresh_history(self):
        """Load recent observations into the history panel."""
        try:
            obs = self.logger.get_recent_observations(count=10)
            lines = []
            for o in obs:
                time_str = o.get("time", "??:??:??")
                desc = o.get("description", "No description.")
                trigger = o.get("trigger", "unknown")
                lines.append(f"[{time_str}] ({trigger})")
                lines.append(f"  {desc[:120]}{'...' if len(desc) > 120 else ''}")
                lines.append("")
            self._update_text(self._history_text, "\n".join(lines) if lines else "No observations yet.")
        except Exception as e:
            self._update_text(self._history_text, f"History error: {e}")

    def _on_close(self):
        """Clean shutdown."""
        self._preview_running = False
        if self._preview_job and self._root:
            self._root.after_cancel(self._preview_job)
            self._preview_job = None
        if self._root:
            self._root.destroy()
            self._root = None

    def start(self):
        """Launch the viewer window (blocks until closed)."""
        self._build_ui()
        self._refresh_history()

        self._preview_running = True
        self._schedule_preview()

        self._set_status("Optical sensors active. POWER SAVING: OFF")
        assert self._root is not None
        self._root.mainloop()

    def start_nonblocking(self):
        """Launch the viewer without blocking the caller."""
        self._build_ui()
        self._refresh_history()
        self._preview_running = True
        self._schedule_preview()
        self._set_status("Optical sensors active. POWER SAVING: OFF")
        assert self._root is not None
        threading.Thread(target=self._root.mainloop, daemon=True).start()

    def is_open(self) -> bool:
        """Check if the window is still open."""
        return self._root is not None

    def trigger_look(self):
        """Programmatically trigger a look (e.g. from voice command)."""
        if self._root:
            self._root.after(0, self._on_look)

    def open_pilot_hud(self):
        """Launch the dedicated Pilot HUD window if available."""
        if not _HAS_HUD or PilotHudWindow is None:
            self._set_status("Pilot HUD not available.")
            return
        hud = PilotHudWindow(
            camera_device=self._camera_device,
            width=1280,
            height=720,
            fullscreen=False,
        )
        # Mirror current state into HUD
        hud.state.pilot_callsign = "PILOT"
        hud.state.system_status = "ONLINE"
        hud.start_nonblocking()
        self._set_status("Pilot HUD opened.")


def main():
    """CLI entry point."""
    import argparse
    parser = argparse.ArgumentParser(description="BT-7274 Vision Viewer")
    parser.add_argument("--device", default="0", help="Camera device index (default: 0)")
    parser.add_argument("--model", default="llava", help="Ollama vision model (default: llava)")
    parser.add_argument("--url", default="http://localhost:11434", help="Ollama URL")
    args = parser.parse_args()

    viewer = VisionViewerWindow(
        camera_device=args.device,
        vision_model=args.model,
        ollama_url=args.url,
    )
    viewer.start()


if __name__ == "__main__":
    main()
