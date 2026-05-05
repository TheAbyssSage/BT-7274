"""Pure data classes for the BT-7274 Pilot HUD state."""

from dataclasses import dataclass, field
from typing import List


@dataclass
class Marker:
    """A point on the minimap or world overlay."""
    x: float = 0.0   # 0..1 relative to minimap/world
    y: float = 0.0   # 0..1 relative to minimap/world
    label: str = ""
    color: str = "blue"   # "blue" | "red" | "green" | "yellow"


@dataclass
class Notification:
    """A single kill-feed / event line."""
    text: str = ""
    color: str = "#ffffff"
    ttl: float = 5.0   # Seconds remaining


@dataclass
class AbilityIcon:
    """One ability/ordnance slot."""
    name: str = ""
    key: str = ""
    color: str = "#00aaff"
    cooldown: float = 0.0   # 0.0 = ready, >0 = seconds remaining


@dataclass
class WeaponReadout:
    """Bottom weapon block."""
    name: str = "XO-16"
    ammo_current: int = 0
    ammo_reserve: int = 0
    silhouette_color: str = "#00ff88"


@dataclass
class HudState:
    """Complete mutable snapshot of what the HUD should display."""
    pilot_callsign: str = "PILOT"
    mission_progress: float = 0.5   # 0..1
    comms_text: str = ""
    comms_icon: str = ""          # Optional icon name / path
    event_cards: List[str] = field(default_factory=list)
    ally_markers: List[Marker] = field(default_factory=list)
    threat_markers: List[Marker] = field(default_factory=list)
    notifications: List[Notification] = field(default_factory=list)
    abilities: List[AbilityIcon] = field(default_factory=list)
    weapon: WeaponReadout = field(default_factory=WeaponReadout)
    compass_heading: float = 0.0   # Degrees, 0 = north
    system_status: str = "ONLINE"
