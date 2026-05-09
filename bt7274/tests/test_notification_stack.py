"""Tests for BT-7274 NotificationStack."""

import sys
from pathlib import Path

_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import time
import pytest
from bt7274.bt7274_hud.notification_stack import NotificationStack, StackedNotification


class TestStackedNotification:
    def test_creation(self):
        sn = StackedNotification(text="VPN enabled", category="SYS")
        assert sn.text == "VPN enabled"
        assert sn.category == "SYS"
        assert sn.alpha == 1.0
        assert not sn.expired

    def test_expiry(self):
        sn = StackedNotification(text="test", ttl=0.01)
        time.sleep(0.02)
        assert sn.expired

    def test_alpha_fade_in_last_second(self):
        sn = StackedNotification(text="test", ttl=1.5)
        time.sleep(0.6)
        alpha = sn.alpha
        assert 0.5 < alpha < 1.0

    def test_alpha_zero_when_expired(self):
        sn = StackedNotification(text="test", ttl=0.001)
        time.sleep(0.01)
        assert sn.alpha == 0.0


class TestNotificationStack:
    def test_initial_state_empty(self):
        stack = NotificationStack(max_visible=5)
        assert len(stack.get_visible()) == 0

    def test_push_adds_to_bottom(self):
        stack = NotificationStack(max_visible=5)
        stack.push("First notification")
        stack.push("Second notification")
        visible = stack.get_visible()
        assert len(visible) == 2
        assert visible[0].text == "First notification"
        assert visible[1].text == "Second notification"

    def test_push_with_category(self):
        stack = NotificationStack(max_visible=5)
        stack.push("Battery low", category="WARN")
        visible = stack.get_visible()
        assert visible[0].category == "WARN"

    def test_max_visible_pushes_oldest_out(self):
        stack = NotificationStack(max_visible=3)
        for i in range(6):
            stack.push(f"Note {i}")
        visible = stack.get_visible()
        assert len(visible) == 3
        assert visible[0].text == "Note 3"
        assert visible[-1].text == "Note 5"

    def test_tick_removes_expired(self):
        stack = NotificationStack(max_visible=5)
        stack.push("Permanent note", ttl=60)
        stack.push("Fleeting note", ttl=0.001)
        time.sleep(0.01)
        stack.tick()
        visible = stack.get_visible()
        assert len(visible) == 1
        assert visible[0].text == "Permanent note"

    def test_get_visible_returns_newest_at_bottom(self):
        stack = NotificationStack(max_visible=5)
        stack.push("A")
        stack.push("B")
        stack.push("C")
        visible = stack.get_visible()
        assert visible[0].text == "A"
        assert visible[1].text == "B"
        assert visible[2].text == "C"

    def test_clear_empties_stack(self):
        stack = NotificationStack(max_visible=5)
        stack.push("test")
        stack.clear()
        assert len(stack.get_visible()) == 0
