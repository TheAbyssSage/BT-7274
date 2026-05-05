"""Tests for BT-7274 HUD data models."""

import sys
import time
from pathlib import Path

_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import pytest
from bt7274_hud.hud_data import (
    HudState, Marker, MarkerKind, Notification, AbilityIcon, WeaponReadout,
    TitanMeter, CallBox, CallContext, InfoFeedMessage, StatusIcon, StatusIconKind,
)


def test_hud_state_defaults():
    state = HudState()
    assert state.pilot_callsign == "PILOT"
    assert state.ally_markers == []
    assert state.threat_markers == []
    assert state.notifications == []
    assert state.abilities == []
    assert state.weapon.ammo_current == 40


def test_marker_creation():
    m = Marker(x=0.5, y=0.2, label="T1", kind=MarkerKind.ALLY)
    assert m.x == 0.5
    assert m.y == 0.2
    assert m.label == "T1"
    assert m.kind == MarkerKind.ALLY


def test_notification_creation():
    n = Notification(text="Objective Complete", color="#00ff88", ttl=3.0)
    assert n.text == "Objective Complete"
    assert n.color == "#00ff88"
    assert n.ttl == 3.0


def test_ability_icon_creation():
    a = AbilityIcon(name="Smoke", key="Q", color="#ff4444",
                    cooldown_total=10.0, cooldown_remaining=0.0)
    assert a.name == "Smoke"
    assert a.key == "Q"
    assert a.color == "#ff4444"
    assert a.cooldown_total == 10.0
    assert a.cooldown_remaining == 0.0


def test_weapon_readout_defaults():
    w = WeaponReadout()
    assert w.name == "XO-16 CHAINGUN"
    assert w.ammo_current == 40
    assert w.ammo_reserve == 120


# --- New Titanfall 2 data model tests ---

def test_titanmeter_defaults():
    tm = TitanMeter()
    assert tm.progress == 0.0
    assert tm.label == "TITANFALL"
    assert tm.is_ready is False


def test_titanmeter_progress_clamped():
    tm = TitanMeter(progress=1.5)
    assert tm.progress == 1.0
    tm2 = TitanMeter(progress=-0.3)
    assert tm2.progress == 0.0


def test_call_box_defaults():
    cb = CallBox()
    assert cb.active is False
    assert cb.pilot_name == ""
    assert cb.voice_line == ""
    assert cb.context == CallContext.NEUTRAL


def test_call_box_active_state():
    cb = CallBox(
        active=True,
        pilot_name="BT-7274",
        voice_line="Transferring control to Pilot.",
        context=CallContext.COMBAT,
    )
    assert cb.active is True
    assert cb.pilot_name == "BT-7274"
    assert cb.context == CallContext.COMBAT


def test_info_feed_message_defaults():
    msg = InfoFeedMessage(text="Enemy spotted")
    assert msg.text == "Enemy spotted"
    assert msg.ttl == 5.0
    assert msg.expired is False


def test_info_feed_message_expires():
    msg = InfoFeedMessage(text="Test", ttl=0.01)
    time.sleep(0.02)
    assert msg.expired is True


def test_info_feed_message_alpha_fades():
    msg = InfoFeedMessage(text="Test", ttl=5.0)
    assert msg.alpha_fraction > 0.9


def test_status_icon_defaults():
    si = StatusIcon(name="STIM", kind=StatusIconKind.ABILITY, key="Q")
    assert si.name == "STIM"
    assert si.kind == StatusIconKind.ABILITY
    assert si.key == "Q"
    assert si.active is True
    assert si.cooldown_fraction == 0.0


def test_status_icon_cooldown():
    si = StatusIcon(
        name="GRAPPLE",
        kind=StatusIconKind.ABILITY,
        key="LB",
        cooldown_total=10.0,
        cooldown_remaining=5.0,
    )
    assert si.cooldown_fraction == 0.5
    assert si.ready is False


def test_hud_state_has_new_fields():
    state = HudState()
    assert isinstance(state.titanmeter, TitanMeter)
    assert isinstance(state.call_box, CallBox)
    assert state.info_feed == []
    assert state.status_icons == []
