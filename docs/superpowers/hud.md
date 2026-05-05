# BT-7274 Pilot HUD

## Quick Start

```bash
# Fullscreen (default)
python hud_launcher.py

# Windowed mode
python hud_launcher.py --windowed

# Use a different camera
python hud_launcher.py --device 1
```

## Architecture

- `bt7274_hud/hud_data.py` — Immutable-ish dataclasses for all HUD state.
- `bt7274_hud/hud_renderer.py` — PIL-based drawing engine. Renders overlays onto a transparent layer and composites onto the camera frame.
- `bt7274_hud/hud_window.py` — Tkinter window with a `Canvas`. Schedules camera captures and refreshes the HUD at ~5 FPS.
- `hud_launcher.py` — Standalone entry point with demo state.

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
from bt7274_hud import PilotHudWindow, HudState, Marker, AbilityIcon

hud = PilotHudWindow(fullscreen=False)
hud.state.pilot_callsign = "PILOT-7274"
hud.state.abilities = [
    AbilityIcon(name="Smoke", key="Q", color="#ff4444", cooldown=0.0),
]
hud.start()
```

## Keyboard Shortcuts

- `ESC` or `Q` — Close HUD
- `F11` — Toggle fullscreen

## Voice Commands

You can also open the HUD by voice:
- "Open HUD"
- "Show HUD"
- "Activate HUD"
- "Pilot HUD"
