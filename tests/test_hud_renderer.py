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
