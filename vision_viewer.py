#!/usr/bin/env python3
"""
BT-7274 Vision Viewer — Standalone launcher.

Opens a window showing what BT-7274's optical sensors see.
"""

import sys
from pathlib import Path

# Ensure project root is on sys.path
_project_root = Path(__file__).parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from bt7274_perception.vision_viewer import main

if __name__ == "__main__":
    main()
