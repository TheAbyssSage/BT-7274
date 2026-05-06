#!/usr/bin/env python3
"""BT-7274 Unified Command-Line Interface.

Usage:
    bt7274 assistant          # Launch the voice assistant
    bt7274 assistant --chat   # Console chat mode
    bt7274 camera             # Open camera stream window
    bt7274 hud                # Open real-time YOLO detection HUD
    bt7274 vision             # Open vision viewer window
    bt7274 logs               # View interaction logs
    bt7274 logs --all         # View all logs
    bt7274 logs --summary     # View log summary
    bt7274 generate-standby   # Generate standby response audio
    bt7274 list-cameras       # List available cameras
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path


def cmd_assistant(args):
    """Launch the BT-7274 voice assistant."""
    from bt7274_assistant.pipeline.core import BT7274Assistant

    assistant = BT7274Assistant(
        ai_mode=args.ai_mode,
        performance_mode=args.performance_mode,
        console_chat_mode=args.chat,
    )

    if args.generate_standby or args.force_regenerate:
        assistant.initialize()
        count = assistant.generate_standby_responses(
            force_regenerate=args.force_regenerate
        )
        print(f"\n  Generated {count} standby responses.")
    else:
        assistant.run()


def cmd_camera(args):
    """Open the camera stream window."""
    from bt7274_hud.hud_window import CameraWindow

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


def cmd_hud(args):
    """Open the real-time YOLO detection HUD."""
    from bt7274_hud.realtime_hud_window import RealtimeHudWindow

    if args.low_latency:
        args.width = 640
        args.height = 480

    print("=" * 55)
    print("  BT-7274 REAL-TIME YOLO DETECTION HUD")
    print("=" * 55)
    print(f"  Camera:            device {args.camera}")
    print(f"  Resolution:        {args.width}x{args.height}")
    print(f"  YOLO:              {'DISABLED' if args.no_yolo else args.model}")
    if not args.no_yolo:
        print(f"  Confidence:        {args.conf}")
        print(f"  Detection interval: every {args.detection_interval} frame(s)")
    print(f"  Fullscreen:        {args.fullscreen}")
    print("=" * 55)

    window = RealtimeHudWindow(
        camera_device=args.camera,
        width=args.width,
        height=args.height,
        fullscreen=args.fullscreen,
        yolo_model=None if args.no_yolo else args.model,
        yolo_conf=args.conf,
        yolo_iou=args.iou,
        enable_yolo=not args.no_yolo,
        detection_interval=args.detection_interval,
    )
    window.start()


def cmd_vision(args):
    """Open the vision viewer window."""
    from bt7274_perception.vision_viewer import main as vision_main
    vision_main()


def cmd_logs(args):
    """View interaction logs."""
    from bt7274_workstation.interaction_logger import InteractionLogger

    logger = InteractionLogger()

    if args.summary:
        log_dir = logger.log_dir
        files = sorted(log_dir.glob("bt7274_interactions_*.jsonl"))
        total_entries = 0
        for f in files:
            with open(f) as fh:
                total_entries += sum(1 for _ in fh)
        print(f"\n  Log files: {len(files)}")
        print(f"  Total entries: {total_entries}")
        return

    date_str = args.date
    if not date_str:
        date_str = datetime.now().strftime("%Y-%m-%d")

    log_file = logger.log_dir / f"bt7274_interactions_{date_str}.jsonl"
    if not log_file.exists():
        print(f"  No logs found for {date_str}")
        return

    entries = []
    with open(log_file) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

    if args.all:
        for f in sorted(logger.log_dir.glob("bt7274_interactions_*.jsonl")):
            print(f"\n  === {f.stem} ===")
            with open(f) as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        try:
                            entry = json.loads(line)
                            ts = entry.get("timestamp", "??:??")
                            pilot = entry.get("pilot_message", "")
                            bt = entry.get("bt_response", "")
                            print(f"  [{ts}] Pilot: {pilot}")
                            print(f"         BT:    {bt}")
                        except json.JSONDecodeError:
                            pass
        return

    print(f"\n  === Logs for {date_str} ({len(entries)} entries) ===")
    for entry in entries:
        ts = entry.get("timestamp", "??:??")
        if "T" in ts:
            ts = ts.split("T")[1].split(".")[0]
        pilot = entry.get("pilot_message", "")
        bt = entry.get("bt_response", "")
        print(f"\n  [{ts}] Pilot: {pilot}")
        print(f"         BT:    {bt}")


def cmd_list_cameras(args):
    """List available cameras."""
    from bt7274_hud.camera_stream import CameraStream
    devices = CameraStream.list_devices()
    if not devices:
        print("No cameras detected.")
    else:
        print(f"{'Index':<8}{'Name'}")
        print("-" * 40)
        for d in devices:
            print(f"{d['index']:<8}{d['name']}")


def main():
    parser = argparse.ArgumentParser(
        description="BT-7274 Vanguard-class Titan AI Assistant"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # ── assistant ──
    assist_parser = subparsers.add_parser("assistant", help="Launch the voice assistant")
    assist_parser.add_argument("--chat", action="store_true", help="Console chat mode (text input)")
    assist_parser.add_argument("--ai-mode", choices=["local", "cloud"], default="local")
    assist_parser.add_argument("--performance-mode", choices=["standard", "performance"])
    assist_parser.add_argument("--generate-standby", action="store_true", help="Generate standby responses")
    assist_parser.add_argument("--force-regenerate", action="store_true", help="Force regenerate all standby audio")

    # ── camera ──
    cam_parser = subparsers.add_parser("camera", help="Open camera stream window")
    cam_parser.add_argument("--device", default="0", help="Camera device index")
    cam_parser.add_argument("--width", type=int, default=1280)
    cam_parser.add_argument("--height", type=int, default=720)
    cam_parser.add_argument("--windowed", action="store_true", help="Run in windowed mode")

    # ── hud ──
    hud_parser = subparsers.add_parser("hud", help="Open real-time YOLO detection HUD")
    hud_parser.add_argument("--camera", default="0", help="Camera device index")
    hud_parser.add_argument("--width", type=int, default=1280)
    hud_parser.add_argument("--height", type=int, default=720)
    hud_parser.add_argument("--fullscreen", action="store_true")
    hud_parser.add_argument("--model", default="yolov8n.pt")
    hud_parser.add_argument("--conf", type=float, default=0.5)
    hud_parser.add_argument("--iou", type=float, default=0.45)
    hud_parser.add_argument("--no-yolo", action="store_true", help="Disable YOLO detection")
    hud_parser.add_argument("--detection-interval", type=int, default=1)
    hud_parser.add_argument("--low-latency", action="store_true")

    # ── vision ──
    subparsers.add_parser("vision", help="Open vision viewer window")

    # ── logs ──
    logs_parser = subparsers.add_parser("logs", help="View interaction logs")
    logs_parser.add_argument("--all", action="store_true", help="Show all log files")
    logs_parser.add_argument("--summary", action="store_true", help="Show summary statistics")
    logs_parser.add_argument("--date", help="Show logs for specific date (YYYY-MM-DD)")

    # ── list-cameras ──
    subparsers.add_parser("list-cameras", help="List available cameras")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return

    commands = {
        "assistant": cmd_assistant,
        "camera": cmd_camera,
        "hud": cmd_hud,
        "vision": cmd_vision,
        "logs": cmd_logs,
        "list-cameras": cmd_list_cameras,
    }

    handler = commands.get(args.command)
    if handler:
        handler(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
