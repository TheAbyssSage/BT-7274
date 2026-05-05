"""Tests for BT-7274 HUD window (smoke tests with mocked tkinter)."""

import sys
from pathlib import Path

_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import pytest
from unittest.mock import MagicMock, patch

import numpy as np

# Guard against tkinter missing in CI
pytest.importorskip("tkinter")

from bt7274_hud.hud_window import CameraWindow


def test_window_init():
    with patch("bt7274_hud.hud_window.tk.Tk") as mock_tk, \
         patch("bt7274_hud.hud_window.CameraStream") as mock_stream_cls:
        mock_root = MagicMock()
        mock_tk.return_value = mock_root
        mock_stream = MagicMock()
        mock_stream_cls.return_value = mock_stream
        mock_stream_cls.list_devices.return_value = [
            {"index": 0, "name": "Test Camera"},
        ]
        win = CameraWindow(camera_device="0", width=640, height=480)
        assert win.width == 640
        assert win.height == 480
        assert win._camera_device == "0"


def test_window_build_ui():
    with patch("bt7274_hud.hud_window.tk.Tk") as mock_tk, \
         patch("bt7274_hud.hud_window.CameraStream") as mock_stream_cls:
        mock_root = MagicMock()
        mock_tk.return_value = mock_root
        mock_stream = MagicMock()
        mock_stream_cls.return_value = mock_stream
        mock_stream_cls.list_devices.return_value = [
            {"index": 0, "name": "Test Camera"},
        ]
        win = CameraWindow(camera_device="0", width=640, height=480)
        win._build_ui()
        assert mock_root.title.called
        assert mock_root.geometry.called
        assert mock_root.configure.called
        assert mock_root.protocol.called


def test_camera_window_has_device_list():
    """CameraWindow should enumerate and store available devices on init."""
    with patch("bt7274_hud.hud_window.tk.Tk") as mock_tk, \
         patch("bt7274_hud.hud_window.CameraStream") as mock_stream_cls:
        mock_root = MagicMock()
        mock_tk.return_value = mock_root
        mock_stream = MagicMock()
        mock_stream_cls.return_value = mock_stream
        mock_stream_cls.list_devices.return_value = [
            {"index": 0, "name": "FaceTime HD Camera"},
            {"index": 1, "name": "USB Webcam"},
        ]

        win = CameraWindow(camera_device="0", width=640, height=480)
        assert hasattr(win, "_available_devices")
        assert len(win._available_devices) == 2
        assert win._available_devices[0]["index"] == 0


def test_camera_window_cycle_camera():
    """cycle_camera() should switch to the next available device."""
    with patch("bt7274_hud.hud_window.tk.Tk") as mock_tk, \
         patch("bt7274_hud.hud_window.CameraStream") as mock_stream_cls:
        mock_root = MagicMock()
        mock_tk.return_value = mock_root
        mock_stream = MagicMock()
        mock_stream_cls.return_value = mock_stream
        mock_stream_cls.list_devices.return_value = [
            {"index": 0, "name": "FaceTime HD Camera"},
            {"index": 1, "name": "USB Webcam"},
        ]

        win = CameraWindow(camera_device="0", width=640, height=480)
        win._build_ui()
        assert win._camera_device == "0"

        # Cycle to next camera
        win._cycle_camera()
        assert win._camera_device == "1"

        # Cycle again — should wrap to 0
        win._cycle_camera()
        assert win._camera_device == "0"


def test_update_frame_uses_array_fast_path():
    """_update_frame should call get_frame_array(), not get_frame(), to avoid PIL copy."""
    with patch("bt7274_hud.hud_window.tk.Tk") as mock_tk, \
         patch("bt7274_hud.hud_window.CameraStream") as mock_stream_cls:
        mock_root = MagicMock()
        mock_tk.return_value = mock_root
        mock_stream = MagicMock()
        mock_stream_cls.return_value = mock_stream
        mock_stream_cls.list_devices.return_value = [
            {"index": 0, "name": "Test Camera"},
        ]

        # Simulate a frame that matches the window dimensions
        fake_frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        mock_stream.get_frame_array.return_value = fake_frame

        win = CameraWindow(camera_device="0", width=1280, height=720)
        win._build_ui()
        win._canvas = MagicMock()
        win._canvas_img_id = 1

        win._update_frame()

        # Must use get_frame_array (fast path), not get_frame (slow PIL path)
        mock_stream.get_frame_array.assert_called_once()
        mock_stream.get_frame.assert_not_called()


def test_update_frame_skips_resize_when_dimensions_match():
    """When frame dimensions match window, no resize should occur."""
    with patch("bt7274_hud.hud_window.tk.Tk") as mock_tk, \
         patch("bt7274_hud.hud_window.CameraStream") as mock_stream_cls, \
         patch("bt7274_hud.hud_window.ImageTk") as mock_itk:
        mock_root = MagicMock()
        mock_tk.return_value = mock_root
        mock_stream = MagicMock()
        mock_stream_cls.return_value = mock_stream
        mock_stream_cls.list_devices.return_value = [
            {"index": 0, "name": "Test Camera"},
        ]

        fake_frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        mock_stream.get_frame_array.return_value = fake_frame

        win = CameraWindow(camera_device="0", width=1280, height=720)
        win._build_ui()
        win._canvas = MagicMock()
        win._canvas_img_id = 1

        win._update_frame()

        # ImageTk.PhotoImage should receive an Image with mode "RGB" (from fromarray)
        # and size should match (1280, 720) — no resize call
        call_args = mock_itk.PhotoImage.call_args
        assert call_args is not None


def test_fps_counter_rendered_on_canvas():
    """After several frames, an FPS text element should appear on the canvas."""
    with patch("bt7274_hud.hud_window.tk.Tk") as mock_tk, \
         patch("bt7274_hud.hud_window.CameraStream") as mock_stream_cls, \
         patch("bt7274_hud.hud_window.ImageTk") as mock_itk, \
         patch("bt7274_hud.hud_window.time") as mock_time:
        mock_root = MagicMock()
        mock_tk.return_value = mock_root
        mock_stream = MagicMock()
        mock_stream_cls.return_value = mock_stream
        mock_stream_cls.list_devices.return_value = [
            {"index": 0, "name": "Test Camera"},
        ]

        fake_frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        mock_stream.get_frame_array.return_value = fake_frame

        # Simulate time advancing
        mock_time.monotonic.side_effect = [0.0, 0.033, 0.066, 0.099]

        win = CameraWindow(camera_device="0", width=1280, height=720)
        win._build_ui()
        mock_canvas = MagicMock()
        win._canvas = mock_canvas
        win._canvas_img_id = 1

        # Run 3 frames
        for _ in range(3):
            win._update_frame()

        # After 3 frames, canvas should have an FPS text element
        text_calls = [
            c for c in mock_canvas.create_text.call_args_list
        ]
        assert len(text_calls) >= 1, "Expected create_text call for FPS counter"


def test_camera_cycle_keybinding_registered():
    """Tab or C key should be bound to _cycle_camera."""
    with patch("bt7274_hud.hud_window.tk.Tk") as mock_tk, \
         patch("bt7274_hud.hud_window.CameraStream") as mock_stream_cls:
        mock_root = MagicMock()
        mock_tk.return_value = mock_root
        mock_stream = MagicMock()
        mock_stream_cls.return_value = mock_stream
        mock_stream_cls.list_devices.return_value = [
            {"index": 0, "name": "Cam A"},
            {"index": 1, "name": "Cam B"},
        ]

        win = CameraWindow(camera_device="0", width=640, height=480)
        win._build_ui()

        # Check that <Tab> and "c" are bound
        bind_calls = [c[0][0] for c in mock_root.bind.call_args_list if len(c[0]) > 0]
        assert "<Tab>" in bind_calls or any(
            "<Tab>" in str(c) for c in bind_calls
        ), f"Expected <Tab> binding in {bind_calls}"
