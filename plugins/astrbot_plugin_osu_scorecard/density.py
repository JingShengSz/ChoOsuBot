"""Beatmap object density and failed-play position for the score card.

The 26 equal-duration buckets follow yumu-bot's Density data.  A failed
score's judgement count selects a hit-object timestamp, so the marker is at
the object's time rather than at a fraction of the chart's bucket count.
"""
from __future__ import annotations

import base64
import struct
import zlib

BUCKETS = 26


def hit_object_times(osu_text: str) -> list[int]:
    """Start times (ms) of mania notes/holds in an .osu [HitObjects] section."""
    in_objects = False
    times = []
    for raw in osu_text.splitlines():
        line = raw.strip()
        if line.startswith("[") and line.endswith("]"):
            in_objects = line == "[HitObjects]"
            continue
        if not in_objects or not line or line.startswith("//"):
            continue
        parts = line.split(",", 5)
        if len(parts) < 4:
            continue
        try:
            time_ms, kind = int(parts[2]), int(parts[3])
        except ValueError:
            continue
        if kind & 129:  # circle (1) or mania hold (128)
            times.append(time_ms)
    return sorted(times)


def buckets(times: list[int], count: int = BUCKETS) -> list[int]:
    """Count object starts in equal spans from first to last object."""
    result = [0] * count
    if not times:
        return result
    duration = times[-1] - times[0]
    if duration <= 0:
        result[0] = len(times)
        return result
    for time_ms in times:
        index = min(count - 1, max(0, (time_ms - times[0]) * count // duration))
        result[index] += 1
    return result


def fail_progress(times: list[int], judged_objects: int) -> float | None:
    """Fraction of active map duration reached by a failed score.

    osu! does not expose a fail timestamp in its score payload.  Like yumu,
    use the number of judged objects to index the map's hit-object times.
    This is an estimate for mania maps whose long notes add extra judgements.
    """
    if len(times) < 2 or judged_objects <= 0:
        return None
    duration = times[-1] - times[0]
    if duration <= 0:
        return None
    index = min(len(times) - 1, judged_objects - 1)
    return max(0.0, min(1.0, (times[index] - times[0]) / duration))


def encode_times(times: list[int]) -> str:
    """Compact timestamps for the existing disk cache (roughly 4 KB/map)."""
    if not times:
        return ""
    raw = struct.pack(f"<{len(times)}I", *times)
    return base64.b64encode(zlib.compress(raw, 6)).decode("ascii")


def decode_times(value: str) -> list[int]:
    try:
        raw = zlib.decompress(base64.b64decode(value, validate=True))
        if len(raw) % 4 or len(raw) > 4 * 100_000:
            return []
        return list(struct.unpack(f"<{len(raw) // 4}I", raw))
    except (ValueError, zlib.error, struct.error):
        return []
