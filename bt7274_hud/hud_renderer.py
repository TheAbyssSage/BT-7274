"""PIL-based HUD drawing engine for BT-7274 Pilot HUD."""

from typing import Any, Optional

from PIL import Image, ImageDraw, ImageFont

from bt7274_hud.hud_data import HudState


def hex_to_rgba(hex_color: str, alpha: int = 255) -> tuple[int, int, int, int]:
    """Convert '#RRGGBB' or 'RRGGBB' or '#RGB' to (R, G, B, A)."""
    hex_color = hex_color.lstrip("#")
    if len(hex_color) == 3:
        hex_color = "".join(c * 2 for c in hex_color)
    if len(hex_color) != 6:
        raise ValueError(f"Invalid hex color: {hex_color}")
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    return (r, g, b, alpha)


class HudRenderer:
    """Draws HUD overlays onto a PIL Image."""

    # Titanfall 2 palette
    COLOR_HUD_GREEN = "#00ff88"
    COLOR_HUD_BLUE = "#00aaff"
    COLOR_HUD_RED = "#ff4444"
    COLOR_HUD_YELLOW = "#ffcc00"
    COLOR_HUD_WHITE = "#ffffff"
    COLOR_PANEL_BG = "#0a0a0a"
    COLOR_PANEL_BORDER = "#00ff88"

    def __init__(self, width: int = 1280, height: int = 720):
        self.width = width
        self.height = height
        self._font: Any = None
        self._font_small: Any = None
        self._load_fonts()

    def _load_fonts(self):
        """Try to load a clean monospaced font; fall back to default."""
        candidates = [
            "/System/Library/Fonts/Menlo.ttc",          # macOS
            "/System/Library/Fonts/Courier.dfont",      # macOS fallback
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",  # Linux
            "C:/Windows/Fonts/consola.ttf",               # Windows
        ]
        for path in candidates:
            try:
                self._font = ImageFont.truetype(path, 14)
                self._font_small = ImageFont.truetype(path, 11)
                return
            except Exception:
                continue
        self._font = ImageFont.load_default()
        self._font_small = ImageFont.load_default()

    def composite(self, background: Image.Image, state: HudState) -> Image.Image:
        """
        Composite HUD overlays on top of the background camera frame.
        Returns a new RGBA image.
        """
        # Ensure background is RGBA
        if background.mode != "RGBA":
            bg = background.convert("RGBA")
        else:
            bg = background.copy()

        overlay = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        self._draw_reticle(draw, state)
        self._draw_minimap(draw, state)
        self._draw_status_bar(draw, state)
        self._draw_comms_panel(draw, state)
        self._draw_event_cards(draw, state)
        self._draw_ability_cluster(draw, state)
        self._draw_weapon_readout(draw, state)
        self._draw_notification_feed(draw, state)
        self._draw_system_status(draw, state)

        # Composite overlay onto background
        bg.paste(overlay, (0, 0), overlay)
        return bg

    # ------------------------------------------------------------------
    # Drawing helpers
    # ------------------------------------------------------------------

    def _draw_reticle(self, draw: ImageDraw.ImageDraw, state: HudState):
        """Small precise white reticle in the center."""
        cx, cy = self.width // 2, self.height // 2
        size = 12
        color = hex_to_rgba(self.COLOR_HUD_WHITE, 200)
        # Crosshair: 4 short lines
        gap = 4
        # Top
        draw.line([(cx, cy - gap - size), (cx, cy - gap)], fill=color, width=1)
        # Bottom
        draw.line([(cx, cy + gap), (cx, cy + gap + size)], fill=color, width=1)
        # Left
        draw.line([(cx - gap - size, cy), (cx - gap, cy)], fill=color, width=1)
        # Right
        draw.line([(cx + gap, cy), (cx + gap + size, cy)], fill=color, width=1)
        # Center dot
        draw.ellipse([(cx - 1, cy - 1), (cx + 1, cy + 1)], fill=color)

    def _draw_minimap(self, draw: ImageDraw.ImageDraw, state: HudState):
        """Top-left circular minimap."""
        size = 120
        margin = 20
        x0, y0 = margin, margin
        x1, y1 = x0 + size, y0 + size
        # Outer ring
        draw.ellipse([(x0, y0), (x1, y1)], outline=hex_to_rgba(self.COLOR_HUD_GREEN, 180), width=2)
        # Inner cross
        cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
        draw.line([(cx, y0 + 10), (cx, y1 - 10)], fill=hex_to_rgba(self.COLOR_HUD_GREEN, 100), width=1)
        draw.line([(x0 + 10, cy), (x1 - 10, cy)], fill=hex_to_rgba(self.COLOR_HUD_GREEN, 100), width=1)
        # Player triangle (center, pointing up)
        tri = [(cx, cy - 6), (cx - 4, cy + 4), (cx + 4, cy + 4)]
        draw.polygon(tri, fill=hex_to_rgba(self.COLOR_HUD_WHITE, 220))
        # Markers
        for m in state.ally_markers:
            mx = x0 + int(m.x * size)
            my = y0 + int(m.y * size)
            draw.ellipse([(mx - 3, my - 3), (mx + 3, my + 3)], fill=hex_to_rgba(self.COLOR_HUD_BLUE, 200))
        for m in state.threat_markers:
            mx = x0 + int(m.x * size)
            my = y0 + int(m.y * size)
            draw.ellipse([(mx - 3, my - 3), (mx + 3, my + 3)], fill=hex_to_rgba(self.COLOR_HUD_RED, 200))
        # Label
        draw.text((x0, y1 + 6), "TACMAP", font=self._font_small, fill=hex_to_rgba(self.COLOR_HUD_GREEN, 180))

    def _draw_status_bar(self, draw: ImageDraw.ImageDraw, state: HudState):
        """Top-center horizontal mission progress bar."""
        bar_w, bar_h = 240, 8
        x0 = (self.width - bar_w) // 2
        y0 = 30
        # Background track
        draw.rectangle([(x0, y0), (x0 + bar_w, y0 + bar_h)], outline=hex_to_rgba(self.COLOR_HUD_GREEN, 120), width=1)
        # Filled portion (left = ally/mission, right = threat/remaining)
        fill_w = int(bar_w * state.mission_progress)
        if fill_w > 0:
            draw.rectangle([(x0, y0), (x0 + fill_w, y0 + bar_h)], fill=hex_to_rgba(self.COLOR_HUD_BLUE, 160))
        # Center icon (neutral diamond)
        cx = x0 + bar_w // 2
        diamond = [(cx, y0 - 6), (cx + 6, y0 + bar_h // 2), (cx, y0 + bar_h + 6), (cx - 6, y0 + bar_h // 2)]
        draw.polygon(diamond, outline=hex_to_rgba(self.COLOR_HUD_WHITE, 200), fill=hex_to_rgba(self.COLOR_HUD_GREEN, 80))

    def _draw_comms_panel(self, draw: ImageDraw.ImageDraw, state: HudState):
        """Top-right holographic comms panel."""
        w, h = 220, 80
        x0 = self.width - w - 20
        y0 = 20
        # Semi-transparent background
        draw.rectangle([(x0, y0), (x0 + w, y0 + h)], fill=hex_to_rgba(self.COLOR_PANEL_BG, 140), outline=hex_to_rgba(self.COLOR_HUD_GREEN, 160), width=1)
        # Header
        draw.text((x0 + 8, y0 + 6), "COMMS", font=self._font_small, fill=hex_to_rgba(self.COLOR_HUD_GREEN, 200))
        # Body text
        if state.comms_text:
            draw.text((x0 + 8, y0 + 26), state.comms_text[:60], font=self._font, fill=hex_to_rgba(self.COLOR_HUD_WHITE, 220))

    def _draw_event_cards(self, draw: ImageDraw.ImageDraw, state: HudState):
        """Middle-left compact cards for key events."""
        x0 = 20
        y0 = self.height // 2 - 40
        card_w = 180
        card_h = 28
        gap = 6
        for i, card in enumerate(state.event_cards[:3]):
            y = y0 + i * (card_h + gap)
            draw.rectangle([(x0, y), (x0 + card_w, y + card_h)], fill=hex_to_rgba(self.COLOR_PANEL_BG, 160), outline=hex_to_rgba(self.COLOR_HUD_GREEN, 140), width=1)
            draw.text((x0 + 8, y + 6), card[:32], font=self._font, fill=hex_to_rgba(self.COLOR_HUD_WHITE, 220))

    def _draw_ability_cluster(self, draw: ImageDraw.ImageDraw, state: HudState):
        """Bottom-left/center stack of circular ability icons."""
        icon_r = 22
        gap = 16
        total_w = len(state.abilities) * (icon_r * 2 + gap) - gap
        x0 = (self.width // 2) - (total_w // 2)
        y0 = self.height - 90
        for i, ability in enumerate(state.abilities[:5]):
            cx = x0 + i * (icon_r * 2 + gap) + icon_r
            cy = y0 + icon_r
            # Circle
            color = hex_to_rgba(ability.color, 180)
            draw.ellipse([(cx - icon_r, cy - icon_r), (cx + icon_r, cy + icon_r)], outline=color, width=2)
            if ability.cooldown <= 0:
                draw.ellipse([(cx - icon_r + 4, cy - icon_r + 4), (cx + icon_r - 4, cy + icon_r - 4)], fill=color)
            # Key label
            draw.text((cx, cy + icon_r + 4), ability.key, font=self._font_small, fill=hex_to_rgba(self.COLOR_HUD_WHITE, 200), anchor="mm")
            # Name under key
            draw.text((cx, cy + icon_r + 18), ability.name[:8], font=self._font_small, fill=hex_to_rgba(self.COLOR_HUD_WHITE, 180), anchor="mm")

    def _draw_weapon_readout(self, draw: ImageDraw.ImageDraw, state: HudState):
        """Bottom-right weapon silhouette + ammo counts."""
        x0 = self.width - 160
        y0 = self.height - 80
        w = state.weapon
        # Silhouette placeholder: rounded rect
        draw.rounded_rectangle([(x0, y0), (x0 + 140, y0 + 50)], radius=4, outline=hex_to_rgba(self.COLOR_HUD_GREEN, 160), width=1)
        # Weapon name
        draw.text((x0 + 8, y0 + 6), w.name, font=self._font, fill=hex_to_rgba(self.COLOR_HUD_WHITE, 220))
        # Ammo
        ammo_text = f"{w.ammo_current} / {w.ammo_reserve}"
        draw.text((x0 + 8, y0 + 26), ammo_text, font=self._font, fill=hex_to_rgba(self.COLOR_HUD_GREEN, 220))

    def _draw_notification_feed(self, draw: ImageDraw.ImageDraw, state: HudState):
        """Right-side horizontal notification feed (kill-feed style)."""
        x0 = self.width - 260
        y0 = self.height - 140
        line_h = 18
        for i, note in enumerate(state.notifications[:4]):
            y = y0 + i * line_h
            draw.text((x0, y), note.text[:50], font=self._font_small, fill=hex_to_rgba(note.color, 200))

    def _draw_system_status(self, draw: ImageDraw.ImageDraw, state: HudState):
        """Tiny status in bottom-left corner."""
        draw.text((20, self.height - 24), f"SYS: {state.system_status}", font=self._font_small, fill=hex_to_rgba(self.COLOR_HUD_GREEN, 160))
