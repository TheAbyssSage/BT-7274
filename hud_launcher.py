#!/usr/bin/env python3
"""
BT-7274 Pilot HUD — Standalone launcher.

Opens a dedicated fullscreen (or windowed) HUD showing the live camera feed
with Titanfall 2-style overlays.

Usage:
    python hud_launcher.py
    python hud_launcher.py --windowed
    python hud_launcher.py --device 1
"""

import argparse
import sys
from pathlib import Path

# Ensure project root is on sys.path
_project_root = Path(__file__).parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from bt7274_hud import PilotHudWindow


def main():
    parser = argparse.ArgumentParser(description="BT-7274 Pilot HUD")
    parser.add_argument("--windowed", action="store_true", help="Run in a window instead of fullscreen")
    parser.add_argument("--device", default="0", help="AVFoundation camera device index (default: 0)")
    parser.add_argument("--width", type=int, default=1280, help="Window width (windowed mode)")
    parser.add_argument("--height", type=int, default=720, help="Window height (windowed mode)")
    args = parser.parse_args()

    print("  [SYS] Initializing Pilot HUD...")
    print(f"  [SYS] Camera device: {args.device}")
    print(f"  [SYS] Mode: {'windowed' if args.windowed else 'fullscreen'}")

    hud = PilotHudWindow(
        camera_device=args.device,
        width=args.width,
        height=args.height,
        fullscreen=not args.windowed,
    )

    # Populate demo state so the HUD isn't empty on first frame
    from bt7274_hud.hud_data import HudState, Marker, AbilityIcon, Notification, WeaponReadout
    hud.state.pilot_callsign = "PILOT-7274"
    hud.state.mission_progress = 0.65
    hud.state.comms_text = "BT-7274: Link established."
    hud.state.event_cards = ["Objective: Secure Zone", "Threat detected"]
    hud.state.ally_markers = [Marker(x=0.3, y=0.4, label="A1", color="blue")]
    hud.state.threat_markers = [Marker(x=0.7, y=0.6, label="T1", color="red")]
    hud.state.abilities = [
        AbilityIcon(name="Smoke", key="Q", color="#ff4444", cooldown=0.0),
        AbilityIcon(name="Wall", key="E", color="#00aaff", cooldown=2.5),
        AbilityIcon(name="Sonar", key="F", color="#00ff88", cooldown=0.0),
    ]
    hud.state.weapon = WeaponReadout(name="XO-16", ammo_current=42, ammo_reserve=240)
    hud.state.notifications = [
        Notification(text="[12:04] Reaper eliminated", color="#ffcc00"),
        Notification(text="[12:02] Shield restored", color="#00ff88"),
    ]
    hud.state.system_status = "ONLINE"

    print("  [SYS] HUD starting. Press ESC or Q to exit.")
    hud.start()
    print("  [SYS] HUD closed.")


if __name__ == "__main__":
    main()
