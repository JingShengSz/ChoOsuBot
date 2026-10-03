"""Bimodal or smooth? — a charter revision leaves a signature.

If a chart was re-snapped after the play, the note COUNT is unchanged but a
minority of notes moved by tens of ms.  Every per-bin MEDIAN then stays near
zero (the majority still line up) while a visible second cluster appears in the
offset histogram.  A player simply hitting early produces one smooth cluster.

Compares the failing map with two that reproduce exactly.
"""

from __future__ import annotations

import bisect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mania_render.osr import parse_osr  # noqa: E402
from mania_render.osu_file import parse_osu  # noqa: E402

OSU = ROOT / "cache" / "osu"
OSR = ROOT / "cache" / "osr"


def bucket(v: float) -> str:
    a = abs(v)
    for edge, name in ((5, "0-5"), (15, "5-15"), (25, "15-25"), (35, "25-35"),
                       (45, "35-45"), (55, "45-55"), (70, "55-70"), (90, "70-90"),
                       (120, "90-120")):
        if a <= edge:
            return name
    return ">120"


def report(bid: str) -> None:
    bm = parse_osu((OSU / f"{bid}.osu").read_text(encoding="utf-8-sig", errors="replace"))
    total = sum(2 if h.is_hold else 1 for h in bm.hit_objects)
    replay = head = None
    for p in sorted(OSR.glob("*.osr")):
        h, r = parse_osr(p)
        if sum(h.counts.values()) == total and r.presses:
            head, replay = h, r
            break
    if replay is None:
        print(f"{bid}: no replay")
        return
    bycol = {}
    for pr in replay.presses:
        bycol.setdefault(pr.column, []).append(pr.time_ms)
    for c in bycol:
        bycol[c].sort()

    counts = {}
    for o in bm.hit_objects:
        arr = bycol.get(o.column, [])
        if not arr:
            continue
        i = bisect.bisect_left(arr, o.start_time)
        cands = arr[max(0, i - 2):i + 2]
        if not cands:
            continue
        off = min(cands, key=lambda t: abs(t - o.start_time)) - o.start_time
        counts[bucket(off)] = counts.get(bucket(off), 0) + 1
    total_notes = sum(counts.values())
    print(f"{bid}  ({total_notes} notes, nearest-press offset histogram)")
    order = ["0-5", "5-15", "15-25", "25-35", "35-45", "45-55", "55-70", "70-90", "90-120", ">120"]
    for k in order:
        n = counts.get(k, 0)
        pct = 100.0 * n / total_notes if total_notes else 0
        bar = "#" * int(pct / 2)
        print(f"   {k:>7} {n:6d} {pct:5.1f}% {bar}")
    tight = sum(counts.get(k, 0) for k in ("0-5", "5-15", "15-25"))
    print(f"   within 25 ms: {100.0*tight/total_notes:.1f}%   "
          f"35-70 ms: {100.0*(counts.get('35-45',0)+counts.get('45-55',0)+counts.get('55-70',0))/total_notes:.1f}%")
    print()


def main() -> int:
    for bid in (sys.argv[1:] or ["4550525", "4213143", "3841899"]):
        report(bid)
    return 0


if __name__ == "__main__":
    sys.exit(main())
