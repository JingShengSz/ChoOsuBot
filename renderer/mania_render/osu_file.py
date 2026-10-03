from __future__ import annotations

import re

from .models import (
    HIT_CIRCLE,
    HIT_LONGNOTE,
    HIT_SPINNER,
    HitObject,
    OsuBeatmap,
    TimingPoint,
)

_SECTION = re.compile(r"^\[([A-Za-z0-9]+)\]$")


def _column_from_x(x: int, keys: int) -> int:
    if keys <= 0:
        return 0
    return max(0, min(keys - 1, int(x * keys / 512.0)))


def parse_osu(text: str) -> OsuBeatmap:
    bm = OsuBeatmap()
    section = ""
    meta: dict[str, str] = {}
    diff: dict[str, str] = {}
    general: dict[str, str] = {}
    bg_name = ""

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("//"):
            continue
        m = _SECTION.match(line)
        if m:
            section = m.group(1)
            continue

        if section in ("General", "Metadata", "Difficulty") and ":" in line:
            k, _, v = line.partition(":")
            k, v = k.strip(), v.strip()
            if section == "Metadata":
                meta[k] = v
            elif section == "Difficulty":
                diff[k] = v
            else:
                general[k] = v
            continue

        if section == "Events":
            # 0,0,"bg.jpg",0,0
            if line.startswith("0,") and "," in line:
                parts = line.split(",")
                if len(parts) >= 3:
                    name = parts[2].strip().strip('"')
                    if name and not bg_name:
                        bg_name = name
            continue

        if section == "TimingPoints":
            parts = line.split(",")
            if len(parts) < 7:
                continue
            try:
                t0 = int(float(parts[0]))
                beat_len = float(parts[1])
                red = parts[6].strip() in ("1", "true", "True")
            except ValueError:
                continue
            bm.timings.append(TimingPoint(t0, beat_len, red))
            continue

        if section == "HitObjects":
            parts = line.split(",")
            if len(parts) < 4:
                continue
            try:
                x = int(parts[0])
                start = int(parts[2])
                flags = int(parts[3])
            except ValueError:
                continue
            end = start
            if flags & (HIT_LONGNOTE | HIT_SPINNER) and len(parts) >= 6:
                try:
                    end = int(parts[5].split(":")[0])
                except ValueError:
                    end = start
            is_hold = bool(flags & HIT_LONGNOTE)
            # mania: circle bit and hold bit; treat non-hold hitables as rice
            is_circle = bool(flags & HIT_CIRCLE) and not is_hold
            if not is_hold and not is_circle and not (flags & HIT_SPINNER):
                continue
            bm.hit_objects.append(
                HitObject(
                    flags=flags,
                    start_time=start,
                    end_time=end,
                    column=0,
                    is_hold=is_hold,
                    x=x,
                )
            )
            continue

    bm.mode = int(general.get("Mode", meta.get("Mode", "3")) or 3)
    bm.title = meta.get("Title", "")
    bm.artist = meta.get("Artist", "")
    bm.creator = meta.get("Creator", "")
    bm.version = meta.get("Version", "")
    bm.tags = meta.get("Tags", "")
    bm.audio_filename = general.get("AudioFilename", "audio.mp3") or "audio.mp3"
    bm.background_filename = bg_name
    bm.beatmap_id = meta.get("BeatmapID", "")
    bm.beatmapset_id = meta.get("BeatmapSetID", "")

    def f(key: str, default: float) -> float:
        try:
            return float(diff.get(key, default))
        except (TypeError, ValueError):
            return default

    bm.cs = f("CircleSize", 4.0)
    bm.od = f("OverallDifficulty", 5.0)
    bm.hp = f("HPDrainRate", 5.0)
    bm.ar = f("ApproachRate", 5.0)

    keys = bm.keys
    for h in bm.hit_objects:
        h.column = _column_from_x(h.x, keys)

    # stable order
    bm.hit_objects.sort(key=lambda h: (h.start_time, h.column))
    return bm
