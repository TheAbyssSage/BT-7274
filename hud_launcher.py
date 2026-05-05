#!/usr/bin/env python3
"""
BT-7274 Camera Stream — Standalone launcher.

Opens a dedicated fullscreen (or windowed) camera feed.
No HUD overlays.  Runs as fast as possible.

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

from bt7274_hud.hud_window import CameraWindow


def main():
    parser = argparse.ArgumentParser(description="BT-7274 Camera Stream")
    parser.add_argument("--windowed", action="store_true", help="Run in a window instead of fullscreen")
    parser.add_argument("--device", default="0", help="AVFoundation camera device index (default: 0)")
    parser.add_argument("--width", type=int, default=1280, help="Window width (windowed mode)")
    parser.add_argument("--height", type=int, default=720, help="Window height (windowed mode)")
    parser.add_argument("--list-cameras", action="store_true", help="List available cameras and exit")
    args = parser.parse_args()

    if args.list_cameras:
        from bt7274_hud.camera_stream import CameraStream
        devices = CameraStream.list_devices()
        if not devices:
            print("No cameras detected.")
        else:
            print(f"{'Index':<8}{'Name'}")
            print("-" * 40)
            for d in devices:
                print(f"{d['index']:<8}{d['name']}")
        return

    print("  [SYS] Initializing camera stream...")
    print(f"  [SYS] Camera device: {args.device}")
    print(f"  [SYS] Mode: {'windowed' if args.windowed else 'fullscreen'}")

    window = CameraWindow(
        camera_device=args.device,
        width=args.width,
        height=args.height,
        fullscreen=not args.windowed,
    )

    print("  [SYS] Camera starting. Press ESC or Q to exit.")
    window.start()
    print("  [SYS] Camera closed.")


if __name__ == "__main__":
    main()
