"""
Camera capture for BT-7274 Perception.

Uses ffmpeg (macOS AVFoundation) to capture frames from the default camera.
No heavy dependencies — just ffmpeg and numpy.
"""

import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional

import numpy as np


class CameraCapture:
    """Capture frames from the system camera using ffmpeg."""

    def __init__(
        self,
        device: str = "0",          # AVFoundation device index (0 = default FaceTime HD)
        width: int = 640,
        height: int = 480,
        fps: int = 30,              # macOS FaceTime HD supports 30fps
        timeout: float = 5.0,       # Seconds to wait for ffmpeg
    ):
        self.device = device
        self.width = width
        self.height = height
        self.fps = fps
        self.timeout = timeout
        self._last_frame_path: Optional[str] = None
        self._last_capture_time: float = 0.0

    def _build_ffmpeg_cmd(self, output_path: str) -> list[str]:
        """Build ffmpeg command for single-frame capture on macOS."""
        return [
            "ffmpeg",
            "-y",                       # Overwrite output
            "-f", "avfoundation",
            "-video_size", f"{self.width}x{self.height}",
            "-framerate", str(self.fps),
            "-i", self.device,          # e.g. "0" for FaceTime HD
            "-frames:v", "1",           # Single frame
            "-pix_fmt", "rgb24",
            "-f", "image2",
            output_path,
        ]

    def capture(self, output_path: Optional[str] = None) -> Optional[str]:
        """
        Capture a single frame from the camera.

        Args:
            output_path: Where to save the frame. If None, uses a temp file.

        Returns:
            Absolute path to the captured image, or None on failure.
        """
        if output_path is None:
            fd, output_path = tempfile.mkstemp(suffix=".png", prefix="bt_vision_")
            os.close(fd)

        output_path = str(Path(output_path).resolve())
        cmd = self._build_ffmpeg_cmd(output_path)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
            if result.returncode != 0:
                # ffmpeg often writes warnings to stderr even on success;
                # treat non-zero as failure but log stderr for debugging.
                return None

            if not Path(output_path).exists() or Path(output_path).stat().st_size == 0:
                return None

            self._last_frame_path = output_path
            self._last_capture_time = time.time()
            return output_path

        except subprocess.TimeoutExpired:
            return None
        except FileNotFoundError:
            # ffmpeg not installed
            return None
        except Exception:
            return None

    def capture_to_bytes(self) -> Optional[bytes]:
        """
        Capture a frame and return raw PNG bytes.

        Returns:
            PNG image bytes, or None on failure.
        """
        path = self.capture()
        if path is None:
            return None
        try:
            with open(path, "rb") as f:
                data = f.read()
            return data
        except Exception:
            return None
        finally:
            # Clean up temp file
            try:
                os.remove(path)
            except Exception:
                pass

    def get_last_frame_path(self) -> Optional[str]:
        """Return path to the most recently captured frame."""
        return self._last_frame_path

    @staticmethod
    def list_devices() -> list[dict]:
        """
        List available AVFoundation video devices.

        Returns:
            List of dicts with 'index' and 'name' keys.
        """
        devices = []
        try:
            result = subprocess.run(
                [
                    "ffmpeg",
                    "-f", "avfoundation",
                    "-list_devices", "true",
                    "-i", "",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            # ffmpeg writes device list to stderr
            output = result.stderr or ""
            in_video_section = False
            for line in output.splitlines():
                if "AVFoundation video devices:" in line:
                    in_video_section = True
                    continue
                if "AVFoundation audio devices:" in line:
                    break
                if not in_video_section:
                    continue
                # Parse lines like: [AVFoundation indev @ 0x...] [0] FaceTime HD Camera
                # We need the second bracket group: [0]
                bracket_parts = []
                rest = line
                while True:
                    start = rest.find("[")
                    if start == -1:
                        break
                    end = rest.find("]", start)
                    if end == -1:
                        break
                    bracket_parts.append(rest[start + 1:end])
                    rest = rest[end + 1:]
                # bracket_parts = ['AVFoundation indev @ 0x...', '0', ...]
                if len(bracket_parts) >= 2:
                    idx = bracket_parts[-1].strip()
                    name = rest.strip()
                    if idx.isdigit() and name:
                        devices.append({"index": idx, "name": name})
        except Exception:
            pass
        return devices
