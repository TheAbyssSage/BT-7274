"""Tests for BT-7274 RealtimeHudWindow."""

import sys
from pathlib import Path

_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import pytest
import unittest.mock
from unittest.mock import MagicMock, patch

pytest.importorskip("tkinter")

from bt7274_hud.realtime_hud_window import RealtimeHudWindow


class TestRealtimeHudWindow:
    def test_init(self):
        with patch("bt7274_hud.realtime_hud_window.tk.Tk") as mock_tk, \
             patch("bt7274_hud.realtime_hud_window.RealtimeVision") as mock_rv:
            mock_root = MagicMock()
            mock_tk.return_value = mock_root
            mock_vision = MagicMock()
            mock_vision.is_running = False
            mock_rv.return_value = mock_vision

            win = RealtimeHudWindow(
                camera_device="0", width=640, height=480,
            )
            assert win.width == 640
            assert win.height == 480

    def test_build_ui_configures_window(self):
        with patch("bt7274_hud.realtime_hud_window.tk.Tk") as mock_tk, \
             patch("bt7274_hud.realtime_hud_window.RealtimeVision") as mock_rv:
            mock_root = MagicMock()
            mock_tk.return_value = mock_root
            mock_vision = MagicMock()
            mock_vision.is_running = False
            mock_rv.return_value = mock_vision

            win = RealtimeHudWindow(
                camera_device="0", width=640, height=480,
            )
            win._build_ui()
            assert mock_root.title.called
            assert mock_root.geometry.called
            assert mock_root.protocol.called

    def test_stop_cleans_up(self):
        with patch("bt7274_hud.realtime_hud_window.tk.Tk") as mock_tk, \
             patch("bt7274_hud.realtime_hud_window.RealtimeVision") as mock_rv:
            mock_root = MagicMock()
            mock_tk.return_value = mock_root
            mock_vision = MagicMock()
            mock_vision.is_running = True
            mock_rv.return_value = mock_vision

            win = RealtimeHudWindow(
                camera_device="0", width=640, height=480,
            )
            win._build_ui()
            win.stop()
            # stop() schedules _on_close via after(0, ...) — verify it was queued
            mock_root.after.assert_called_once_with(0, win._on_close)
            # Now simulate what the event loop would do: call _on_close directly
            win._on_close()
            mock_vision.stop.assert_called_once()

    def test_fullscreen_mode(self):
        with patch("bt7274_hud.realtime_hud_window.tk.Tk") as mock_tk, \
             patch("bt7274_hud.realtime_hud_window.RealtimeVision") as mock_rv:
            mock_root = MagicMock()
            mock_tk.return_value = mock_root
            mock_vision = MagicMock()
            mock_vision.is_running = False
            mock_rv.return_value = mock_vision

            win = RealtimeHudWindow(
                camera_device="0", width=640, height=480, fullscreen=True,
            )
            win._build_ui()
            mock_root.attributes.assert_any_call("-fullscreen", True)

    def test_camera_switch_keybinding_registered(self):
        with patch("bt7274_hud.realtime_hud_window.tk.Tk") as mock_tk, \
             patch("bt7274_hud.realtime_hud_window.RealtimeVision") as mock_rv:
            mock_root = MagicMock()
            mock_tk.return_value = mock_root
            mock_vision = MagicMock()
            mock_vision.is_running = False
            mock_rv.return_value = mock_vision

            win = RealtimeHudWindow(
                camera_device="0", width=640, height=480,
            )
            win._build_ui()
            # Tab and C should be bound for camera cycling
            mock_root.bind.assert_any_call("<Tab>", unittest.mock.ANY)
            mock_root.bind.assert_any_call("c", unittest.mock.ANY)

    def test_fps_text_drawn_on_canvas(self):
        with patch("bt7274_hud.realtime_hud_window.tk.Tk") as mock_tk, \
             patch("bt7274_hud.realtime_hud_window.RealtimeVision") as mock_rv:
            mock_root = MagicMock()
            mock_tk.return_value = mock_root
            mock_vision = MagicMock()
            mock_vision.is_running = False
            mock_rv.return_value = mock_vision

            win = RealtimeHudWindow(
                camera_device="0", width=640, height=480,
            )
            win._build_ui()
            # Verify the canvas and FPS tracking were set up
            assert win._canvas is not None
            assert win._fps_text_id is None  # not drawn until first frame
            assert len(win._frame_times) == 0  # no frames yet

    def test_fullscreen_mode(self):
        with patch("bt7274_hud.realtime_hud_window.tk.Tk") as mock_tk, \
             patch("bt7274_hud.realtime_hud_window.RealtimeVision") as mock_rv:
            mock_root = MagicMock()
            mock_tk.return_value = mock_root
            mock_vision = MagicMock()
            mock_vision.is_running = False
            mock_rv.return_value = mock_vision

            win = RealtimeHudWindow(
                camera_device="0", width=640, height=480, fullscreen=True,
            )
            win._build_ui()
            mock_root.attributes.assert_any_call("-fullscreen", True)
