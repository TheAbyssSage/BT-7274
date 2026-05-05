"""
HUD drawing engine — BT-7274 Pilot HUD
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Upgrades over v1:
  • Minimap rotates with ``state.compass_heading`` so forward is always up
  • Ability cluster respects AbilitySize enum (main=54 px, tactical=36 px,
    passive=28 px) and draws a swept arc for the cooldown fraction
  • Vitals section (health / shield / titan-link) drawn as thin segmented
    bars in the bottom-centre, with numeric readouts
  • Notification feed entries fade out in their final second
  • Top scanline + corner bracket overlays for the helmet-glass aesthetic
  • Comms panel shows speaker name, role, channel, and a signal-bar
    visualiser driven by ``state.comms.signal_strength``
  • All semi-transparent fills use a cached RGBA overlay approach so
    every element composites cleanly over any camera background
  • Font loading extended: tries system + bundled fallbacks in order
"""

from __future__ import annotations

import logging
import math
import os
from typing import Any, Optional, Tuple

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from bt7274_hud.hud_data import (
    AbilitySize,
    CardCategory,
    CommsState,
    EventCard,
    HudState,
    MarkerKind,
    Notification,
    SystemStatus,
    VitalState,
)

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Colour palette  (Titanfall 2 inspired — orange / white / blue)
# ---------------------------------------------------------------------------

# Primary accent — orange (Titanfall signature)
_ORANGE        = (255, 140,   0, 255)
_ORANGE_DIM    = (255, 140,   0, 100)
_ORANGE_GHOST  = (255, 140,   0,  40)
_ORANGE_BRIGHT = (255, 165,   0, 255)

# Secondary accent — electric blue
_BLUE          = (0,   128, 255, 255)
_BLUE_DIM      = (0,   100, 220, 100)
_BLUE_GHOST    = (0,   128, 255,  40)

# Alert / threat
_RED           = (255,  60,  60, 255)
_RED_DIM       = (255,  60,  60, 100)
_AMBER         = (255, 190,  40, 255)
_AMBER_DIM     = (255, 190,  40, 100)

# Neutral
_WHITE         = (255, 255, 255, 220)
_WHITE_DIM     = (255, 255, 255,  80)
_WHITE_GHOST   = (255, 255, 255,  30)

# Panel backgrounds — very dark, mostly transparent
_PANEL_BG      = (  5,  15,  30, 140)
_PANEL_BDR     = (255, 140,   0, 160)

# Keep backward-compat aliases for any code referencing old names
_CYAN        = _ORANGE
_CYAN_DIM    = _ORANGE_DIM
_CYAN_GHOST  = _ORANGE_GHOST


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hex(h: str, a: int = 255) -> Tuple[int, int, int, int]:
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return (r, g, b, a)


def _fade(color: Tuple[int, int, int, int], fraction: float) -> Tuple[int, int, int, int]:
    """Multiply the alpha channel by *fraction* (0..1)."""
    r, g, b, a = color
    return (r, g, b, int(a * max(0.0, min(1.0, fraction))))


def _draw_rounded_rect(
    draw: ImageDraw.ImageDraw,
    xy: Tuple[int, int, int, int],
    radius: int = 4,
    fill=None,
    outline=None,
    width: int = 1,
) -> None:
    """Thin wrapper; PIL's rounded_rectangle available since 8.2."""
    x0, y0, x1, y1 = xy
    draw.rounded_rectangle([(x0, y0), (x1, y1)], radius=radius, fill=fill, outline=outline, width=width)


def _arc_cooldown(
    draw: ImageDraw.ImageDraw,
    cx: int,
    cy: int,
    r: int,
    fraction: float,
    color: Tuple[int, int, int, int],
    width: int = 2,
) -> None:
    """Draw a clockwise sweep arc representing remaining cooldown."""
    if fraction <= 0:
        return
    start_deg = -90                          # 12 o'clock
    end_deg   = start_deg + 360 * fraction
    bbox = [(cx - r, cy - r), (cx + r, cy + r)]
    draw.arc(bbox, start=start_deg, end=end_deg, fill=color, width=width)


# ---------------------------------------------------------------------------
# Font loader
# ---------------------------------------------------------------------------

_FONT_SEARCH_PATHS = [
    # Condensed / monospaced — preferred
    "/System/Library/Fonts/Menlo.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
    "C:/Windows/Fonts/consola.ttf",
    # Sans fallbacks
    "/System/Library/Fonts/Helvetica.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in _FONT_SEARCH_PATHS:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------

class HudRenderer:
    """
    Draws all HUD overlays onto a PIL Image.

    Usage::

        renderer = HudRenderer(width=1280, height=720)
        output   = renderer.composite(camera_frame_pil, hud_state)
    """

    def __init__(self, width: int = 1280, height: int = 720):
        self.width  = width
        self.height = height

        # Font sizes scale with resolution
        base = max(10, height // 60)
        self._f_lg   = _load_font(base + 4)    # ~18 px at 720 p
        self._f_md   = _load_font(base)         # ~14 px
        self._f_sm   = _load_font(base - 2)     # ~11 px
        self._f_xs   = _load_font(max(8, base - 4))  # ~9 px

        # Pre-compute layout anchors (all relative to W×H)
        self._cx = width  // 2
        self._cy = height // 2

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def composite(self, background: Image.Image, state: HudState) -> Image.Image:
        """
        Composite every HUD layer onto *background*.

        *background* may be any PIL mode; output is always RGBA.
        """
        bg = background.convert("RGBA") if background.mode != "RGBA" else background.copy()

        # Resize if the camera produced a different resolution
        if bg.size != (self.width, self.height):
            bg = bg.resize((self.width, self.height), Image.Resampling.LANCZOS)

        overlay = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        draw    = ImageDraw.Draw(overlay)

        # Draw in z-order (background → foreground)
        self._draw_scanlines(draw)
        self._draw_corner_brackets(draw)
        self._draw_reticle(draw)
        self._draw_minimap(draw, state)
        self._draw_mission_bar(draw, state)
        self._draw_comms_panel(draw, state)
        self._draw_event_cards(draw, state)
        self._draw_notification_feed(draw, state)
        self._draw_vitals(draw, state)
        self._draw_ability_cluster(draw, state)
        self._draw_weapon_readout(draw, state)
        self._draw_system_status(draw, state)

        bg.paste(overlay, (0, 0), overlay)
        return bg

    # ------------------------------------------------------------------
    # Helmet-glass effects
    # ------------------------------------------------------------------

    def _draw_scanlines(self, draw: ImageDraw.ImageDraw) -> None:
        """Subtle horizontal scanlines across the entire frame."""
        step = 4
        for y in range(0, self.height, step):
            draw.line([(0, y), (self.width, y)], fill=(0, 180, 255, 8))

    def _draw_corner_brackets(self, draw: ImageDraw.ImageDraw) -> None:
        """Four corner bracket decorations — gives the helmet-frame look."""
        arm = 32
        gap = 12
        w   = 2
        c   = _CYAN_DIM
        W, H = self.width, self.height

        for (bx, by, sx, sy) in [
            (gap,     gap,     +1, +1),   # top-left
            (W - gap, gap,     -1, +1),   # top-right
            (gap,     H - gap, +1, -1),   # bottom-left
            (W - gap, H - gap, -1, -1),   # bottom-right
        ]:
            draw.line([(bx, by), (bx + sx * arm, by)], fill=c, width=w)
            draw.line([(bx, by), (bx, by + sy * arm)], fill=c, width=w)

    # ------------------------------------------------------------------
    # Reticle
    # ------------------------------------------------------------------

    def _draw_reticle(self, draw: ImageDraw.ImageDraw) -> None:
        """Small, precise reticle at screen centre."""
        cx, cy = self._cx, self._cy
        gap, arm = 6, 10
        dot_r = 1
        c = _WHITE

        draw.line([(cx,          cy - gap - arm), (cx,          cy - gap)], fill=c, width=1)
        draw.line([(cx,          cy + gap),        (cx,          cy + gap + arm)], fill=c, width=1)
        draw.line([(cx - gap - arm, cy),            (cx - gap,    cy)], fill=c, width=1)
        draw.line([(cx + gap,    cy),               (cx + gap + arm, cy)], fill=c, width=1)
        draw.ellipse([(cx - dot_r, cy - dot_r), (cx + dot_r, cy + dot_r)], fill=c)

    # ------------------------------------------------------------------
    # Top-left minimap
    # ------------------------------------------------------------------

    def _draw_minimap(self, draw: ImageDraw.ImageDraw, state: HudState) -> None:
        """
        Circular minimap.

        Rotates so the pilot's current heading is always at the top.
        Ally markers → blue, threat → red, objective → amber.
        """
        size   = min(130, self.width // 10)
        margin = 18
        cx     = margin + size // 2
        cy     = margin + size // 2
        r      = size // 2
        r_inner = r - 3

        # --- filled background ---
        draw.ellipse([(cx - r, cy - r), (cx + r, cy + r)], fill=_PANEL_BG)

        # --- inner grid lines ---
        for offset in (-r_inner // 2, 0, r_inner // 2):
            draw.line([(cx + offset, cy - r_inner), (cx + offset, cy + r_inner)], fill=_WHITE_GHOST)
            draw.line([(cx - r_inner, cy + offset), (cx + r_inner, cy + offset)], fill=_WHITE_GHOST)

        # --- markers (rotated by heading) ---
        heading_rad = math.radians(-state.compass_heading)  # negate → rotate map, not player
        marker_colors = {
            MarkerKind.ALLY:      _BLUE,
            MarkerKind.THREAT:    _RED,
            MarkerKind.OBJECTIVE: _AMBER,
            MarkerKind.WAYPOINT:  _CYAN,
        }
        for m in state.markers:
            if not m.visible:
                continue
            # Convert 0..1 to centred coords, then rotate
            mx_raw = (m.x - 0.5) * size * state.minimap_zoom
            my_raw = (m.y - 0.5) * size * state.minimap_zoom
            cos_h, sin_h = math.cos(heading_rad), math.sin(heading_rad)
            mx = cx + int(mx_raw * cos_h - my_raw * sin_h)
            my = cy + int(mx_raw * sin_h + my_raw * cos_h)
            # Clamp to circle
            dx, dy = mx - cx, my - cy
            dist = math.hypot(dx, dy)
            if dist > r_inner:
                mx = cx + int(dx / dist * r_inner)
                my = cy + int(dy / dist * r_inner)
            col = marker_colors.get(m.kind, _WHITE)
            mr = 3 if m.kind == MarkerKind.ALLY else 4
            draw.ellipse([(mx - mr, my - mr), (mx + mr, my + mr)], fill=col)

        # --- pilot triangle (always points up) ---
        tri = [(cx, cy - 7), (cx - 4, cy + 5), (cx + 4, cy + 5)]
        draw.polygon(tri, fill=_WHITE)

        # --- outer ring + tick marks ---
        draw.ellipse([(cx - r, cy - r), (cx + r, cy + r)],
                     outline=_PANEL_BDR, width=2)
        for deg in range(0, 360, 45):
            angle = math.radians(deg - state.compass_heading)
            r_tick_in  = r - 6
            r_tick_out = r - 1
            draw.line([
                (cx + int(r_tick_in  * math.sin(angle)), cy - int(r_tick_in  * math.cos(angle))),
                (cx + int(r_tick_out * math.sin(angle)), cy - int(r_tick_out * math.cos(angle))),
            ], fill=_CYAN_DIM, width=1)

        # --- label ---
        draw.text((cx, margin + size + 5), "TACMAP", font=self._f_xs,
                  fill=_fade(_CYAN, 0.7), anchor="mt")

    # ------------------------------------------------------------------
    # Top-centre mission progress bar
    # ------------------------------------------------------------------

    def _draw_mission_bar(self, draw: ImageDraw.ImageDraw, state: HudState) -> None:
        bar_w, bar_h = min(260, self.width // 5), 6
        x0 = self._cx - bar_w // 2
        y0 = 22

        # Track
        draw.rectangle([(x0, y0), (x0 + bar_w, y0 + bar_h)],
                       fill=_WHITE_GHOST, outline=_CYAN_GHOST, width=1)
        # Fill
        fw = int(bar_w * max(0.0, min(1.0, state.mission_progress)))
        if fw > 0:
            draw.rectangle([(x0, y0), (x0 + fw, y0 + bar_h)], fill=_BLUE_DIM)

        # Objective label
        if state.objective_label:
            draw.text((self._cx, y0 - 4), state.objective_label.upper(),
                      font=self._f_xs, fill=_fade(_WHITE, 0.5), anchor="mb")

    # ------------------------------------------------------------------
    # Top-right comms panel
    # ------------------------------------------------------------------

    def _draw_comms_panel(self, draw: ImageDraw.ImageDraw, state: HudState) -> None:
        comms = state.comms
        pw, ph = min(230, self.width // 6), 110
        x0 = self.width - pw - 16
        y0 = 16

        # Background
        _draw_rounded_rect(draw, (x0, y0, x0 + pw, y0 + ph),
                           radius=3, fill=_PANEL_BG, outline=_PANEL_BDR, width=1)
        # Right accent stripe
        draw.rectangle([(x0 + pw - 3, y0 + 3), (x0 + pw - 1, y0 + ph - 3)],
                       fill=_fade(_CYAN, 0.4))

        ty = y0 + 6
        # Header row
        status_dot_col = _CYAN if comms.active else _fade(_CYAN, 0.3)
        draw.ellipse([(x0 + 7, ty + 2), (x0 + 12, ty + 7)], fill=status_dot_col)
        draw.text((x0 + 17, ty), comms.header if comms.active else "STANDBY",
                  font=self._f_xs, fill=_fade(_CYAN, 0.9 if comms.active else 0.35))
        # Channel
        draw.text((x0 + pw - 8, ty), comms.channel,
                  font=self._f_xs, fill=_fade(_CYAN, 0.4), anchor="ra")

        ty += 16
        draw.line([(x0 + 6, ty), (x0 + pw - 6, ty)], fill=_fade(_CYAN, 0.2))
        ty += 5

        if comms.active:
            # Speaker info
            draw.text((x0 + 8, ty), comms.speaker_name.upper(),
                      font=self._f_sm, fill=_WHITE)
            ty += 14
            draw.text((x0 + 8, ty), comms.speaker_role.upper(),
                      font=self._f_xs, fill=_fade(_CYAN, 0.5))
            ty += 14

            # Signal-strength bars (audio visualiser stand-in)
            bar_heights = [4, 7, 10, 7, 4, 10, 6, 8, 5, 9]
            sig = max(0.0, min(1.0, comms.signal_strength))
            bx = x0 + 8
            for i, bh in enumerate(bar_heights):
                scaled = int(bh * sig)
                bcolor = _CYAN if scaled > 0 else _fade(_CYAN, 0.2)
                by_top = ty + 12 - scaled
                draw.rectangle([(bx + i * 5, by_top), (bx + i * 5 + 3, ty + 12)], fill=bcolor)
            ty += 18

            # Message (truncated to panel width)
            if comms.message:
                chars_per_line = (pw - 16) // 6
                snippet = comms.message[:chars_per_line]
                draw.text((x0 + 8, ty), snippet, font=self._f_xs,
                          fill=_fade(_WHITE, 0.7))

    # ------------------------------------------------------------------
    # Middle-left event cards
    # ------------------------------------------------------------------

    def _draw_event_cards(self, draw: ImageDraw.ImageDraw, state: HudState) -> None:
        card_w, card_h = min(190, self.width // 7), 34
        gap   = 5
        x0    = 16
        start_y = self._cy - (len(state.event_cards) * (card_h + gap)) // 2

        cat_colors = {
            CardCategory.INFO:    _BLUE,
            CardCategory.SUCCESS: _CYAN,
            CardCategory.WARNING: _AMBER,
            CardCategory.DANGER:  _RED,
        }

        for i, card in enumerate(state.event_cards[-4:]):
            y    = start_y + i * (card_h + gap)
            alpha = card.alpha_fraction
            col  = cat_colors.get(card.category, _CYAN)

            # Background
            _draw_rounded_rect(draw, (x0, y, x0 + card_w, y + card_h),
                               radius=3, fill=_fade(_PANEL_BG, alpha))
            # Left accent stripe
            draw.rectangle([(x0, y + 3), (x0 + 2, y + card_h - 3)],
                           fill=_fade(col, alpha))
            # Small label
            draw.text((x0 + 8, y + 4), card.label.upper(),
                      font=self._f_xs, fill=_fade(col, 0.6 * alpha))
            # Main value
            draw.text((x0 + 8, y + 14), card.value[:28],
                      font=self._f_sm, fill=_fade(_WHITE, alpha))

    # ------------------------------------------------------------------
    # Right-side notification feed
    # ------------------------------------------------------------------

    def _draw_notification_feed(self, draw: ImageDraw.ImageDraw, state: HudState) -> None:
        x1    = self.width - 16
        y_top = self._cy + 20
        lh    = 16

        for i, note in enumerate(reversed(state.notifications[-5:])):
            y     = y_top + i * lh
            alpha = note.alpha_fraction
            col   = _fade(_hex(note.color), int(200 * alpha))
            text  = note.text[:45]
            # Subtle outline for legibility over bright backgrounds
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                draw.text((x1 + dx, y + dy), text, font=self._f_xs,
                          fill=_fade((0, 0, 0, 180), alpha), anchor="ra")
            draw.text((x1, y), text, font=self._f_xs, fill=col, anchor="ra")

    # ------------------------------------------------------------------
    # Bottom vitals bars
    # ------------------------------------------------------------------

    def _draw_vitals(self, draw: ImageDraw.ImageDraw, state: HudState) -> None:
        v     = state.vitals
        bw    = min(160, self.width // 8)
        bh    = 4
        gap   = 6
        total_h = 3 * (bh + gap) + 14   # 3 bars + label
        x0    = self._cx - bw // 2
        y0    = self.height - total_h - 16

        specs = [
            ("HEALTH",      v.health,     _CYAN),
            ("SHIELD",      v.shield,     _BLUE),
            ("TITAN LINK",  v.titan_link, _AMBER),
        ]

        for row, (label, frac, col) in enumerate(specs):
            ry = y0 + row * (bh + gap)
            # Track
            draw.rectangle([(x0, ry), (x0 + bw, ry + bh)],
                           fill=_WHITE_GHOST, outline=_fade(col, 0.25), width=1)
            # Fill — segment flicker near empty
            fw = int(bw * max(0.0, min(1.0, frac)))
            if fw > 0:
                fill_col = _RED if frac < 0.25 else col
                draw.rectangle([(x0, ry), (x0 + fw, ry + bh)], fill=_fade(fill_col, 0.8))
            # Numeric label at left
            draw.text((x0 - 4, ry + bh // 2), label,
                      font=self._f_xs, fill=_fade(col, 0.5), anchor="rm")
            # Percentage at right
            pct = f"{int(frac * 100)}%"
            draw.text((x0 + bw + 4, ry + bh // 2), pct,
                      font=self._f_xs, fill=_fade(col, 0.7), anchor="lm")

    # ------------------------------------------------------------------
    # Bottom-left ability cluster
    # ------------------------------------------------------------------

    def _draw_ability_cluster(self, draw: ImageDraw.ImageDraw, state: HudState) -> None:
        if not state.abilities:
            return

        size_map = {
            AbilitySize.MAIN:     27,
            AbilitySize.TACTICAL: 18,
            AbilitySize.PASSIVE:  13,
        }

        # Layout: compute total width to left-anchor near bottom-left
        radii   = [size_map[ab.size] for ab in state.abilities]
        padding = 10
        total_w = sum(r * 2 for r in radii) + padding * (len(radii) - 1)
        start_x = 18
        cy_base = self.height - 18

        x = start_x
        for ab, r in zip(state.abilities, radii):
            cx = x + r
            cy = cy_base - r - 24   # 24 px above the bottom for key labels

            # Background circle
            col_rgba  = _hex(ab.color)
            bg_alpha  = 60 if ab.ready else 30
            draw.ellipse([(cx - r, cy - r), (cx + r, cy + r)],
                         fill=_fade(col_rgba, bg_alpha / 255),
                         outline=_fade(col_rgba, 180), width=2)

            # Cooldown arc (remaining fraction)
            if not ab.ready:
                _arc_cooldown(draw, cx, cy, r - 2, ab.cooldown_fraction,
                              _fade(col_rgba, 200), width=2)

            # Icon glyph
            glyph = ab.icon_glyph or ab.name[:2].upper()
            draw.text((cx, cy), glyph, font=self._f_sm,
                      fill=_fade(_WHITE, 200 if ab.ready else 100), anchor="mm")

            # Key prompt
            draw.text((cx, cy + r + 4), ab.key,
                      font=self._f_xs, fill=_fade(_WHITE, 150), anchor="mt")

            # Name label
            draw.text((cx, cy + r + 14), ab.name[:7].upper(),
                      font=self._f_xs, fill=_fade(col_rgba, 120), anchor="mt")

            x += r * 2 + padding

    # ------------------------------------------------------------------
    # Bottom-right weapon readout
    # ------------------------------------------------------------------

    def _draw_weapon_readout(self, draw: ImageDraw.ImageDraw, state: HudState) -> None:
        w = state.weapon
        pw, ph = min(170, self.width // 8), 80
        x0 = self.width - pw - 16
        y0 = self.height - ph - 16

        # Background panel
        _draw_rounded_rect(draw, (x0, y0, x0 + pw, y0 + ph),
                           radius=4, fill=_PANEL_BG, outline=_PANEL_BDR, width=1)

        # Weapon name + fire mode
        draw.text((x0 + 8, y0 + 7), w.name,
                  font=self._f_xs, fill=_fade(_CYAN, 0.6))
        draw.text((x0 + pw - 8, y0 + 7), w.fire_mode,
                  font=self._f_xs, fill=_fade(_AMBER, 0.7), anchor="ra")

        # Ammo count — large
        ammo_str = str(w.ammo_current)
        draw.text((x0 + pw - 8, y0 + 38), ammo_str,
                  font=self._f_lg, fill=_WHITE, anchor="rb")

        # Reserve count — smaller, dimmer
        reserve_str = f"/ {w.ammo_reserve}"
        draw.text((x0 + pw - 8, y0 + 54), reserve_str,
                  font=self._f_sm, fill=_fade(_WHITE, 0.45), anchor="rb")

        # Ammo pips
        pips = w.mag_size
        pip_w, pip_h, pip_gap = 3, 8, 2
        pips_per_row = min(pips, (pw - 16) // (pip_w + pip_gap))
        for i in range(pips):
            spent  = i >= w.ammo_current
            col    = _fade(_CYAN, 0.2) if spent else _fade(_CYAN, 0.75)
            px     = x0 + 8 + (i % pips_per_row) * (pip_w + pip_gap)
            row    = i // pips_per_row
            py_top = y0 + ph - 14 - row * (pip_h + 2)
            draw.rectangle([(px, py_top), (px + pip_w, py_top + pip_h)], fill=col)

    # ------------------------------------------------------------------
    # Bottom-left system status
    # ------------------------------------------------------------------

    def _draw_system_status(self, draw: ImageDraw.ImageDraw, state: HudState) -> None:
        status_colors = {
            SystemStatus.ONLINE:   _CYAN,
            SystemStatus.DEGRADED: _AMBER,
            SystemStatus.OFFLINE:  _RED,
        }
        col   = status_colors.get(state.system_status, _WHITE)
        parts = [
            f"SYS:{state.system_status.value}",
            f"CAM:{state.camera_fps:.0f}FPS",
            f"HDG:{state.compass_heading:.0f}°",
        ]
        draw.text((16, self.height - 14), "  ".join(parts),
                  font=self._f_xs, fill=_fade(col, 0.5))