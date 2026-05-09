"""Tests for BT-7274 HUD data models."""

import sys
from pathlib import Path

_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import pytest
from bt7274.bt7274_hud.hud_data import HudState, Marker, MarkerKind, Notification, AbilityIcon, WeaponReadout


def test_hud_state_defaults():
    state = HudState()
    assert state.pilot_callsign == "PILOT"
    assert state.markers == []
    assert state.notifications == []
    assert state.abilities == []
    assert state.weapon.ammo_current == 40


def test_marker_creation():
    m = Marker(x=0.5, y=0.2, label="T1", kind=MarkerKind.THREAT)
    assert m.x == 0.5
    assert m.y == 0.2
    assert m.label == "T1"
    assert m.kind == MarkerKind.THREAT


def test_notification_creation():
    n = Notification(text="Objective Complete", color="#00ff88", ttl=3.0)
    assert n.text == "Objective Complete"
    assert n.color == "#00ff88"
    assert n.ttl == 3.0


def test_ability_icon_creation():
    a = AbilityIcon(name="Smoke", key="Q", color="#ff4444", cooldown_total=10.0, cooldown_remaining=5.0)
    assert a.name == "Smoke"
    assert a.key == "Q"
    assert a.color == "#ff4444"
    assert a.cooldown_total == 10.0
    assert a.cooldown_remaining == 5.0
    assert not a.ready


def test_weapon_readout_defaults():
    w = WeaponReadout()
    assert w.name == "XO-16 CHAINGUN"
    assert w.ammo_current == 40
    assert w.ammo_reserve == 120
