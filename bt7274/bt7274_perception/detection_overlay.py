"""Detection overlay renderer for BT-7274 Perception.

Draws YOLO bounding boxes, labels, and HUD chrome in a Titanfall-inspired
style directly onto camera frames.
"""
from __future__ import annotations

import logging
from typing import List, Union

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from bt7274.bt7274_perception.yolo_engine import Detection

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Colour palette — Titanfall 2 HUD inspired
# ---------------------------------------------------------------------------

_CYAN       = (0,   220, 180)
_CYAN_DIM   = (0,   160, 130)
_BLUE       = (0,   160, 255)
_RED        = (255,  60,  60)
_AMBER      = (255, 190,  40)
_GREEN      = (0,   230, 100)
_WHITE      = (220, 240, 255)
_WHITE_DIM  = (160, 200, 220)

# Per-class label colours
_CLASS_COLORS: dict[str, tuple[int, int, int]] = {
    "person":       _CYAN,
    "car":          _BLUE,
    "truck":        _BLUE,
    "motorcycle":   _BLUE,
    "bicycle":      _BLUE,
    "dog":          _AMBER,
    "cat":          _AMBER,
    "bird":         _AMBER,
    "horse":        _AMBER,
    "cell phone":   _GREEN,
    "laptop":       _GREEN,
    "backpack":     _GREEN,
    "knife":        _RED,
    "scissors":     _RED,
    "weapon":       _RED,
    "gun":          _RED,
}


class DetectionOverlay:
    """Draws bounding boxes, labels, and HUD chrome onto frames.

    Usage:
        overlay = DetectionOverlay(width=1280, height=720)
        output_frame = overlay.draw(frame_array, yolo_detections)
    """

    def __init__(self, width: int = 1280, height: int = 720):
        self.width = width
        self.height = height

        # Font — try monospace, fall back to PIL default
        self._font: ImageFont.FreeTypeFont | ImageFont.ImageFont
        try:
            self._font = ImageFont.truetype(
                "/System/Library/Fonts/Menlo.ttc", size=12,
            )
        except (OSError, IOError):
            try:
                self._font = ImageFont.truetype(
                    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
                    size=12,
                )
            except (OSError, IOError):
                self._font = ImageFont.load_default()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def draw(
        self,
        frame: Union[np.ndarray, Image.Image],
        detections: List[Detection],
    ) -> np.ndarray:
        """Draw all overlays onto *frame* and return the composited RGB array.

        Args:
            frame: RGB image as numpy (H,W,3) uint8 or PIL Image.
            detections: YOLO object detections to draw.

        Returns:
            RGB numpy array (H, W, 3) uint8 with overlays drawn.
        """
        # Convert to PIL for drawing
        if isinstance(frame, np.ndarray):
            pil_img = Image.fromarray(frame)
        else:
            pil_img = frame.convert("RGB")

        # Resize if needed
        if pil_img.size != (self.width, self.height):
            pil_img = pil_img.resize(
                (self.width, self.height), Image.Resampling.LANCZOS,
            )

        draw = ImageDraw.Draw(pil_img)

        # HUD chrome (corner brackets)
        self._draw_corner_brackets(draw)

        # YOLO detection boxes
        for det in detections:
            self._draw_detection_box(draw, det)

        # Status bar
        self._draw_status_bar(draw, len(detections))

        return np.array(pil_img)

    # ------------------------------------------------------------------
    # HUD chrome
    # ------------------------------------------------------------------

    def _draw_corner_brackets(self, draw: ImageDraw.ImageDraw) -> None:
        """Four corner bracket decorations — helmet-frame aesthetic."""
        arm = 32
        gap = 12
        w = 2
        c = (*_CYAN_DIM, 100)
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
    # Detection boxes
    # ------------------------------------------------------------------

    def _draw_detection_box(
        self, draw: ImageDraw.ImageDraw, det: Detection,
    ) -> None:
        """Draw a single YOLO detection bounding box with label."""
        color = _CLASS_COLORS.get(det.label, _WHITE_DIM)
        x1, y1, x2, y2 = det.x1, det.y1, det.x2, det.y2

        # Clamp to frame bounds
        x1 = max(0, min(x1, self.width - 1))
        y1 = max(0, min(y1, self.height - 1))
        x2 = max(0, min(x2, self.width - 1))
        y2 = max(0, min(y2, self.height - 1))

        # Double-line bounding box for HUD look
        draw.rectangle([(x1, y1), (x2, y2)], outline=color, width=1)
        draw.rectangle(
            [(x1 + 2, y1 + 2), (x2 - 2, y2 - 2)],
            outline=(*color, 80), width=1,
        )

        # Corner accents
        corner_len = min(12, (x2 - x1) // 4, (y2 - y1) // 4)
        for (cx, cy, dx, dy) in [
            (x1, y1, +1, +1),
            (x2, y1, -1, +1),
            (x1, y2, +1, -1),
            (x2, y2, -1, -1),
        ]:
            draw.line(
                [(cx, cy), (cx + dx * corner_len, cy)],
                fill=color, width=2,
            )
            draw.line(
                [(cx, cy), (cx, cy + dy * corner_len)],
                fill=color, width=2,
            )

        # Label pill
        label_text = f"{det.label} {det.confidence:.0%}"
        self._draw_label(draw, x1, y1 - 18, label_text, color)

    def _draw_label(
        self,
        draw: ImageDraw.ImageDraw,
        x: int,
        y: int,
        text: str,
        color: tuple[int, int, int],
    ) -> None:
        """Draw a label pill above a bounding box."""
        bbox = draw.textbbox((0, 0), text, font=self._font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        pad = 4

        # Clamp label position
        lx = max(0, x)
        ly = max(0, y - th - pad)

        # Background pill
        draw.rectangle(
            [(lx, ly), (lx + tw + pad * 2, ly + th + pad)],
            fill=(*color, 180),
        )
        # Left accent edge
        draw.rectangle(
            [(lx, ly), (lx + 2, ly + th + pad)],
            fill=(*color, 255),
        )
        # Text
        draw.text((lx + pad, ly), text, font=self._font, fill=(255, 255, 255))

    # ------------------------------------------------------------------
    # Status bar
    # ------------------------------------------------------------------

    def _draw_status_bar(
        self, draw: ImageDraw.ImageDraw, num_objects: int,
    ) -> None:
        """Draw a bottom status bar with detection count."""
        y = self.height - 20
        text = f"OBJECTS: {num_objects}"
        bbox = draw.textbbox((0, 0), text, font=self._font)
        tw = bbox[2] - bbox[0]

        # Background strip
        draw.rectangle(
            [(0, y - 2), (self.width, y + 18)],
            fill=(5, 15, 30, 140),
        )
        draw.line(
            [(0, y - 2), (self.width, y - 2)],
            fill=(*_CYAN_DIM, 100), width=1,
        )

        draw.text(
            (self.width - tw - 10, y), text,
            font=self._font, fill=_CYAN_DIM,
        )
