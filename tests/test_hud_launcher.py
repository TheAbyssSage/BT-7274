"""Tests for BT-7274 HUD launcher importability."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))


def test_launcher_imports():
    # Ensure the launcher module can be imported without running tkinter
    with patch.dict(sys.modules, {"tkinter": MagicMock()}):
        import hud_launcher
        assert hasattr(hud_launcher, "main")
