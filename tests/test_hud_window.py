"""Tests for BT-7274 HUD window (smoke tests with mocked tkinter)."""

import sys
from pathlib import Path

_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import pytest
from unittest.mock import MagicMock, patch

# Guard against tkinter missing in CI
pytest.importorskip("tkinter")

from bt7274_hud.hud_window import PilotHudWindow


def test_window_init():
    with patch("bt7274_hud.hud_window.tk.Tk") as mock_tk:
        mock_root = MagicMock()
        mock_tk.return_value = mock_root
        win = PilotHudWindow(camera_device="0", width=640, height=480)
        assert win.width == 640
        assert win.height == 480
        assert win._camera_device == "0"


def test_window_build_ui():
    with patch("bt7274_hud.hud_window.tk.Tk") as mock_tk:
        mock_root = MagicMock()
        mock_tk.return_value = mock_root
        win = PilotHudWindow(camera_device="0", width=640, height=480)
        win._build_ui()
        assert mock_root.title.called
        assert mock_root.geometry.called
        assert mock_root.configure.called
        assert mock_root.protocol.called
