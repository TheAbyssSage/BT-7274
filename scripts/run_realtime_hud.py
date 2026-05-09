#!/usr/bin/env python3
"""BT-7274 Real-Time YOLO HUD — delegates to unified CLI.

Usage:
    python run_realtime_hud.py
    python run_realtime_hud.py --camera 1 --fullscreen
"""

from bt7274.cli import main as cli_main
import sys

if __name__ == "__main__":
    sys.argv = ["bt7274", "hud"] + sys.argv[1:]
    cli_main()
