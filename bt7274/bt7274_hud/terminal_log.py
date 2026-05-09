"""Terminal log ring buffer for BT-7274 HUD bottom-left box.

Captures assistant terminal output lines with timestamps and severity levels.
The HUD window reads the most recent N lines each frame.
"""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import List


@dataclass(slots=True)
class LogLine:
    """A single line of terminal-style output."""
    text: str
    level: str = "INFO"          # "INFO", "SUCCESS", "WARN", "ERROR"
    timestamp: float = field(default_factory=time.monotonic)

    @property
    def age_seconds(self) -> float:
        """Seconds since this line was created."""
        return time.monotonic() - self.timestamp


class TerminalLogBuffer:
    """Fixed-size ring buffer of LogLine entries.

    Thread-safe for a single producer (assistant) and single consumer (HUD
    render loop).  Not locked — relies on the GIL for append + read of
    small objects.

    Parameters
    ----------
    max_lines:
        Maximum number of lines retained in the buffer.  Oldest lines are
        dropped when the buffer overflows.
    """

    def __init__(self, max_lines: int = 200):
        self._max_lines = max_lines
        self._buffer: deque[LogLine] = deque(maxlen=max_lines)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add(self, text: str, level: str = "INFO") -> None:
        """Append one or more lines (splits on ``\\n``).

        Each physical line becomes a separate ``LogLine`` with the same
        *level* and timestamp.
        """
        for raw_line in text.split("\n"):
            stripped = raw_line.rstrip("\r")
            if stripped:
                self._buffer.append(LogLine(text=stripped, level=level))

    def get_visible(self, count: int) -> List[LogLine]:
        """Return the most recent *count* lines, oldest first."""
        if count <= 0:
            return []
        items = list(self._buffer)
        return items[-count:] if len(items) > count else items

    def clear(self) -> None:
        """Empty the buffer."""
        self._buffer.clear()

    def __len__(self) -> int:
        return len(self._buffer)
