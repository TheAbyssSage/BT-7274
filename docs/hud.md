# BT-7274 Pilot HUD

## Quick Start

```bash
# Fullscreen (default)
python hud_launcher.py

# Windowed mode
python hud_launcher.py --windowed

# Use a different camera
python hud_launcher.py --device 1

# List all available cameras
python hud_launcher.py --list-cameras
```

## Architecture

- `bt7274_hud/camera_stream.py` — OpenCV-based camera capture with auto-reconnect, MJPEG negotiation, and device enumeration.
- `bt7274_hud/hud_data.py` — Immutable-ish dataclasses for all HUD state.
- `bt7274_hud/hud_renderer.py` — PIL-based drawing engine. Renders overlays onto a transparent layer and composites onto the camera frame.
- `bt7274_hud/hud_window.py` — Tkinter window with a `Canvas`. Zero-copy render loop at maximum FPS with FPS counter overlay.
- `hud_launcher.py` — Standalone entry point with demo state.

## Camera Selection

- `Tab` or `C` — Cycle to the next available camera
- `--list-cameras` — List all detected cameras from the CLI:
  ```bash
  python hud_launcher.py --list-cameras
  ```
- `--device N` — Start with a specific camera index:
  ```bash
  python hud_launcher.py --device 1
  ```

The current camera name is displayed in the top-left corner of the window.

## Performance

The render loop is optimized for zero-latency helmet display:
- Uses `get_frame_array()` fast-path to avoid PIL conversion overhead
- Skips frame resize when camera resolution matches window dimensions
- OpenCV buffer size set to 1 (no stale frames queued)
- MJPEG preferred over raw for lower CPU usage
- Real-time FPS counter displayed in bottom-right corner

Target: ≥30 FPS with <2 frames of latency on Apple Silicon.

## HUD Elements

| Position | Element | Description |
|----------|---------|-------------|
| Center | Reticle | White crosshair with center dot |
| Top-left | TACMAP | Circular minimap with ally (blue) and threat (red) markers |
| Top-center | Mission Bar | Horizontal progress bar with neutral diamond icon |
| Top-right | COMMS | Semi-transparent panel for alerts/transmissions |
| Mid-left | Event Cards | Compact cards for objectives and key events |
| Bottom-center | Abilities | Circular icons with key prompts (red = offensive, blue/green = utility) |
| Bottom-right | Weapon Readout | Silhouette + ammo counts |
| Right-mid | Notification Feed | Kill-feed style event log |
| Bottom-left | System Status | Small "SYS: ONLINE" text |

## Customizing State

```python
from bt7274.bt7274_hud.hud_window import CameraWindow
from bt7274.bt7274_hud.hud_data import HudState, Marker, AbilityIcon

hud = CameraWindow(fullscreen=False)
# Note: CameraWindow is a bare camera feed — for HUD overlays, use HudRenderer
```

## Keyboard Shortcuts

- `ESC` or `Q` — Close HUD
- `F11` — Toggle fullscreen
- `Tab` or `C` — Cycle camera

## Voice Commands

You can also open the HUD by voice:
- "Open HUD"
- "Show HUD"
- "Activate HUD"
- "Pilot HUD"
