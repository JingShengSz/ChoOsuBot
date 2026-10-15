from __future__ import annotations

import lzma
import json
import math
import struct
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .models import ReplayData, ReplayPress


def _read_uleb128(buf: memoryview, off: int) -> tuple[int, int]:
    n = 0
    shift = 0
    while True:
        if off >= len(buf):
            raise ValueError("eof uleb")
        b = buf[off]
        off += 1
        n |= (b & 0x7F) << shift
        if not (b & 0x80):
            return n, off
        shift += 7
        if shift > 35:
            raise ValueError("uleb overflow")


def _read_string(buf: memoryview, off: int) -> tuple[str | None, int]:
    """osr string: 0x00 = empty, 0x0b + ULEB128 length + UTF-8 (SerializationReader)."""
    if off >= len(buf):
        raise ValueError("eof string")
    marker = buf[off]
    off += 1
    if marker == 0:
        return None, off
    # BinaryWriter / osu SerializationReader: 0x0b then 7-bit/ULEB128 length
    n, off = _read_uleb128(buf, off)
    if n < 0 or off + n > len(buf):
        raise ValueError(f"eof string body n={n}")
    raw = bytes(buf[off : off + n])
    off += n
    return raw.decode("utf-8", "replace"), off


def _read_bytes(buf: memoryview, off: int) -> tuple[bytes | None, int]:
    if off + 4 > len(buf):
        raise ValueError("eof bytes len")
    (n,) = struct.unpack_from("<i", buf, off)
    off += 4
    if n < 0:
        return None, off
    if n == 0:
        return b"", off
    raw = bytes(buf[off : off + n])
    off += n
    return raw, off


# osu!stable's mod bitmask, as stored in the `.osr` header. Only the one bit this
# renderer acts on is named; the field itself is a plain int.
MOD_MIRROR = 1 << 30


@dataclass
class OsrHeader:
    ruleset_id: int = 0
    version: int = 0
    beatmap_md5: str = ""
    username: str = ""
    mods: int = 0
    replay_bytes: bytes | None = field(default=None)
    # The judgement counts the GAME recorded, read out of the header.  These are
    # ground truth: comparing them against what the renderer derives from the
    # replay is the only honest way to check a judgement implementation.
    # Mapping (osu.Game/Scoring/Legacy/ScoreInfoExtensions.cs):
    #   count_geki -> Perfect   count_300 -> Great   count_katu -> Good
    #   count_100  -> Ok        count_50  -> Meh     count_miss -> Miss
    count_300: int = 0
    count_100: int = 0
    count_50: int = 0
    count_geki: int = 0
    count_katu: int = 0
    count_miss: int = 0
    score: int = 0
    max_combo: int = 0
    ended_at: str | None = None
    # Lazer stores complete mods/settings and statistics after the legacy payload.
    mods_detail: list[dict] = field(default_factory=list)
    maximum_statistics: dict = field(default_factory=dict)

    @property
    def clock_rate(self) -> float:
        for mod in self.mods_detail:
            acronym = mod.get("acronym")
            if acronym in ("DT", "NC", "HT", "DC"):
                value = float(mod.get("settings", {}).get("speed_change", 1.5 if acronym in ("DT", "NC") else .75))
                if not math.isfinite(value) or value <= 0:
                    raise ValueError("回放倍速设置无效")
                return value
        return 1.5 if self.mods & (64 | 512) else .75 if self.mods & 256 else 1.0

    @property
    def counts(self) -> dict[str, int]:
        """The header counts keyed by lazer result names."""
        return {
            "perfect": self.count_geki,
            "great": self.count_300,
            "good": self.count_katu,
            "ok": self.count_100,
            "meh": self.count_50,
            "miss": self.count_miss,
        }

    @property
    def mirror(self) -> bool:
        """ManiaModMirror was active for this play.

        The .osu on disk is never rewritten by a mod, so a mirrored play's replay
        records key presses against MIRRORED columns while the beatmap file still
        describes the unmirrored chart. Anything that pairs presses with hit objects
        has to apply the same flip (`OsuBeatmap.apply_mirror`) or every judgement
        lands on the wrong lane.
        """
        return bool(self.mods & MOD_MIRROR) or any(m.get("acronym") == "MR" for m in self.mods_detail)


def parse_osr(path: str | Path) -> tuple[OsrHeader, ReplayData]:
    data = Path(path).read_bytes()
    buf = memoryview(data)
    off = 0

    head = OsrHeader()
    head.ruleset_id = buf[off]
    off += 1
    (head.version,) = struct.unpack_from("<i", buf, off)
    off += 4
    head.beatmap_md5, off = _read_string(buf, off)
    head.username, off = _read_string(buf, off)
    _, off = _read_string(buf, off)  # replay hash
    # judgement counts — read them, they are the game's own tally
    (head.count_300, head.count_100, head.count_50,
     head.count_geki, head.count_katu, head.count_miss) = struct.unpack_from("<6H", buf, off)
    off += 2 * 6
    (head.score,) = struct.unpack_from("<i", buf, off)
    off += 4  # score
    (head.max_combo,) = struct.unpack_from("<H", buf, off)
    off += 2  # max combo
    off += 1  # perfect
    (head.mods,) = struct.unpack_from("<i", buf, off)
    off += 4  # mods
    _, off = _read_string(buf, off)  # life bar
    (ticks,) = struct.unpack_from('<q',buf,off)
    try:
        head.ended_at=(datetime(1,1,1,tzinfo=timezone.utc)+timedelta(microseconds=ticks//10)).isoformat() if ticks>0 else None
    except OverflowError:
        head.ended_at=None
    off += 8  # timestamp
    blob, off = _read_bytes(buf, off)
    head.replay_bytes = blob

    # LegacyScoreDecoder reads OnlineID, then an LZMA-compressed JSON score for
    # versions >= 30000001. The legacy bitmask cannot represent HO or DT settings.
    if head.version >= 30000001 and off + 12 <= len(buf):
        off += 8  # LegacyOnlineID
        extra, off = _read_bytes(buf, off)
        if extra:
            score_info = json.loads(lzma.decompress(extra, format=lzma.FORMAT_ALONE))
            head.mods_detail = score_info.get("mods", [])
            head.maximum_statistics = score_info.get("maximum_statistics", {})
            statistics = score_info.get("statistics")
            if statistics is not None:
                for name, attr in {"perfect":"count_geki", "great":"count_300", "good":"count_katu",
                                   "ok":"count_100", "meh":"count_50", "miss":"count_miss"}.items():
                    setattr(head, attr, int(statistics.get(name, 0)))

    if head.ruleset_id != 3:
        raise ValueError(f"replay ruleset {head.ruleset_id} is not mania (3)")

    replay = ReplayData()
    # LegacyScoreDecoder: `scoreInfo.IsLegacyScore = version < FIRST_LAZER_VERSION`
    # and a legacy (osu!stable) score then gets ModClassic appended, which flips
    # ManiaHitWindows to the classic window set. Note this is the SCORE encoder's
    # constant (30_000_000), not the beatmap encoder's (128).
    replay.classic = head.version < 30000000
    # The header's own counts decide the object model and pin the final accuracy
    # -- see mania_render/judge.py.
    replay.counts = head.counts
    if not blob:
        return head, replay

    # 5-byte LZMA props + 8-byte uncompressed size + payload
    raw = lzma.decompress(blob, format=lzma.FORMAT_ALONE)
    text = raw.decode("utf-8", "replace")
    t = 0
    prev_mask = 0
    frames = text.split(",")
    for fr in frames:
        fr = fr.strip()
        if not fr:
            continue
        parts = fr.split("|")
        # LegacyScoreDecoder: `if (split.Length < 4) continue;` — a frame with
        # fewer than four fields is DROPPED, not parsed.  Accepting 2- and
        # 3-field frames (as this did) invents presses the game never saw.
        if len(parts) < 4:
            continue
        try:
            w = int(float(parts[0]))
            x = int(float(parts[1]))
        except ValueError:
            continue
        if w == -12345:
            continue
        y = int(float(parts[2])) if len(parts) > 2 else 0
        # The delta counts BEFORE the sentinel frames are dropped. Stable opens a replay
        # with two `(256, -500)` marker frames — "at time 0 and SkipBoundary - 1" — and
        # osu! itself accumulates every delta first and only then removes them
        # (LegacyScoreDecoder.readLegacyReplay: `lastTime += diff;` … then
        # `legacyFrames.RemoveAt(1)` / `RemoveAt(0)`). Dropping the delta instead throws
        # away the second marker's time, which is ordinarily -1 ms and therefore
        # invisible — but one real 2026-09-30 user render carried 5630 ms there, and its
        # whole press stream landed 5.63 s early (31.60 % HUD against a 99.12 % score).
        t += w
        if x == 256 and y == -500:
            continue
        mask = x & 0xFFFFF
        for bit in range(20):
            prev = (prev_mask >> bit) & 1
            cur = (mask >> bit) & 1
            if prev == 0 and cur == 1:
                replay.presses.append(ReplayPress(t, bit))
            elif prev == 1 and cur == 0:
                replay.releases.append(ReplayPress(t, bit))
        prev_mask = mask

    replay.presses.sort(key=lambda p: p.time_ms)
    replay.releases.sort(key=lambda p: p.time_ms)
    return head, replay
