"""Show exactly which press each note got, around notes the engine rates 'good'.

The engine rates ~1069 notes 'good' where the game rates 116.  Offsets are tiny
in aggregate (median +5 ms), so the presses exist and are close — they are just
being handed to the wrong note.  This prints the neighbourhood of a few such
notes so the mechanism is visible instead of guessed at.
"""

from __future__ import annotations

import bisect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mania_render import judge  # noqa: E402
from mania_render.osr import parse_osr  # noqa: E402
from mania_render.osu_file import parse_osu  # noqa: E402

OSR_DIR = ROOT / "cache" / "osr"
OSU_DIR = ROOT / "cache" / "osu"


def find_replay(total: int):
    for p in sorted(OSR_DIR.glob("*.osr")):
        head, replay = parse_osr(p)
        if sum(head.counts.values()) == total:
            return p, head, replay
    return None, None, None


def main() -> int:
    p, head, replay = find_replay(5273)
    if p is None:
        print("not found")
        return 1
    bm = parse_osu((OSU_DIR / "4550525.osu").read_text(encoding="utf-8-sig", errors="replace"))
    w = judge.mania_hit_windows(bm.od)
    print(f"{p.name[:40]}")
    print(f"OD={bm.od} windows={w}")
    print(f"game={head.counts}")
    js = judge.judge_replay(bm, replay, od=bm.od)
    print(f"mine={judge.canonical_counts(judge.score_counts([j.result for j in js]))}")

    # press times per column
    bycol = {}
    for pr in replay.presses:
        bycol.setdefault(pr.column, []).append(pr.time_ms)
    for c in bycol:
        bycol[c].sort()

    heads = [j for j in js if j.kind == "head"]
    goods = [j for j in heads if j.result == "good"]
    print(f"\nnotes I rate 'good': {len(goods)}")
    print("showing 12, with the column's notes and presses around each:\n")

    objs_by_col = {}
    for o in bm.hit_objects:
        objs_by_col.setdefault(o.column, []).append(o)
    for c in objs_by_col:
        objs_by_col[c].sort(key=lambda o: o.start_time)

    shown = 0
    for j in goods:
        if shown >= 12:
            break
        col = next(o.column for o in bm.hit_objects if o.start_time == j.obj_start)
        notes = [o.start_time for o in objs_by_col[col]]
        i = notes.index(j.obj_start)
        lo, hi = max(0, i - 3), min(len(notes), i + 4)
        prs = bycol.get(col, [])
        k = bisect.bisect_left(prs, j.obj_start)
        nearby = prs[max(0, k - 4):k + 4]
        print(f"  col{col} note@{j.obj_start} <- got offset {j.offset:+.1f} ({j.result})")
        print(f"      notes  {notes[lo:hi]}")
        print(f"      presses{nearby}")
        print(f"      offsets vs this note: "
              f"{[t - j.obj_start for t in nearby]}")
        shown += 1

    # How many 'good' notes had a press within the PERFECT window of them?
    close = 0
    for j in goods:
        col = next(o.column for o in bm.hit_objects if o.start_time == j.obj_start)
        prs = bycol.get(col, [])
        k = bisect.bisect_left(prs, j.obj_start)
        cand = prs[max(0, k - 2):k + 2]
        if any(abs(t - j.obj_start) <= w["perfect"] for t in cand):
            close += 1
    print(f"\n'good' notes that HAVE a press within the perfect window of them: {close} / {len(goods)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
