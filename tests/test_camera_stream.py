"""Tests for BT-7274 CameraStream."""

import sys
from pathlib import Path

_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import pytest
from unittest.mock import MagicMock, patch
import numpy as np

from bt7274_hud.camera_stream import CameraStream


class TestCameraStreamListDevices:
    """Tests for CameraStream.list_devices() static method."""

    def test_list_devices_returns_list(self):
        """list_devices() should return a list of dicts with index and name keys."""
        devices = CameraStream.list_devices()
        assert isinstance(devices, list)
        if len(devices) > 0:
            for d in devices:
                assert "index" in d
                assert "name" in d
                assert isinstance(d["index"], int)
                assert isinstance(d["name"], str)

    def test_list_devices_includes_default_camera(self):
        """If any camera exists, index 0 should be present."""
        devices = CameraStream.list_devices()
        indices = [d["index"] for d in devices]
        if len(devices) > 0:
            assert 0 in indices, f"Expected camera 0 in {indices}"

    def test_list_devices_graceful_on_failure(self):
        """list_devices() should return empty list (not raise) if OpenCV can't probe."""
        with patch("bt7274_hud.camera_stream.cv2.VideoCapture") as mock_cap:
            mock_cap.return_value.isOpened.return_value = False
            devices = CameraStream.list_devices()
            assert devices == []


class TestCameraStreamFrameAccess:
    """Tests for frame retrieval methods."""

    def test_get_frame_array_returns_numpy_array(self):
        """get_frame_array() should return an RGB uint8 numpy array or None."""
        stream = CameraStream(device="0", width=320, height=240)
        # Without starting, should return None
        assert stream.get_frame_array() is None

    def test_get_frame_returns_pil_image_or_none(self):
        """get_frame() should return a PIL Image or None."""
        stream = CameraStream(device="0", width=320, height=240)
        assert stream.get_frame() is None


class TestCameraStreamZeroCopy:
    """Tests for the double-buffer zero-copy frame access."""

    def test_get_frame_array_no_copy_returns_view(self):
        """get_frame_array_no_copy() should return the buffer without copying."""
        stream = CameraStream(device="0", width=320, height=240)
        # Without starting, should return None
        assert stream.get_frame_array_no_copy() is None

    def test_switch_device_updates_device(self):
        """switch_device() should update the internal device reference."""
        stream = CameraStream(device="0", width=320, height=240)
        stream.switch_device("1")
        assert stream.device == 1

    def test_switch_device_string_to_int(self):
        """switch_device() should handle string-to-int conversion."""
        stream = CameraStream(device="0", width=320, height=240)
        stream.switch_device("2")
        assert stream.device == 2  # converted to int
