#!/usr/bin/env python3
"""BT-7274 Vision Viewer — delegates to unified CLI."""

from bt7274.cli import main as cli_main
import sys

if __name__ == "__main__":
    sys.argv = ["bt7274", "vision"] + sys.argv[1:]
    cli_main()
