"""Tests for BT-7274 TerminalLogBuffer."""

import sys
from pathlib import Path

_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import time
import pytest
from bt7274_hud.terminal_log import TerminalLogBuffer, LogLine


class TestLogLine:
    def test_log_line_creation(self):
        line = LogLine(text="[OK] Systems online", level="INFO")
        assert line.text == "[OK] Systems online"
        assert line.level == "INFO"
        assert line.timestamp > 0

    def test_log_line_default_level(self):
        line = LogLine(text="Some output")
        assert line.level == "INFO"

    def test_log_line_age(self):
        line = LogLine(text="test", timestamp=time.monotonic() - 5)
        assert line.age_seconds >= 4.9


class TestTerminalLogBuffer:
    def test_initial_state_empty(self):
        buf = TerminalLogBuffer(max_lines=10)
        assert len(buf.get_visible(10)) == 0

    def test_add_line_appends(self):
        buf = TerminalLogBuffer(max_lines=10)
        buf.add("Line 1")
        buf.add("Line 2")
        visible = buf.get_visible(10)
        assert len(visible) == 2
        assert visible[0].text == "Line 1"
        assert visible[1].text == "Line 2"

    def test_add_line_with_level(self):
        buf = TerminalLogBuffer(max_lines=10)
        buf.add("[OK] Done", level="SUCCESS")
        visible = buf.get_visible(10)
        assert visible[0].level == "SUCCESS"

    def test_max_lines_truncates_oldest(self):
        buf = TerminalLogBuffer(max_lines=5)
        for i in range(10):
            buf.add(f"Line {i}")
        visible = buf.get_visible(10)
        assert len(visible) == 5
        assert visible[0].text == "Line 5"
        assert visible[-1].text == "Line 9"

    def test_get_visible_respects_count(self):
        buf = TerminalLogBuffer(max_lines=20)
        for i in range(10):
            buf.add(f"Line {i}")
        visible = buf.get_visible(3)
        assert len(visible) == 3
        assert visible[0].text == "Line 7"
        assert visible[-1].text == "Line 9"

    def test_clear_empties_buffer(self):
        buf = TerminalLogBuffer(max_lines=10)
        buf.add("test")
        buf.clear()
        assert len(buf.get_visible(10)) == 0

    def test_add_multiline_splits_on_newlines(self):
        buf = TerminalLogBuffer(max_lines=20)
        buf.add("Line A\nLine B\nLine C")
        visible = buf.get_visible(10)
        assert len(visible) == 3
        assert visible[0].text == "Line A"
        assert visible[1].text == "Line B"
        assert visible[2].text == "Line C"

    def test_add_multiline_respects_max_lines(self):
        buf = TerminalLogBuffer(max_lines=3)
        buf.add("A\nB\nC\nD\nE")
        visible = buf.get_visible(10)
        assert len(visible) == 3
        assert visible[0].text == "C"
        assert visible[-1].text == "E"
