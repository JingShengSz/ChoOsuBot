from __future__ import annotations

from dataclasses import dataclass

from .models import ManiaSkinBlock, OsuBeatmap

# lazer constants (osu-master DrawableManiaRuleset / Stage / LegacyManiaSkinConfiguration)
MIN_TIME_RANGE = 290.0
MAX_TIME_RANGE = 11485.0
LEGACY_DEFAULT_HIT_POS = (480 - 402) * 1.6  # 124.8, from bottom (LegacyManiaSkinConfiguration)
BASE_HEIGHT = 768.0
VIEW_W = 1920
VIEW_H = 1080


def compute_scroll_time(scroll_speed: float) -> float:
    """TimeRange_raw = 11485 / ScrollSpeed (ms). 30 → 382.83ms."""
    return MAX_TIME_RANGE / float(scroll_speed)


@dataclass
class PlayfieldGeometry:
    keys: int
    col_x: list[float]  # left edges in view pixels
    col_w: list[float]
    stage_left: float
    stage_right: float
    hit_y: float  # judgement line Y in view pixels
    scroll_len: float  # pixels above hit line used as time span
    time_range: float  # ms over scroll_len
    upside_down: bool
    scale: float  # 768-space → view


def build_geometry(
    block: ManiaSkinBlock,
    scroll_speed: float = 30.0,
    rate: float = 1.0,
) -> PlayfieldGeometry:
    keys = block.keys
    widths = block.column_width or [48.0] * keys
    if len(widths) < keys:
        widths = widths + [widths[-1] if widths else 48.0] * (keys - len(widths))
    widths = widths[:keys]

    # hit_position is already view Y from top (skin.ini HitPosition / 480 * 1080)
    hit_y_raw = float(block.hit_position)
    if hit_y_raw <= 0:
        hit_y_raw = 675.0
    # TimeRange scale from osu: lengthToHitPosition / 643.2
    # lengthToHitPosition ≈ hit line height from top in 768-space
    length_to_hit_768 = hit_y_raw * (BASE_HEIGHT / float(VIEW_H))
    scale_hit = length_to_hit_768 / (BASE_HEIGHT - LEGACY_DEFAULT_HIT_POS)
    time_range = compute_scroll_time(scroll_speed) * rate * max(0.15, scale_hit)

    view_scale = VIEW_H / BASE_HEIGHT

    stage_w768 = sum(widths)
    start_x_view = (VIEW_W - stage_w768 * view_scale) / 2.0

    col_x = []
    x = 0.0
    for w in widths:
        col_x.append(start_x_view + x * view_scale)
        x += w
    col_w = [w * view_scale for w in widths]
    stage_left = start_x_view
    stage_right = start_x_view + stage_w768 * view_scale

    hit_y = hit_y_raw
    if block.upside_down:
        hit_y = VIEW_H - hit_y
    scroll_len = hit_y if not block.upside_down else (VIEW_H - hit_y)
    return PlayfieldGeometry(
        keys=keys,
        col_x=col_x,
        col_w=col_w,
        stage_left=stage_left,
        stage_right=stage_right,
        hit_y=hit_y,
        scroll_len=scroll_len,
        time_range=time_range,
        upside_down=block.upside_down,
        scale=view_scale,
    )


def y_for_time(geom: PlayfieldGeometry, t_ms: float, now_ms: float) -> float:
    """Constant scroll: position along scroll axis from current-time origin (hit line)."""
    rel = (t_ms - now_ms) / geom.time_range * geom.scroll_len
    return (geom.hit_y - rel) if not geom.upside_down else (geom.hit_y + rel)


def red_bpm_display(bm: OsuBeatmap) -> tuple[float | None, float | None, float | None]:
    reds = bm.red_bpms
    if not reds:
        return None, None, None
    return sum(reds) / len(reds) if reds else None, min(reds), max(reds)
