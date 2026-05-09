#!/usr/bin/env python3
"""BT-7274 Log Viewer — delegates to unified CLI.

Usage:
    python view_logs.py
    python view_logs.py --all
    python view_logs.py --summary
    python view_logs.py --date 2026-04-24
"""

from bt7274.cli import main as cli_main
import sys

if __name__ == "__main__":
    sys.argv = ["bt7274", "logs"] + sys.argv[1:]
    cli_main()
