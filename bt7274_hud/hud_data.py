"""
HUD data model — BT-7274 Pilot HUD
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Upgrades over v1:
  • ``AbilitySlot`` enum-based sizing (MAIN / TACTICAL / PASSIVE) replaces
    implicit ordering; renderer can query size from the enum directly
  • ``CommsState`` captures richer transmission metadata (speaker portrait
    path, signal strength, channel, timestamp)
  • ``VitalState`` adds health + shield + titan-link integrity bars so the
    renderer can draw the bottom status cluster properly
  • ``EventCard`` promotes bare strings to typed objects with category,
    colour, and a TTL so cards auto-expire
  • ``HudState`` exposes a convenience ``tick(dt)`` method that ages TTLs
    and prunes expired items — call it once per frame from the render loop
  • ``Marker`` gains a ``heading`` field (degrees) for directional icons
  • All dataclasses are ``slots=True`` for slightly lower per-instance cost
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List, Optional


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class MarkerKind(str, Enum):
    ALLY      = "ally"
    THREAT    = "threat"
    OBJECTIVE = "objective"
    WAYPOINT  = "waypoint"


class AbilitySize(Enum):
    """Controls the rendered circle diameter."""
    MAIN     = auto()   # dominant central icon  (e.g. 54 px)
    TACTICAL = auto()   # medium secondary icon  (e.g. 36 px)
    PASSIVE  = auto()   # small utility icon     (e.g. 28 px)


class CardCategory(str, Enum):
    INFO    = "info"     # neutral white/blue
    SUCCESS = "success"  # green — objective complete, target locked
    WARNING = "warning"  # amber — low ammo, threat detected
    DANGER  = "danger"   # red   — taking damage, system failure


class SystemStatus(str, Enum):
    ONLINE   = "ONLINE"
    DEGRADED = "DEGRADED"
    OFFLINE  = "OFFLINE"


class StatusIconKind(str, Enum):
    ABILITY   = "ability"
    ORDNANCE  = "ordnance"
    PASSIVE   = "passive"


class CallContext(str, Enum):
    NEUTRAL      = "neutral"
    COMBAT       = "combat"
    MOVEMENT     = "movement"
    ENVIRONMENT  = "environment"
    OBJECTIVE    = "objective"
    ALERT        = "alert"


# ---------------------------------------------------------------------------
# Primitive data objects
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class Marker:
    """A point on the minimap or world overlay."""
    x: float = 0.0          # 0..1 relative to minimap canvas
    y: float = 0.0          # 0..1 relative to minimap canvas
    label: str = ""
    kind: MarkerKind = MarkerKind.ALLY
    heading: float = 0.0    # degrees; 0 = marker faces north; used for directional icons
    visible: bool = True    # can be toggled by game logic without removing from list


@dataclass(slots=True)
class Notification:
    """A single kill-feed / event line."""
    text: str = ""
    color: str = "#c8f0ff"
    created_at: float = field(default_factory=time.monotonic)
    ttl: float = 5.0        # seconds before auto-removal

    @property
    def expired(self) -> bool:
        return (time.monotonic() - self.created_at) >= self.ttl

    @property
    def alpha_fraction(self) -> float:
        """0 → 1; fades out in the final 1 second of TTL."""
        age = time.monotonic() - self.created_at
        remaining = self.ttl - age
        return max(0.0, min(1.0, remaining))   # full alpha until last second


@dataclass(slots=True)
class AbilityIcon:
    """One ability / ordnance slot in the bottom cluster."""
    name: str = ""
    key: str = ""                              # keyboard / controller label
    color: str = "#00aaff"                    # hex; e.g. red = offensive, blue = utility
    cooldown_total: float = 0.0               # seconds for a full cooldown cycle
    cooldown_remaining: float = 0.0           # seconds left; 0 = ready
    size: AbilitySize = AbilitySize.TACTICAL
    icon_glyph: str = ""                      # optional single unicode glyph or path

    @property
    def ready(self) -> bool:
        return self.cooldown_remaining <= 0.0

    @property
    def cooldown_fraction(self) -> float:
        """0.0 = ready, 1.0 = just activated (full cooldown)."""
        if self.cooldown_total <= 0:
            return 0.0
        return max(0.0, min(1.0, self.cooldown_remaining / self.cooldown_total))


@dataclass(slots=True)
class WeaponReadout:
    """Bottom weapon block."""
    name: str = "XO-16 CHAINGUN"
    ammo_current: int = 40
    ammo_reserve: int = 120
    mag_size: int = 40                        # for pip rendering
    silhouette_color: str = "#00ff88"
    fire_mode: str = "AUTO"                   # e.g. "AUTO", "BURST", "SINGLE"


@dataclass(slots=True)
class VitalState:
    """Pilot health, shield, and titan-link bars."""
    health: float = 1.0           # 0..1
    shield: float = 1.0           # 0..1
    titan_link: float = 1.0       # 0..1; titan readiness / bond integrity
    health_max: float = 1.0       # kept for labelling (e.g. "100 HP")
    shield_max: float = 1.0


@dataclass(slots=True)
class CommsState:
    """Rich metadata for the top-right transmission panel."""
    active: bool = False
    header: str = "INTERCEPTING TRANSMISSION"
    speaker_name: str = ""
    speaker_role: str = ""
    portrait_path: Optional[str] = None       # path to a small portrait image
    message: str = ""
    signal_strength: float = 1.0             # 0..1; drives audio-visualiser animation
    channel: str = "CH-07"
    timestamp: str = ""                       # e.g. "T+00:04:12"


@dataclass(slots=True)
class EventCard:
    """A compact card in the middle-left event stack."""
    label: str = ""                           # small upper label, e.g. "CALLSIGN"
    value: str = ""                           # main text, e.g. "Objective Complete"
    category: CardCategory = CardCategory.INFO
    created_at: float = field(default_factory=time.monotonic)
    ttl: float = 6.0                          # seconds; 0 = permanent

    @property
    def expired(self) -> bool:
        if self.ttl <= 0:
            return False
        return (time.monotonic() - self.created_at) >= self.ttl

    @property
    def alpha_fraction(self) -> float:
        if self.ttl <= 0:
            return 1.0
        age = time.monotonic() - self.created_at
        remaining = self.ttl - age
        return max(0.0, min(1.0, remaining))


@dataclass(slots=True)
class TitanMeter:
    """Circular titan-build gauge in bottom-left corner."""
    progress: float = 0.0       # 0..1; fill fraction of the circular gauge
    label: str = "TITANFALL"
    is_ready: bool = False      # when True, gauge pulses/flashes

    def __post_init__(self):
        self.progress = max(0.0, min(1.0, self.progress))


@dataclass(slots=True)
class CallBox:
    """Top-right call panel — only visible when active."""
    active: bool = False
    pilot_name: str = ""
    voice_line: str = ""
    context: CallContext = CallContext.NEUTRAL
    signal_strength: float = 1.0   # 0..1


@dataclass(slots=True)
class InfoFeedMessage:
    """A single line in the bottom-right scrolling info feed."""
    text: str = ""
    color: str = "#ffffff"
    created_at: float = field(default_factory=time.monotonic)
    ttl: float = 5.0

    @property
    def expired(self) -> bool:
        return (time.monotonic() - self.created_at) >= self.ttl

    @property
    def alpha_fraction(self) -> float:
        age = time.monotonic() - self.created_at
        remaining = self.ttl - age
        return max(0.0, min(1.0, remaining))


@dataclass(slots=True)
class StatusIcon:
    """A notched-rectangle icon to the right of the titanmeter."""
    name: str = ""
    kind: StatusIconKind = StatusIconKind.ABILITY
    key: str = ""                              # keyboard label
    active: bool = True
    icon_glyph: str = ""                       # unicode glyph
    cooldown_total: float = 0.0
    cooldown_remaining: float = 0.0

    @property
    def ready(self) -> bool:
        return self.cooldown_remaining <= 0.0

    @property
    def cooldown_fraction(self) -> float:
        if self.cooldown_total <= 0:
            return 0.0
        return max(0.0, min(1.0, self.cooldown_remaining / self.cooldown_total))


# ---------------------------------------------------------------------------
# Root HUD state
# ---------------------------------------------------------------------------

@dataclass
class HudState:
    """
    Complete mutable snapshot of everything the HUD renders each frame.

    The application mutates this object freely; the renderer reads it.
    Call ``tick(dt)`` once per frame to age and expire time-limited items.
    """

    # Identity
    pilot_callsign: str = "PILOT"
    faction: str = "MILITIA"

    # Vitals
    vitals: VitalState = field(default_factory=VitalState)

    # Navigation
    compass_heading: float = 0.0   # degrees; 0 = north; drives minimap rotation
    minimap_zoom: float = 1.0      # multiplier applied to marker positions

    # Map markers (minimap)
    markers: List[Marker] = field(default_factory=list)

    # Communication panel
    comms: CommsState = field(default_factory=CommsState)

    # Middle-left event cards (auto-expiring)
    event_cards: List[EventCard] = field(default_factory=list)

    # Right-side notification feed (auto-expiring)
    notifications: List[Notification] = field(default_factory=list)

    # Bottom ability cluster
    abilities: List[AbilityIcon] = field(default_factory=list)

    # Bottom weapon readout
    weapon: WeaponReadout = field(default_factory=WeaponReadout)

    # Mission
    mission_progress: float = 0.5   # 0..1; drives top-center progress bar
    objective_label: str = ""

    # System
    system_status: SystemStatus = SystemStatus.ONLINE
    camera_fps: float = 0.0         # populated by the window from stream telemetry

    # New Titanfall 2 HUD elements
    titanmeter: TitanMeter = field(default_factory=TitanMeter)
    call_box: CallBox = field(default_factory=CallBox)
    info_feed: List[InfoFeedMessage] = field(default_factory=list)
    status_icons: List[StatusIcon] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def add_notification(
        self,
        text: str,
        color: str = "#c8f0ff",
        ttl: float = 5.0,
        *,
        max_visible: int = 5,
    ) -> None:
        """Push a notification; trim the list to *max_visible*."""
        self.notifications.append(Notification(text=text, color=color, ttl=ttl))
        # Keep only the most recent
        if len(self.notifications) > max_visible:
            self.notifications = self.notifications[-max_visible:]

    def add_card(
        self,
        value: str,
        label: str = "",
        category: CardCategory = CardCategory.INFO,
        ttl: float = 6.0,
        *,
        max_visible: int = 4,
    ) -> None:
        """Push an event card; trim to *max_visible*."""
        self.event_cards.append(
            EventCard(label=label, value=value, category=category, ttl=ttl)
        )
        if len(self.event_cards) > max_visible:
            self.event_cards = self.event_cards[-max_visible:]

    def add_info_message(
        self,
        text: str,
        color: str = "#ffffff",
        ttl: float = 5.0,
        *,
        max_visible: int = 6,
    ) -> None:
        """Push an info feed message; trim to *max_visible*."""
        self.info_feed.append(InfoFeedMessage(text=text, color=color, ttl=ttl))
        if len(self.info_feed) > max_visible:
            self.info_feed = self.info_feed[-max_visible:]

    def tick(self, dt: float) -> None:
        """
        Advance all time-limited state by *dt* seconds.

        Intended to be called once per frame from the render loop:
        ``state.tick(dt)``

        Actions:
          • Decrement ability cooldowns
          • Remove expired notifications and event cards
        """
        # Ability cooldowns
        for ab in self.abilities:
            if ab.cooldown_remaining > 0:
                ab.cooldown_remaining = max(0.0, ab.cooldown_remaining - dt)

        # Status icon cooldowns
        for si in self.status_icons:
            if si.cooldown_remaining > 0:
                si.cooldown_remaining = max(0.0, si.cooldown_remaining - dt)

        # Prune expired items
        self.notifications = [n for n in self.notifications if not n.expired]
        self.event_cards = [c for c in self.event_cards if not c.expired]
        self.info_feed = [m for m in self.info_feed if not m.expired]

    # ------------------------------------------------------------------
    # Backwards-compatible shims for code written against v1
    # ------------------------------------------------------------------

    @property
    def ally_markers(self) -> List[Marker]:
        return [m for m in self.markers if m.kind == MarkerKind.ALLY]

    @property
    def threat_markers(self) -> List[Marker]:
        return [m for m in self.markers if m.kind == MarkerKind.THREAT]

    @property
    def comms_text(self) -> str:
        return self.comms.message

    @comms_text.setter
    def comms_text(self, value: str) -> None:
        self.comms.message = value