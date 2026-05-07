#!/usr/bin/env python3
"""BT-7274 Camera Stream — delegates to unified CLI.

Usage:
    python hud_launcher.py
    python hud_launcher.py --windowed
    python hud_launcher.py --device 1
"""

from bt7274.cli import main as cli_main
import sys

if __name__ == "__main__":
    sys.argv = ["bt7274", "camera"] + sys.argv[1:]
    cli_main()
