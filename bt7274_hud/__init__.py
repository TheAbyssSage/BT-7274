"""BT-7274 Camera Stream package."""

try:
    from bt7274_hud.hud_window import CameraWindow
    __all__ = ["CameraWindow"]
except ImportError:
    CameraWindow = None  # type: ignore[assignment]
    __all__ = []