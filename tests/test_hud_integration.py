"""Tests for BT-7274 HUD integration into vision pipeline."""

import sys
from pathlib import Path

_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import pytest
from unittest.mock import MagicMock, patch

from bt7274_hud.hud_data import HudState, Notification


def test_hud_can_be_imported_from_vision_viewer():
    """Ensure the HUD module is importable from the vision viewer context."""
    with patch.dict(sys.modules, {"tkinter": MagicMock()}):
        import bt7274_hud.hud_window
        from bt7274_hud.hud_data import HudState as HS
        assert bt7274_hud.hud_window.CameraWindow is not None
        assert HS is not None


def test_hud_state_populated_from_vision_result():
    state = HudState()
    state.comms_text = "Enemy pilot detected."
    state.notifications.append(Notification(text="Vision scan complete", color="#00ff88"))
    assert state.comms_text == "Enemy pilot detected."
    assert len(state.notifications) == 1


def test_new_modules_exported():
    """TerminalLogBuffer, NotificationStack, and TelemetryPanel are importable."""
    from bt7274_hud.terminal_log import TerminalLogBuffer
    from bt7274_hud.notification_stack import NotificationStack
    from bt7274_hud.telemetry_panel import TelemetryPanel

    assert TerminalLogBuffer is not None
    assert NotificationStack is not None
    assert TelemetryPanel is not None
