"""Fit long beatmap headings inside the left column of the score card."""
from __future__ import annotations

from PIL import Image, ImageDraw

from render import font_for


TITLE_X, TITLE_Y, RIGHT_EDGE = 104, 74, 660
ARTIST_X, ARTIST_Y = 60, 153
TITLE_LINE_STEP = 39


def _wrap(title: str, draw: ImageDraw.ImageDraw, font) -> list[str]:
    """Wrap at the measured right edge, preferring spaces when available."""
    words = title.split(" ")
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}" if current else word
        if draw.textlength(candidate, font=font) <= RIGHT_EDGE - TITLE_X:
            current = candidate
            continue
        if current:
            lines.append(current)
            current = ""
        for ch in word:
            if draw.textlength(current + ch, font=font) > RIGHT_EDGE - TITLE_X and current:
                lines.append(current)
                current = ""
            current += ch
    if current:
        lines.append(current)
    return lines


def render_wrapped_heading(title: str, artist: str) -> Image.Image | None:
    """Return a full-canvas transparent overlay only when the title overflows.

    The original title and artist text layers are blanked in that case. Sharing
    this overlay between the Pillow and Photoshop paths keeps their layout equal.
    """
    canvas = Image.new("RGBA", (1920, 1080))
    draw = ImageDraw.Draw(canvas)
    title_font = font_for("Inter18pt-Medium", 36, title, "YuGothic-Medium")
    if title_font is None or draw.textlength(title, font=title_font) <= RIGHT_EDGE - TITLE_X:
        return None
    lines = _wrap(title, draw, title_font)
    for size in range(35, 25, -1):
        if len(lines) <= 2:
            break
        title_font = font_for("Inter18pt-Medium", size, title, "YuGothic-Medium")
        lines = _wrap(title, draw, title_font)
    if len(lines) > 2:
        tail = " ".join(lines[1:]).strip()
        while tail and draw.textlength(tail + "…", font=title_font) > RIGHT_EDGE - TITLE_X:
            tail = tail[:-1]
        lines = [lines[0], tail.rstrip() + "…"]
    for index, line in enumerate(lines):
        # Match layer_mapping.json's ink top, not Pillow's font ascender.
        ink_top = draw.textbbox((0, 0), line, font=title_font)[1]
        draw.text((TITLE_X, TITLE_Y + index * TITLE_LINE_STEP - ink_top), line,
                  font=title_font, fill="#EAEEF6")
    artist_font = font_for("Inter18pt-Medium", 28, artist, "YuGothic-Medium")
    if artist_font is not None:
        if draw.textlength(artist, font=artist_font) > RIGHT_EDGE - ARTIST_X:
            while artist and draw.textlength(artist + "…", font=artist_font) > RIGHT_EDGE - ARTIST_X:
                artist = artist[:-1]
            artist = artist.rstrip() + "…"
        ink_top = draw.textbbox((0, 0), artist, font=artist_font)[1]
        draw.text((ARTIST_X, ARTIST_Y - ink_top), artist, font=artist_font,
                  fill="#8C97A9")
    return canvas
