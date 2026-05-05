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
