#!/usr/bin/env python3
"""Launch the BT-7274 real-time YOLO detection HUD window.

Usage:
    python run_realtime_hud.py
    python run_realtime_hud.py --camera 1 --width 640 --height 480
    python run_realtime_hud.py --fullscreen
    python run_realtime_hud.py --model yolov8s.pt --conf 0.3
    python run_realtime_hud.py --no-yolo          # camera-only, no detection
    python run_realtime_hud.py --detection-interval 3  # run YOLO every 3 frames
"""

import argparse
import sys
from pathlib import Path

# Ensure project root on path
_project_root = Path(__file__).parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from bt7274_hud.realtime_hud_window import RealtimeHudWindow


def main():
    parser = argparse.ArgumentParser(
        description="BT-7274 Real-Time YOLO Detection HUD",
    )
    parser.add_argument(
        "--camera", default="0",
        help="Camera device index (default: 0)",
    )
    parser.add_argument(
        "--width", type=int, default=1280,
        help="Window width (default: 1280)",
    )
    parser.add_argument(
        "--height", type=int, default=720,
        help="Window height (default: 720)",
    )
    parser.add_argument(
        "--fullscreen", action="store_true",
        help="Launch in fullscreen mode",
    )
    parser.add_argument(
        "--model", default="yolov8n.pt",
        help="YOLO model: yolov8n.pt (nano/fast), yolov8s.pt (small), "
             "yolov8m.pt (medium) (default: yolov8n.pt)",
    )
    parser.add_argument(
        "--conf", type=float, default=0.5,
        help="Confidence threshold 0.0-1.0 (default: 0.5)",
    )
    parser.add_argument(
        "--iou", type=float, default=0.45,
        help="IoU threshold for NMS (default: 0.45)",
    )
    parser.add_argument(
        "--no-yolo", action="store_true",
        help="Disable YOLO detection (camera-only mode)",
    )
    parser.add_argument(
        "--detection-interval", type=int, default=1,
        help="Run YOLO every N frames — higher = better FPS, less CPU "
             "(default: 1)",
    )

    args = parser.parse_args()

    print("=" * 55)
    print("  BT-7274 REAL-TIME YOLO DETECTION HUD")
    print("=" * 55)
    print(f"  Camera:            device {args.camera}")
    print(f"  Resolution:        {args.width}x{args.height}")
    print(f"  YOLO:              {'OFF' if args.no_yolo else args.model}")
    if not args.no_yolo:
        print(f"  Confidence:        {args.conf}")
        print(f"  IoU threshold:     {args.iou}")
        print(f"  Detection every:   {args.detection_interval} frame(s)")
    print(f"  Mode:              {'fullscreen' if args.fullscreen else 'windowed'}")
    print("=" * 55)
    print()
    print("  CONTROLS:")
    print("    Esc / Q  — Close window")
    print("    F11      — Toggle fullscreen")
    print()

    window = RealtimeHudWindow(
        camera_device=args.camera,
        width=args.width,
        height=args.height,
        fullscreen=args.fullscreen,
        yolo_model=args.model if not args.no_yolo else None,
        yolo_conf=args.conf,
        yolo_iou=args.iou,
        enable_yolo=not args.no_yolo,
        detection_interval=args.detection_interval,
    )
    window.start()


if __name__ == "__main__":
    main()
