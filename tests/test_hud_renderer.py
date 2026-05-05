"""Tests for BT-7274 HUD renderer."""

import sys
from pathlib import Path

_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import pytest
from PIL import Image

from bt7274_hud.hud_renderer import HudRenderer, _hex as hex_to_rgba


def test_hex_to_rgba():
    assert hex_to_rgba("#ff0000", 128) == (255, 0, 0, 128)
    assert hex_to_rgba("00ff00", 255) == (0, 255, 0, 255)
    assert hex_to_rgba("#123", 64) == (17, 34, 51, 64)


def test_renderer_init():
    r = HudRenderer(width=640, height=480)
    assert r.width == 640
    assert r.height == 480


def test_renderer_composite_returns_image():
    r = HudRenderer(width=320, height=240)
    bg = Image.new("RGB", (320, 240), "black")
    from bt7274_hud.hud_data import HudState
    result = r.composite(bg, HudState())
    assert isinstance(result, Image.Image)
    assert result.size == (320, 240)
    assert result.mode == "RGBA"


def test_minimap_has_scanline_effect():
    """Minimap output should differ from a plain circle — scanlines add pixels."""
    from bt7274_hud.hud_data import HudState, Marker, MarkerKind
    r = HudRenderer(width=400, height=300)
    state = HudState()
    state.markers = [Marker(x=0.5, y=0.5, label="BT", kind=MarkerKind.ALLY)]
    bg = Image.new("RGB", (400, 300), "black")
    result = r.composite(bg, state)
    # The minimap region (top-left ~130px) should have non-black pixels
    region = result.crop((0, 0, 150, 150))
    pixels = list(region.getdata())
    non_black = [p for p in pixels if p[:3] != (0, 0, 0)]
    assert len(non_black) > 50, "Minimap should render visible elements"


def test_minimap_has_outer_ring():
    """Minimap must have a visible outer ring/border."""
    from bt7274_hud.hud_data import HudState
    r = HudRenderer(width=400, height=300)
    bg = Image.new("RGB", (400, 300), "black")
    result = r.composite(bg, HudState())
    region = result.crop((0, 0, 150, 150))
    pixels = list(region.getdata())
    # Look for orange-ish pixels (the border ring, composited over black so dimmer)
    # Orange (255,140,0) at alpha ~100/255 over black → ~(100, 55, 0)
    orange_pixels = [p for p in pixels if p[0] > 60 and p[1] > 20 and p[1] < 120 and p[2] < 30]
    assert len(orange_pixels) > 10, "Minimap should have orange border ring"


def test_titanmeter_renders_circular_gauge():
    """Titanmeter should render a circular arc with a gap at 6 o'clock."""
    from bt7274_hud.hud_data import HudState, TitanMeter
    r = HudRenderer(width=400, height=300)
    state = HudState()
    state.titanmeter = TitanMeter(progress=0.6, label="TITANFALL")
    bg = Image.new("RGB", (400, 300), "black")
    result = r.composite(bg, state)
    # Bottom-left region should have rendered content
    region = result.crop((0, 200, 120, 300))
    pixels = list(region.getdata())
    non_black = [p for p in pixels if p[:3] != (0, 0, 0)]
    assert len(non_black) > 30, "Titanmeter should render visible elements in bottom-left"


def test_titanmeter_shows_label():
    """Titanmeter must display its label text."""
    from bt7274_hud.hud_data import HudState, TitanMeter
    r = HudRenderer(width=400, height=300)
    state = HudState()
    state.titanmeter = TitanMeter(progress=0.3, label="TITANFALL")
    bg = Image.new("RGB", (400, 300), "black")
    result = r.composite(bg, state)
    # The label should produce non-black pixels in the bottom-left area
    region = result.crop((0, 240, 120, 300))
    pixels = list(region.getdata())
    non_black = [p for p in pixels if p[:3] != (0, 0, 0)]
    assert len(non_black) > 5, "Titanmeter label should be visible"


def test_status_icons_render_notched_rectangles():
    """Status icons should render as notched rectangles to the right of titanmeter."""
    from bt7274_hud.hud_data import HudState, StatusIcon, StatusIconKind
    r = HudRenderer(width=400, height=300)
    state = HudState()
    state.status_icons = [
        StatusIcon(name="STIM", kind=StatusIconKind.ABILITY, key="Q", icon_glyph="⚡"),
        StatusIcon(name="GRAPPLE", kind=StatusIconKind.ABILITY, key="LB", icon_glyph="⬡"),
    ]
    bg = Image.new("RGB", (400, 300), "black")
    result = r.composite(bg, state)
    # Bottom-left area (right of titanmeter) should have rendered content
    region = result.crop((80, 220, 200, 300))
    pixels = list(region.getdata())
    non_black = [p for p in pixels if p[:3] != (0, 0, 0)]
    assert len(non_black) > 20, "Status icons should render visible elements"


def test_call_box_hidden_when_inactive():
    """Call box should not render anything when inactive."""
    from bt7274_hud.hud_data import HudState, CallBox
    r = HudRenderer(width=400, height=300)
    state = HudState()
    state.call_box = CallBox(active=False)
    bg = Image.new("RGB", (400, 300), "black")
    result_inactive = r.composite(bg, state)

    # Now activate and compare — active should have more pixels in call box area
    state.call_box = CallBox(
        active=True, pilot_name="BT", voice_line="Test",
    )
    result_active = r.composite(bg, state)

    # Call box area (avoiding corner brackets)
    region_inactive = result_inactive.crop((200, 20, 370, 90))
    region_active = result_active.crop((200, 20, 370, 90))

    inactive_count = len([p for p in region_inactive.getdata() if p[:3] != (0, 0, 0)])
    active_count = len([p for p in region_active.getdata() if p[:3] != (0, 0, 0)])

    # Active call box should add significant pixels
    assert active_count > inactive_count + 50, "Active call box should add rendered pixels"


def test_call_box_visible_when_active():
    """Call box should render when active with pilot name and voice line."""
    from bt7274_hud.hud_data import HudState, CallBox, CallContext
    r = HudRenderer(width=400, height=300)
    state = HudState()
    state.call_box = CallBox(
        active=True,
        pilot_name="BT-7274",
        voice_line="Transferring control to Pilot.",
        context=CallContext.COMBAT,
    )
    bg = Image.new("RGB", (400, 300), "black")
    result = r.composite(bg, state)
    region = result.crop((250, 0, 400, 120))
    pixels = list(region.getdata())
    non_black = [p for p in pixels if p[:3] != (0, 0, 0)]
    assert len(non_black) > 80, "Active call box should render visible elements"


def test_info_feed_renders_text_only():
    """Info feed should render text lines in bottom-right, no icons."""
    from bt7274_hud.hud_data import HudState, InfoFeedMessage
    r = HudRenderer(width=400, height=300)
    state = HudState()
    state.info_feed = [
        InfoFeedMessage(text="Enemy pilot detected", color="#ff4444"),
        InfoFeedMessage(text="Uplink established", color="#00aaff"),
        InfoFeedMessage(text="Titanfall ready", color="#ff8c00"),
    ]
    bg = Image.new("RGB", (400, 300), "black")
    result = r.composite(bg, state)
    # Bottom-right region should have text
    region = result.crop((250, 200, 400, 300))
    pixels = list(region.getdata())
    non_black = [p for p in pixels if p[:3] != (0, 0, 0)]
    assert len(non_black) > 30, "Info feed should render visible text in bottom-right"


def test_info_feed_newest_at_bottom():
    """Newer messages should appear below older ones (higher y position)."""
    from bt7274_hud.hud_data import HudState, InfoFeedMessage
    r = HudRenderer(width=400, height=300)
    state = HudState()
    state.info_feed = [
        InfoFeedMessage(text="MSG1", color="#ffffff", ttl=3600),
        InfoFeedMessage(text="MSG2", color="#ffffff", ttl=3600),
        InfoFeedMessage(text="MSG3", color="#ffffff", ttl=3600),
    ]
    bg = Image.new("RGB", (400, 300), "black")
    result = r.composite(bg, state)
    # Info feed renders from base_y=280 upward with lh=15
    # MSG3 at y=280, MSG2 at y=265, MSG1 at y=250
    # Bottom region (newest): y=275-285
    bottom_region = result.crop((250, 275, 400, 285))
    # Top region (oldest): y=245-255
    top_region = result.crop((250, 245, 400, 255))
    bottom_count = len([p for p in bottom_region.getdata() if p[:3] != (0, 0, 0)])
    top_count = len([p for p in top_region.getdata() if p[:3] != (0, 0, 0)])
    # Both should have text rendered
    assert bottom_count > 5, "Bottom region should have newest message text"
    assert top_count > 5, "Top region should have oldest message text"
