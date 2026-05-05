"""BT-7274 Camera Stream package."""

try:
    from bt7274_hud.hud_window import CameraWindow
    from bt7274_hud.terminal_log import TerminalLogBuffer, LogLine
    from bt7274_hud.notification_stack import NotificationStack, StackedNotification
    from bt7274_hud.telemetry_panel import TelemetryPanel, TelemetrySnapshot
    __all__ = [
        "CameraWindow",
        "TerminalLogBuffer",
        "LogLine",
        "NotificationStack",
        "StackedNotification",
        "TelemetryPanel",
        "TelemetrySnapshot",
    ]
except ImportError:
    CameraWindow = None  # type: ignore[assignment]
    TerminalLogBuffer = None  # type: ignore[assignment]
    LogLine = None  # type: ignore[assignment]
    NotificationStack = None  # type: ignore[assignment]
    StackedNotification = None  # type: ignore[assignment]
    TelemetryPanel = None  # type: ignore[assignment]
    TelemetrySnapshot = None  # type: ignore[assignment]
    __all__ = []