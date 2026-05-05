"""Tests for VisionViewerWindow camera preview pipeline."""

import sys
from pathlib import Path

_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import pytest
from unittest.mock import MagicMock, patch, PropertyMock

# Guard against tkinter missing in CI
pytest.importorskip("tkinter")

import numpy as np
from bt7274_perception.vision_viewer import VisionViewerWindow


class TestVisionViewerPreview:
    """Tests for the CameraStream-based preview pipeline."""

    def test_uses_camera_stream_for_preview(self):
        """VisionViewerWindow should create a CameraStream, not ffmpeg, for preview."""
        with patch("bt7274_perception.vision_viewer.tk.Tk") as mock_tk, \
             patch("bt7274_perception.vision_viewer.CameraStream") as mock_stream_cls, \
             patch("bt7274_perception.vision_viewer.VisionEngine") as mock_engine, \
             patch("bt7274_perception.vision_viewer.VisionLogger") as mock_logger:
            mock_root = MagicMock()
            mock_tk.return_value = mock_root
            mock_stream = MagicMock()
            mock_stream_cls.return_value = mock_stream

            viewer = VisionViewerWindow(camera_device="0")
            viewer._build_ui()

            # CameraStream should be created for preview
            mock_stream_cls.assert_called_once()
            # CameraStream.start() should be called when preview starts
            assert viewer._preview_stream is not None

    def test_preview_interval_is_fast(self):
        """Preview interval should be ~33ms (30 FPS), not 1000ms."""
        with patch("bt7274_perception.vision_viewer.tk.Tk") as mock_tk, \
             patch("bt7274_perception.vision_viewer.CameraStream") as mock_stream_cls, \
             patch("bt7274_perception.vision_viewer.VisionEngine") as mock_engine, \
             patch("bt7274_perception.vision_viewer.VisionLogger") as mock_logger:
            mock_root = MagicMock()
            mock_tk.return_value = mock_root
            mock_stream = MagicMock()
            mock_stream_cls.return_value = mock_stream

            viewer = VisionViewerWindow(camera_device="0")

            # Preview interval should be 33ms or less (30+ FPS)
            assert viewer.PREVIEW_INTERVAL_MS <= 33, (
                f"PREVIEW_INTERVAL_MS is {viewer.PREVIEW_INTERVAL_MS}ms, "
                f"expected <= 33ms for 30 FPS"
            )

    def test_preview_updates_from_stream_frame(self):
        """Preview should call get_frame_array() on CameraStream, not ffmpeg."""
        with patch("bt7274_perception.vision_viewer.tk.Tk") as mock_tk, \
             patch("bt7274_perception.vision_viewer.CameraStream") as mock_stream_cls, \
             patch("bt7274_perception.vision_viewer.VisionEngine") as mock_engine, \
             patch("bt7274_perception.vision_viewer.VisionLogger") as mock_logger:
            mock_root = MagicMock()
            mock_tk.return_value = mock_root
            mock_stream = MagicMock()
            mock_stream_cls.return_value = mock_stream

            # Create a fake frame
            fake_frame = np.zeros((120, 160, 3), dtype=np.uint8)
            mock_stream.get_frame_array.return_value = fake_frame

            viewer = VisionViewerWindow(camera_device="0")
            viewer._build_ui()
            viewer._preview_label = MagicMock()

            viewer._capture_preview_frame()

            # Should call get_frame_array() on the stream
            mock_stream.get_frame_array.assert_called_once()
            # Should NOT spawn ffmpeg
            # (CameraCapture is not used for preview anymore)

    def test_look_still_uses_camera_capture(self):
        """The LOOK button should still use CameraCapture (ffmpeg) for high-res."""
        with patch("bt7274_perception.vision_viewer.tk.Tk") as mock_tk, \
             patch("bt7274_perception.vision_viewer.CameraStream") as mock_stream_cls, \
             patch("bt7274_perception.vision_viewer.VisionEngine") as mock_engine, \
             patch("bt7274_perception.vision_viewer.VisionLogger") as mock_logger, \
             patch("bt7274_perception.vision_viewer.CameraCapture") as mock_cap_cls:
            mock_root = MagicMock()
            mock_tk.return_value = mock_root
            mock_stream = MagicMock()
            mock_stream_cls.return_value = mock_stream
            mock_cap = MagicMock()
            mock_cap.capture.return_value = "/tmp/test_capture.png"
            mock_cap_cls.return_value = mock_cap

            viewer = VisionViewerWindow(camera_device="0")
            viewer._build_ui()

            # The _look_camera should be a CameraCapture, not CameraStream
            assert viewer._look_camera is not None
            mock_cap_cls.assert_called()  # CameraCapture was created for LOOK

    def test_no_adaptive_interval_for_preview(self):
        """Preview should not have adaptive interval slowing — always fast."""
        with patch("bt7274_perception.vision_viewer.tk.Tk") as mock_tk, \
             patch("bt7274_perception.vision_viewer.CameraStream") as mock_stream_cls, \
             patch("bt7274_perception.vision_viewer.VisionEngine") as mock_engine, \
             patch("bt7274_perception.vision_viewer.VisionLogger") as mock_logger:
            mock_root = MagicMock()
            mock_tk.return_value = mock_root
            mock_stream = MagicMock()
            mock_stream_cls.return_value = mock_stream

            viewer = VisionViewerWindow(camera_device="0")

            # _update_adaptive_interval method should not exist or be a no-op
            # The preview should always run at PREVIEW_INTERVAL_MS
            assert not hasattr(viewer, '_update_adaptive_interval') or \
                   viewer._adaptive_interval == viewer.PREVIEW_INTERVAL_MS
