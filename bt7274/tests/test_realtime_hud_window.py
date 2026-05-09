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

from bt7274.bt7274_hud.realtime_hud_window import RealtimeHudWindow


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


class TestHudBoxes:
    def test_terminal_log_buffer_attached(self):
        with patch("bt7274_hud.realtime_hud_window.tk.Tk") as mock_tk, \
             patch("bt7274_hud.realtime_hud_window.RealtimeVision") as mock_rv:
            mock_root = MagicMock()
            mock_tk.return_value = mock_root
            mock_vision = MagicMock()
            mock_vision.is_running = False
            mock_rv.return_value = mock_vision

            win = RealtimeHudWindow(camera_device="0", width=640, height=480)
            assert win.terminal_log is not None
            assert win.notification_stack is not None
            assert win.telemetry_panel is not None

    def test_terminal_log_add_appears_in_buffer(self):
        with patch("bt7274_hud.realtime_hud_window.tk.Tk") as mock_tk, \
             patch("bt7274_hud.realtime_hud_window.RealtimeVision") as mock_rv:
            mock_root = MagicMock()
            mock_tk.return_value = mock_root
            mock_vision = MagicMock()
            mock_vision.is_running = False
            mock_rv.return_value = mock_vision

            win = RealtimeHudWindow(camera_device="0", width=640, height=480)
            win.terminal_log.add("[OK] Test message")
            visible = win.terminal_log.get_visible(10)
            assert len(visible) == 1
            assert visible[0].text == "[OK] Test message"

    def test_notification_stack_push(self):
        with patch("bt7274_hud.realtime_hud_window.tk.Tk") as mock_tk, \
             patch("bt7274_hud.realtime_hud_window.RealtimeVision") as mock_rv:
            mock_root = MagicMock()
            mock_tk.return_value = mock_root
            mock_vision = MagicMock()
            mock_vision.is_running = False
            mock_rv.return_value = mock_vision

            win = RealtimeHudWindow(camera_device="0", width=640, height=480)
            win.notification_stack.push("VPN enabled", category="OK")
            visible = win.notification_stack.get_visible()
            assert len(visible) == 1
            assert visible[0].text == "VPN enabled"

    def test_telemetry_panel_updates(self):
        with patch("bt7274_hud.realtime_hud_window.tk.Tk") as mock_tk, \
             patch("bt7274_hud.realtime_hud_window.RealtimeVision") as mock_rv:
            mock_root = MagicMock()
            mock_tk.return_value = mock_root
            mock_vision = MagicMock()
            mock_vision.is_running = False
            mock_rv.return_value = mock_vision

            win = RealtimeHudWindow(camera_device="0", width=640, height=480)
            win.telemetry_panel.update_fps(30.0)
            snap = win.telemetry_panel.snapshot()
            assert snap.fps == 30.0

    def test_draw_terminal_box_creates_canvas_elements(self):
        with patch("bt7274_hud.realtime_hud_window.tk.Tk") as mock_tk, \
             patch("bt7274_hud.realtime_hud_window.RealtimeVision") as mock_rv:
            mock_root = MagicMock()
            mock_canvas = MagicMock()
            mock_canvas.winfo_width.return_value = 640
            mock_canvas.winfo_height.return_value = 480
            mock_tk.return_value = mock_root
            mock_vision = MagicMock()
            mock_vision.is_running = False
            mock_rv.return_value = mock_vision

            win = RealtimeHudWindow(camera_device="0", width=640, height=480)
            win._canvas = mock_canvas
            win.terminal_log.add("[OK] Systems online")
            win._draw_terminal_box()
            assert mock_canvas.create_rectangle.called or mock_canvas.create_text.called

    def test_draw_notification_box_creates_canvas_elements(self):
        with patch("bt7274_hud.realtime_hud_window.tk.Tk") as mock_tk, \
             patch("bt7274_hud.realtime_hud_window.RealtimeVision") as mock_rv:
            mock_root = MagicMock()
            mock_canvas = MagicMock()
            mock_canvas.winfo_width.return_value = 640
            mock_canvas.winfo_height.return_value = 480
            mock_tk.return_value = mock_root
            mock_vision = MagicMock()
            mock_vision.is_running = False
            mock_rv.return_value = mock_vision

            win = RealtimeHudWindow(camera_device="0", width=640, height=480)
            win._canvas = mock_canvas
            win.notification_stack.push("Test notification")
            win._draw_notification_box()
            assert mock_canvas.create_rectangle.called or mock_canvas.create_text.called

    def test_draw_telemetry_box_creates_canvas_elements(self):
        with patch("bt7274_hud.realtime_hud_window.tk.Tk") as mock_tk, \
             patch("bt7274_hud.realtime_hud_window.RealtimeVision") as mock_rv:
            mock_root = MagicMock()
            mock_canvas = MagicMock()
            mock_canvas.winfo_width.return_value = 640
            mock_canvas.winfo_height.return_value = 480
            mock_tk.return_value = mock_root
            mock_vision = MagicMock()
            mock_vision.is_running = False
            mock_rv.return_value = mock_vision

            win = RealtimeHudWindow(camera_device="0", width=640, height=480)
            win._canvas = mock_canvas
            win.telemetry_panel.update_fps(30.0)
            win._draw_telemetry_box()
            assert mock_canvas.create_rectangle.called or mock_canvas.create_text.called

    def test_log_terminal_convenience(self):
        with patch("bt7274_hud.realtime_hud_window.tk.Tk") as mock_tk, \
             patch("bt7274_hud.realtime_hud_window.RealtimeVision") as mock_rv:
            mock_root = MagicMock()
            mock_tk.return_value = mock_root
            mock_vision = MagicMock()
            mock_vision.is_running = False
            mock_rv.return_value = mock_vision

            win = RealtimeHudWindow(camera_device="0", width=640, height=480)
            win.log_terminal("[OK] Audio stream active", level="SUCCESS")
            visible = win.terminal_log.get_visible(10)
            assert visible[0].text == "[OK] Audio stream active"
            assert visible[0].level == "SUCCESS"

    def test_notify_convenience(self):
        with patch("bt7274_hud.realtime_hud_window.tk.Tk") as mock_tk, \
             patch("bt7274_hud.realtime_hud_window.RealtimeVision") as mock_rv:
            mock_root = MagicMock()
            mock_tk.return_value = mock_root
            mock_vision = MagicMock()
            mock_vision.is_running = False
            mock_rv.return_value = mock_vision

            win = RealtimeHudWindow(camera_device="0", width=640, height=480)
            win.notify("VPN connected", category="OK")
            visible = win.notification_stack.get_visible()
            assert visible[0].text == "VPN connected"
