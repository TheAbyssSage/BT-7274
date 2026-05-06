"""Notification stack manager for BT-7274 HUD bottom-right box.

Notifications appear at the bottom and push older ones upward.  A maximum
of 5-7 are visible at once.  Each notification fades out over its final
second of life, then is removed.
"""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import List


@dataclass(slots=True)
class StackedNotification:
    """A single notification in the bottom-right stack.

    Parameters
    ----------
    text:
        Display text (truncated to ~50 chars by the renderer).
    category:
        Tag used for colour coding: ``"SYS"``, ``"WARN"``, ``"ERR"``,
        ``"OK"``, or any freeform string.
    ttl:
        Lifetime in seconds.  Fade-out begins in the final 1.0 s.
    """
    text: str
    category: str = "SYS"
    ttl: float = 6.0
    created_at: float = field(default_factory=time.monotonic)

    @property
    def age(self) -> float:
        return time.monotonic() - self.created_at

    @property
    def expired(self) -> bool:
        return self.age >= self.ttl

    @property
    def alpha(self) -> float:
        """0.0 → 1.0.  Full opacity until the final second, then linear fade."""
        remaining = self.ttl - self.age
        if remaining <= 0:
            return 0.0
        if remaining >= 1.0:
            return 1.0
        return remaining  # linear 1.0 → 0.0 in last second


class NotificationStack:
    """Ordered stack of ``StackedNotification`` items.

    New items are pushed onto the **bottom** (end of the list).  The
    renderer draws them bottom-up so the newest appears at the bottom of
    the screen and older items float upward.

    Parameters
    ----------
    max_visible:
        Maximum number of notifications shown at once.  When exceeded, the
        oldest (top-most) notification is dropped.
    """

    def __init__(self, max_visible: int = 6):
        self._max_visible = max_visible
        self._items: deque[StackedNotification] = deque()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def push(self, text: str, category: str = "SYS", ttl: float = 6.0) -> None:
        """Add a notification to the bottom of the stack."""
        self._items.append(StackedNotification(text=text, category=category, ttl=ttl))
        # Trim from the top (oldest) if over capacity
        while len(self._items) > self._max_visible:
            self._items.popleft()

    def tick(self) -> None:
        """Remove all expired notifications.  Call once per frame."""
        while self._items and self._items[0].expired:
            self._items.popleft()
        # Also sweep any expired items that aren't at the front
        self._items = deque(n for n in self._items if not n.expired)

    def get_visible(self) -> List[StackedNotification]:
        """Return all currently visible notifications, oldest first."""
        return list(self._items)

    def clear(self) -> None:
        """Remove all notifications."""
        self._items.clear()

    def __len__(self) -> int:
        return len(self._items)
