"""Is the CHART drifting against the replay, or is the matcher wrong?

If the note times and the press times disagree by a slowly varying amount, the
cached .osu is a different revision of the chart than the one the play was made
on, and no matcher can reproduce the score from it.  If instead the offsets are
flat but the assignment is wrong, it is a matcher bug.

Bins the map by time and reports, per bin, the median press-to-nearest-note
offset.  A revision shows as a trend or as jumps between bins; a matcher bug
shows as flat-but-large.
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
BINS = 12


def report(label: str, bm, replay) -> None:
    notes = sorted(o.start_time for o in bm.hit_objects)
    if not notes:
        return
    presses_by_col = {}
    for p in replay.presses:
        presses_by_col.setdefault(p.column, []).append(p.time_ms)
    for c in presses_by_col:
        presses_by_col[c].sort()
    span = notes[-1] - notes[0]
    buckets = [[] for _ in range(BINS)]
    for o in bm.hit_objects:
        arr = presses_by_col.get(o.column, [])
        if not arr:
            continue
        i = bisect.bisect_left(arr, o.start_time)
        cands = arr[max(0, i - 2):i + 2]
        if not cands:
            continue
        off = min(cands, key=lambda t: abs(t - o.start_time)) - o.start_time
        b = min(BINS - 1, int((o.start_time - notes[0]) / max(1, span) * BINS))
        buckets[b].append(off)
    med = []
    for b in buckets:
        s = sorted(b)
        med.append(None if not s else s[len(s) // 2])
    print(f"{label}")
    print("   median press-minus-note offset per 1/12 of the map:")
    print("   " + "  ".join("  --  " if m is None else f"{m:+5.0f}" for m in med))
    first = [m for m in med if m is not None]
    if first:
        print(f"   spread = {max(first) - min(first):.0f} ms   "
              f"(flat ~0 = same chart; tens/hundreds = chart drifted)")


def main() -> int:
    targets = sys.argv[1:] or ["4550525", "4213143", "750518"]
    by_total = {}
    for p in OSU.glob("*.osu"):
        bm = parse_osu(p.read_text(encoding="utf-8-sig", errors="replace"))
        by_total.setdefault(sum(2 if h.is_hold else 1 for h in bm.hit_objects), []).append((p.stem, bm))

    for bid in targets:
        bm = parse_osu((OSU / f"{bid}.osu").read_text(encoding="utf-8-sig", errors="replace"))
        total = sum(2 if h.is_hold else 1 for h in bm.hit_objects)
        found = False
        for p in sorted(OSR.glob("*.osr")):
            head, replay = parse_osr(p)
            if sum(head.counts.values()) != total or not replay.presses:
                continue
            report(f"{bid}  <-  {p.name[:46]}", bm, replay)
            found = True
            break
        if not found:
            print(f"{bid}: no replay matched")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
