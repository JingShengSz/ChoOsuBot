"""Raster pieces of the score card, drawn with Pillow.

The data-driven parts of the template are bitmaps, not text layers, so they have
to be generated per score:

  star_strip   the star-rating bar (pips + value badge + tier label)
  od_bar       OD progress bar
  hp_bar       HP progress bar
  avatar       the player avatar, clipped to the template's ellipse
  mod badges   one PNG per enabled mod, laid out at the template's pitch

The star strip is a faithful port of ``template/star_strip.js`` — same ramps,
same geometry, same partial-star fill. That file is the source of truth; if the
numbers here stop matching it, this port has drifted. ``self_test.py`` compares
a few values against the JS module to catch exactly that.

No AstrBot imports live here, so this module can be exercised standalone.
"""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont

# ─────────────────────────────── colour helpers ───────────────────────────────


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    h = str(value).strip().lstrip("#")
    if len(h) == 3:
        h = h[0] * 2 + h[1] * 2 + h[2] * 2
    n = int(h, 16)
    return (n >> 16) & 255, (n >> 8) & 255, n & 255


def rgb_to_hex(rgb) -> str:
    return "#" + "".join(f"{max(0, min(255, round(v))):02x}" for v in rgb)


def _lerp_hex(a: str, b: str, t: float) -> str:
    ca, cb = hex_to_rgb(a), hex_to_rgb(b)
    return rgb_to_hex([ca[i] + (cb[i] - ca[i]) * t for i in range(3)])


def ramp_color(ramp, value: float) -> str:
    if value <= ramp[0][0]:
        return ramp[0][1]
    if value >= ramp[-1][0]:
        return ramp[-1][1]
    for i in range(len(ramp) - 1):
        v0, c0 = ramp[i]
        v1, c1 = ramp[i + 1]
        if v0 <= value <= v1:
            t = 0.0 if v1 == v0 else (value - v0) / (v1 - v0)
            return _lerp_hex(c0, c1, t)
    return ramp[-1][1]


def luminance(value: str) -> float:
    r, g, b = hex_to_rgb(value)
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255


def mix(a: str, b: str, amount: float) -> str:
    return _lerp_hex(a, b, amount)


# ─────────────────────────────── ramps (mirror star_strip.js) ───────────────────────────────

STAR_RAMP = [
    (0.00, "#4fc3f7"), (2.00, "#7ed957"), (2.70, "#c9e83c"),
    (3.40, "#ffe94a"), (4.00, "#ff8c3c"), (4.70, "#ff4d6d"),
    (5.30, "#e040fb"), (6.50, "#7b8cff"), (7.60, "#6a6ae8"),
    (8.60, "#5b5be0"), (9.60, "#6250dc"), (10.60, "#6a45d8"),
    (12.00, "#7040d4"), (18.00, "#7a3ad0"),
]

NUM_RAMP = [
    (0.00, "#4fc3f7"), (2.00, "#7ed957"), (3.40, "#ffe94a"),
    (4.70, "#ff4d6d"), (5.30, "#e040fb"), (6.50, "#ffcb2e"),
    (7.32, "#ffcb2e"), (8.20, "#ffb022"), (9.00, "#ffa022"),
    (9.50, "#ff8a20"), (9.90, "#f4792b"), (10.00, "#ff3b5c"),
    (10.50, "#ff3b8e"), (11.00, "#ff3bd0"), (11.70, "#e83bf5"),
    (12.00, "#c04df5"), (12.70, "#a855f7"), (13.30, "#8b5cf6"),
    (14.30, "#5b6bff"), (16.00, "#4a5cff"),
]

TIERS = [
    {"label": "Easy",    "lo": 0.0, "hi": 2.0,      "range": "0.0 – 1.99",    "color": "#4fc3f7", "accent": "#4fc3f7"},
    {"label": "Normal",  "lo": 2.0, "hi": 2.7,      "range": "2.0 – 2.69",    "color": "#7ed957", "accent": "#7ed957"},
    {"label": "Hard",    "lo": 2.7, "hi": 4.0,      "range": "2.7 – 3.99",    "color": "#ffe94a", "accent": "#ffe94a"},
    {"label": "Insane",  "lo": 4.0, "hi": 5.3,      "range": "4.0 – 5.29",    "color": "#ff4d6d", "accent": "#ff4d6d"},
    {"label": "Expert",  "lo": 5.3, "hi": 6.5,      "range": "5.3 – 6.49",    "color": "#e040fb", "accent": "#e040fb"},
    {"label": "Expert+", "lo": 6.5, "hi": float("inf"), "range": "6.5 and above", "color": "#7b8cff", "accent": "#ffcb2e"},
]

DUAL_MODE = {"threshold": 10, "lowStars": 10, "highStars": 15, "baseSpacing": 1.24}

STRIP_DEFAULTS = {
    "starSize": 46,
    "spacing": 1.24,
    "badgeBg": "#2b3048",
    "emptyColor": "#5A6684",
    "emptyOpacity": 0.75,
    "capRatio": 0.66,
    "starStroke": "auto",
    "starStrokeWidth": 1.5,
    "starStrokeMinLum": 0.30,
    "starStrokeWhiteMix": 0.55,
    "showBadge": True,
    "showTier": True,
    "fadeTail": True,
}

# ─────────────────────────────── fonts ───────────────────────────────

_FONT_DIRS = [
    Path.home() / "AppData/Local/Microsoft/Windows/Fonts",
    Path("C:/Windows/Fonts"),
]

# The SVG asks for `Segoe UI` at weight 800; Inter ExtraBold is the closest
# resident match and is what the rest of the template already uses.
#
# `seguiemj.ttf` is Segoe UI EMOJI. It ships with Windows so it always exists, and it
# used to be first in this list — meaning every bold glyph on the star strip (the SR
# number, the tier label) was being drawn in the emoji font. Inter goes first now.
_FONT_CANDIDATES = {
    "bold":    ["Inter_18pt-ExtraBold.ttf", "Inter_18pt-Bold.ttf",
                "segoeuib.ttf", "arialbd.ttf"],
    "regular": ["Inter_18pt-Regular.ttf", "segoeui.ttf", "arial.ttf"],
    "medium":  ["Inter_18pt-Medium.ttf", "Inter_18pt-Regular.ttf", "segoeui.ttf"],
}

_font_cache: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}


def _font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    size = max(1, int(round(size)))
    key = (weight, size)
    if key in _font_cache:
        return _font_cache[key]
    for name in _FONT_CANDIDATES.get(weight, []):
        for d in _FONT_DIRS:
            p = d / name
            if p.is_file():
                try:
                    f = ImageFont.truetype(str(p), size)
                    _font_cache[key] = f
                    return f
                except OSError:
                    continue
    f = ImageFont.load_default(size)
    _font_cache[key] = f
    return f


def _text_width(draw: ImageDraw.ImageDraw, text: str, font) -> float:
    return draw.textlength(text, font=font)


# ─────────────────────────────── star strip ───────────────────────────────


def _star_points(cx: float, cy: float, r_out: float, r_in: float):
    pts = []
    for i in range(10):
        rad = r_out if i % 2 == 0 else r_in
        a = -math.pi / 2 + i * math.pi / 5
        pts.append((cx + rad * math.cos(a), cy + rad * math.sin(a)))
    return pts


def _spacing_for_same_width(n_from: int, sp_from: float, n_to: int) -> float:
    span = sp_from * (n_from - 1) + 1
    return (span - 1) / (n_to - 1)


def _tier_of(value: float) -> dict:
    for t in TIERS:
        if t["lo"] <= value < t["hi"]:
            return t
    return TIERS[-1]


def _paint_strip(value: float, star_size: float, star_count: int, scale_max: int,
                 spacing: float, opts: dict) -> tuple[Image.Image, dict]:
    """One pass of the strip at a given star size. Returns (image, metrics)."""
    pad = round(star_size * 0.42)
    R = star_size / 2
    pitch = star_size * spacing

    tier = _tier_of(value)
    star_color = ramp_color(STAR_RAMP, value)
    num_color = ramp_color(NUM_RAMP, value)
    per_star = scale_max / star_count if star_count else 1

    # --- measure the badge first: its width feeds the layout ---
    badge_h = star_size * 0.96
    badge_font_size = badge_h * 0.50
    icon_r = badge_h * 0.27
    badge_pad_x = badge_h * 0.36
    badge_inner_gap = badge_h * 0.24
    val_str = f"{value:.2f}"

    probe = Image.new("RGBA", (8, 8))
    pd = ImageDraw.Draw(probe)
    badge_font = _font("bold", badge_font_size)
    text_w = _text_width(pd, val_str, badge_font)
    badge_w = badge_pad_x + icon_r * 2 + badge_inner_gap + text_w + badge_pad_x

    badge_star_gap = round(star_size * 0.42)
    stars_w = star_count * pitch - (pitch - star_size)
    tier_font_size = max(11.0, star_size * 0.30)
    tier_h = tier_font_size * 1.75 if opts["showTier"] else 0

    row_h = max(badge_h, star_size)
    W = int(round(pad * 2 + (badge_w + badge_star_gap if opts["showBadge"] else 0) + stars_w))
    H = int(round(pad * 2 + row_h + tier_h))
    W, H = max(1, W), max(1, H)

    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cy = pad + row_h / 2
    star_start_x = pad + (badge_w + badge_star_gap if opts["showBadge"] else 0)

    # --- badge ---
    if opts["showBadge"]:
        bx = pad
        by = cy - badge_h / 2
        brx = badge_h / 2
        badge_stroke = mix(opts["badgeBg"], num_color, 0.38)
        badge_fg = mix(num_color, "#ffffff", 0.30) if luminance(num_color) < 0.18 else num_color
        d.rounded_rectangle(
            [bx, by, bx + badge_w, by + badge_h], radius=brx,
            fill=hex_to_rgb(opts["badgeBg"]) + (255,),
            outline=hex_to_rgb(badge_stroke) + (255,), width=1,
        )
        icx = bx + badge_pad_x + icon_r
        d.polygon(_star_points(icx, cy, icon_r, icon_r * 0.45),
                  fill=hex_to_rgb(star_color) + (255,))
        tx = icx + icon_r + badge_inner_gap
        baseline = cy + badge_font_size * opts["capRatio"] / 2
        d.text((tx, baseline), val_str, font=badge_font,
               fill=hex_to_rgb(badge_fg) + (255,), anchor="ls")

    # --- pips ---
    empty_color = opts["emptyColor"] or star_color
    empty_base = max(0.0, min(1.0, opts["emptyOpacity"]))

    stroke_w = 0.0
    stroke_col = None
    if opts["starStroke"] and opts["starStroke"] != "none":
        explicit = isinstance(opts["starStroke"], str) and opts["starStroke"].startswith("#")
        if explicit or luminance(star_color) < opts["starStrokeMinLum"]:
            stroke_w = opts["starStrokeWidth"]
            stroke_col = opts["starStroke"] if explicit else mix(
                star_color, "#ffffff", opts["starStrokeWhiteMix"])

    past_fill = 0
    for i in range(star_count):
        cx = star_start_x + i * pitch + R
        filled = max(0.0, min(1.0, value / per_star - i))
        pts = _star_points(cx, cy, R, R * 0.45)

        if filled >= 0.999:
            op, fill_col = 1.0, star_color
            past_fill = 0
        elif filled > 0:
            op, fill_col = empty_base + (1 - empty_base) * filled, star_color
            past_fill = 1
        else:
            op = max(0.06, empty_base * (1 - 0.42 * past_fill)) if opts["fadeTail"] else empty_base
            fill_col = empty_color
            past_fill += 1

        if op > 0.001:
            lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            ImageDraw.Draw(lay).polygon(pts, fill=hex_to_rgb(fill_col) + (int(round(op * 255)),))
            img.alpha_composite(lay)

        # partial pip: the lit portion is clipped to the left `filled` of the pips box
        if 0.002 < filled < 0.998:
            lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            ImageDraw.Draw(lay).polygon(pts, fill=hex_to_rgb(star_color) + (255,))
            keep = Image.new("L", (W, H), 0)
            ImageDraw.Draw(keep).rectangle(
                [cx - R - 1, cy - R - 1, cx - R - 1 + 2 * R * filled, cy + R + 1], fill=255)
            lay.putalpha(ImageChops.multiply(lay.getchannel("A"), keep))
            img.alpha_composite(lay)

        if stroke_w > 0 and filled > 0.002:
            lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            ImageDraw.Draw(lay).polygon(pts, outline=hex_to_rgb(stroke_col) + (255,),
                                        width=max(1, int(round(stroke_w))))
            img.alpha_composite(lay)

    # --- tier label ---
    if opts["showTier"]:
        ty = pad + row_h + tier_font_size * 1.05
        tier_font = _font("bold", tier_font_size)
        d.text((star_start_x, ty), tier["label"], font=tier_font,
               fill=hex_to_rgb(tier["accent"]) + (255,), anchor="ls")
        tw = _text_width(d, tier["label"], tier_font)
        small = _font("regular", tier_font_size * 0.82)
        d.text((star_start_x + tw + tier_font_size * 0.6, ty), tier["range"], font=small,
               fill=(255, 255, 255, int(0.72 * 255)), anchor="ls")

    return img, {"width": W, "height": H, "tier": tier["label"], "starColor": star_color,
                 "numColor": num_color, "starSize": star_size}


def render_star_strip(value: float, width: int = 600, **overrides) -> Image.Image:
    """The star bar, locked to `width` px — the Python side of renderStarStripFit."""
    opts = {**STRIP_DEFAULTS, **overrides}
    v = max(0.0, float(value or 0))
    high = v > DUAL_MODE["threshold"]
    star_count = DUAL_MODE["highStars"] if high else DUAL_MODE["lowStars"]
    scale_max = DUAL_MODE["highStars"] if high else DUAL_MODE["lowStars"]
    spacing = (_spacing_for_same_width(DUAL_MODE["lowStars"], DUAL_MODE["baseSpacing"],
                                       DUAL_MODE["highStars"])
               if high else DUAL_MODE["baseSpacing"])

    probe, _ = _paint_strip(v, 46.0, star_count, scale_max, spacing, opts)
    k = probe.width / 46.0
    star_size = max(8.0, round((width / k) * 100) / 100)
    img, _ = _paint_strip(v, star_size, star_count, scale_max, spacing, opts)
    return img


# ─────────────────────────────── OD / HP bars ───────────────────────────────

def render_stat_bar(value: float, vmin: float, vmax: float, width: int = 600,
                    height: int = 12, radius: int = 6, tick_step: float = 1.0,
                    track_color: str = "#2E3543", tick_color: str = "#0B0D11",
                    tick_opacity: float = 0.5) -> Image.Image:
    """A rounded track with a ramp-coloured fill and ticks — the OD/HP bars."""
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    radius = min(radius, height // 2)

    span = (vmax - vmin) or 1.0
    frac = max(0.0, min(1.0, (float(value) - vmin) / span))
    # The JS side maps the FILL FRACTION onto the numeric ramp (domainMax 18),
    # so a bar's colour tracks how full it is, not the raw stat value.
    color = ramp_color(NUM_RAMP, frac * 18.0)

    d.rounded_rectangle([0, 0, width - 1, height - 1], radius=radius, fill=hex_to_rgb(track_color) + (255,))
    fill_w = int(round(width * frac))
    if fill_w > 0:
        d.rounded_rectangle([0, 0, max(1, fill_w) - 1, height - 1], radius=radius,
                            fill=hex_to_rgb(color) + (255,))

    if tick_step and tick_step > 0:
        n = int(round(span / tick_step))
        for i in range(1, n):
            x = width * (i * tick_step) / span
            d.rectangle([x - 0.5, 0, x + 0.5, height - 1],
                        fill=hex_to_rgb(tick_color) + (int(round(tick_opacity * 255)),))
    return img


# ─────────────────────────────── avatar ───────────────────────────────

AVATAR_BOX = (116, 116)  # layer_mapping.json: player_avatar 116x116 at (922,60)


def render_avatar(square: Image.Image, size: tuple[int, int] = AVATAR_BOX) -> Image.Image:
    """Clip a (already square) avatar into the template's ellipse."""
    w, h = size
    src = square.convert("RGBA").resize((w * 4, h * 4), Image.LANCZOS)
    mask = Image.new("L", (w * 4, h * 4), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, w * 4 - 1, h * 4 - 1], fill=255)
    mask = mask.resize((w, h), Image.LANCZOS)
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    out.paste(src.resize((w, h), Image.LANCZOS), (0, 0), mask)
    return out


# ─────────────────────────────── mod badges ───────────────────────────────

# 48px tall badges, pitch 110, first at x60 (layer_mapping.json mods_block).
MOD_PITCH = 110
MOD_FIRST_X = 60
MOD_Y = 842
MOD_HEIGHT = 48
MOD_SLOTS = 6


def render_mod_row(codes: list[str], assets_dir: Path,
                   pitch: int = MOD_PITCH, first_x: int = MOD_FIRST_X,
                   y: int = MOD_Y, height: int = MOD_HEIGHT) -> tuple[Image.Image, list[dict]]:
    """One 1920x1080 transparent sheet holding every badge that has art.

    Returns (sheet, placed) where `placed` lists {code, x, w} for the multis line.
    """
    sheet = Image.new("RGBA", (1920, 1080), (0, 0, 0, 0))
    placed: list[dict] = []
    slot = 0
    for code in codes:
        if slot >= MOD_SLOTS:
            break
        path = assets_dir / f"mod_{code.lower()}.png"
        if not path.is_file():
            continue
        badge = Image.open(path).convert("RGBA")
        scale = height / badge.height
        badge = badge.resize((max(1, round(badge.width * scale)), height), Image.LANCZOS)
        x = first_x + slot * pitch + 4  # +4 matches the template's placed badges
        sheet.alpha_composite(badge, (x, y))
        placed.append({"code": code, "x": x + badge.width // 2, "w": badge.width})
        slot += 1
    return sheet, placed


# ─────────────────────────────── background ───────────────────────────────


def cover_fit(image: Image.Image, size: tuple[int, int] = (1920, 1080)) -> Image.Image:
    """Scale-and-centre-crop, the way a wallpaper would be fitted."""
    tw, th = size
    src = image.convert("RGB")
    scale = max(tw / src.width, th / src.height)
    nw, nh = max(tw, round(src.width * scale)), max(th, round(src.height * scale))
    src = src.resize((nw, nh), Image.LANCZOS)
    left, top = (nw - tw) // 2, (nh - th) // 2
    return src.crop((left, top, left + tw, top + th))
