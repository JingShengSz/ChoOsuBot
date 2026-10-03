"""Regression test for ManiaModMirror in the replay judgement path.

The bug: `.osr` mods were never read, so a play with Mirror (bit 30) had its presses
matched against the UNMIRRORED chart. Every judgement landed in the wrong lane and the
rendered HUD reported ~44 % accuracy for a 99.7 % score — on both engines, on any length.

What this test pins:
  * `OsrHeader.mods` is actually read, and `mirror` decodes bit 30.
  * `OsuBeatmap.apply_mirror()` is the game's transform: Column -> (keys-1) - Column.
  * Judged through the real `hud.build_from_replay` / `hud.judge_counts` path, a mirrored
    replay scores 100 % MAX when the flip is applied and mostly misses without it — so the
    test is red-capable, not a tautology.

Run: python tools/test_mirror_mod.py
"""
from __future__ import annotations

import lzma
import struct
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mania_render.hud import build_from_replay, judge_counts  # noqa: E402
from mania_render.osr import MOD_MIRROR, parse_osr  # noqa: E402
from mania_render.osu_file import parse_osu  # noqa: E402

FAILS: list[str] = []


def check(name: str, got, want) -> None:
    ok = got == want
    print(f"  {'PASS' if ok else 'FAIL'}  {name}: got {got!r} want {want!r}")
    if not ok:
        FAILS.append(name)


# ── fixtures ─────────────────────────────────────────────────────────────────
# 8 notes, 4K. Columns come from x: floor(x*4/512) -> 0,1,2,3 at x = 0/128/256/384.
NOTES = [(0, 1000), (128, 1200), (256, 1400), (384, 1600),
         (0, 1800), (384, 2000), (256, 2200), (128, 2400)]

OSU_TEXT = """osu file format v14

[General]
AudioFilename: audio.mp3
Mode: 3

[Metadata]
Title:Mirror Fixture
Version:4K

[Difficulty]
CircleSize:4
OD:8

[TimingPoints]
0,500,4,2,0,60,1,0

[HitObjects]
""" + "\n".join(f"{x},192,{t},1,0,0:0:0:0:" for x, t in NOTES) + "\n"


def build_osr(mods: int, mirrored_play: bool = True) -> bytes:
    """A minimal mania .osr replaying OSU_TEXT.

    `mirrored_play` decides which columns the presses are recorded in; `mods` is what the
    header claims. They are independent on purpose: the whole bug is that the header was
    ignored, so the test has to be able to build both pairings.
    """
    frames = []
    events = sorted((t, (3 - (x * 4 // 512)) if mirrored_play else (x * 4 // 512))
                    for x, t in NOTES)
    t = 0
    for time_ms, col in events:
        down = 1 << col
        frames.append(f"{time_ms - t}|{down}|0|0")
        t = time_ms
        frames.append(f"40|0|0|0")          # release 40 ms later
        t += 40
    blob = lzma.compress(",".join(frames).encode(), format=lzma.FORMAT_ALONE)
    out = bytearray()
    out += bytes([3])                        # ruleset: mania
    out += struct.pack("<i", 20240101)       # version
    for s in ("0" * 32, "Tester", "0" * 32):  # beatmap md5, player, replay md5
        b = s.encode()
        out += bytes([0x0B]) + _uleb(len(b)) + b
    out += struct.pack("<6h", 0, 0, 0, 0, 0, 0)   # counts
    out += struct.pack("<i", 100000)              # score
    out += struct.pack("<h", len(NOTES))          # max combo
    out += bytes([1])                             # perfect
    out += struct.pack("<i", mods)                # mods
    out += bytes([0x00])                          # life (empty string)
    out += struct.pack("<q", 0)                   # timestamp
    out += struct.pack("<i", len(blob)) + blob
    return bytes(out)


def _uleb(n: int) -> bytes:
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        out.append(b | (0x80 if n else 0))
        if not n:
            return bytes(out)


def judged(mods: int, apply_mirror: bool, mirrored_play: bool = True) -> dict:
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "r.osr"
        p.write_bytes(build_osr(mods, mirrored_play))
        head, replay = parse_osr(p)
    bm = parse_osu(OSU_TEXT)
    if apply_mirror:
        bm.apply_mirror()
    ev = build_from_replay(bm, replay)
    return judge_counts(bm, ev, od=8.0)


def main() -> int:
    print("mods field / mirror flag")
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "m.osr"
        p.write_bytes(build_osr(MOD_MIRROR))
        head, _ = parse_osr(p)
    check("mods read back", head.mods, MOD_MIRROR)
    check("mirror decoded", head.mirror, True)
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "n.osr"
        p.write_bytes(build_osr(0))
        head0, _ = parse_osr(p)
    check("mirror clear when mods=0", head0.mirror, False)

    print("apply_mirror is the game's transform")
    bm = parse_osu(OSU_TEXT)
    before = [h.column for h in bm.hit_objects]
    bm.apply_mirror()
    check("columns flipped (keys=4)", [h.column for h in bm.hit_objects],
          [3 - c for c in before])
    bm.apply_mirror()
    check("flip is its own inverse", [h.column for h in bm.hit_objects], before)

    print("end-to-end judgement through hud.build_from_replay")
    mirrored_fixed = judged(MOD_MIRROR, apply_mirror=True)
    mirrored_broken = judged(MOD_MIRROR, apply_mirror=False)
    check("mirrored replay WITH the flip: every note MAX",
          mirrored_fixed, {"max": len(NOTES), "300": 0, "200": 0, "100": 0, "50": 0, "miss": 0})
    check("mirrored replay WITHOUT the flip: not all MAX (red-capable)",
          mirrored_fixed != mirrored_broken, True)
    print(f"        unflipped counts = {mirrored_broken}")

    plain = judged(0, apply_mirror=False, mirrored_play=False)
    check("unmirrored replay is untouched by the fix",
          plain, {"max": len(NOTES), "300": 0, "200": 0, "100": 0, "50": 0, "miss": 0})

    print()
    if FAILS:
        print(f"FAILED ({len(FAILS)}): " + ", ".join(FAILS))
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
