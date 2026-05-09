"""BT-7274 Voice Assistant - Pipeline Package.

Re-exports BT7274Assistant for backward compatibility.
"""

import sys
from pathlib import Path

# Ensure bt7274_assistant/ and project root are on sys.path for sibling imports
_pkg = Path(__file__).parent
if str(_pkg) not in sys.path:
    sys.path.insert(0, str(_pkg))
if str(_pkg.parent) not in sys.path:
    sys.path.insert(0, str(_pkg.parent))

from bt7274.bt7274_assistant.pipeline.core import BT7274Assistant

__all__ = ["BT7274Assistant"]
