"""Why does a dense pure-rice replay mismatch?

Dumps the press/note pairing for the worst case so the failure has a shape
rather than a guess: offsets, how many notes went unmatched, and where the
matched offsets sit relative to the windows.
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mania_render import judge  # noqa: E402
from mania_render.osr import parse_osr  # noqa: E402
from mania_render.osu_file import parse_osu  # noqa: E402

osr_name = sys.argv[1] if len(sys.argv) > 1 else None

OSR_DIR = ROOT / "cache" / "osr"
OSU_DIR = ROOT / "cache" / "osu"


def main() -> int:
    target = None
    for p in sorted(OSR_DIR.glob("*.osr")):
        if osr_name and osr_name not in p.name:
            continue
        head, replay = parse_osr(p)
        if sum(head.counts.values()) == 5273:
            target = (p, head, replay)
            break
    if target is None:
        print("no matching replay")
        return 1
    p, head, replay = target
    bm = parse_osu((OSU_DIR / "4550525.osu").read_text(encoding="utf-8-sig", errors="replace"))
    w = judge.mania_hit_windows(bm.od)
    print(f"{p.name}\n  OD={bm.od} windows={w}")
    print(f"  game says: {head.counts}")

    js = judge.judge_replay(bm, replay, od=bm.od)
    mine = judge.canonical_counts(judge.score_counts([j.result for j in js]))
    print(f"  engine   : {mine}")

    heads = [j for j in js if j.kind == "head"]
    pushed = [j for j in heads if j.by_press]
    auto = [j for j in heads if not j.by_press]
    print(f"\n  head judgements : {len(heads)}")
    print(f"    by press      : {len(pushed)}")
    print(f"    auto-missed   : {len(auto)}   (game misses: {head.count_miss})")

    # Distribution of |offset| for press-judged heads.
    buckets = Counter()
    for j in pushed:
        a = abs(j.offset)
        for name in judge.HIT_RESULTS:
            if a <= w[name]:
                buckets[name] += 1
                break
        else:
            buckets["beyond"] += 1
    print(f"\n  |offset| buckets for press-judged heads: {dict(buckets)}")
    print(f"    within perfect ({w['perfect']}): {sum(1 for j in pushed if abs(j.offset) <= w['perfect'])}")
    print(f"    within great   ({w['great']}): {sum(1 for j in pushed if abs(j.offset) <= w['great'])}")
    print(f"    within meh     ({w['meh']}): {sum(1 for j in pushed if abs(j.offset) <= w['meh'])}")
    offs = sorted(j.offset for j in pushed)
    if offs:
        print(f"    offset median  : {offs[len(offs)//2]:.1f}")
        print(f"    offset mean    : {sum(offs)/len(offs):.2f}")

    # How many presses were never used at all?
    used = len(pushed)
    print(f"\n  presses in replay: {len(replay.presses)}  (used {used}, wasted {len(replay.presses)-used})")

    # Note spacing: how dense is this map?
    col0 = sorted(o.start_time for o in bm.hit_objects if o.column == 0)
    gaps = [b - a for a, b in zip(col0, col0[1:])]
    gaps.sort()
    if gaps:
        print(f"\n  column 0 note gap: min={gaps[0]} median={gaps[len(gaps)//2]} "
              f"p10={gaps[len(gaps)//10]} p90={gaps[9*len(gaps)//10]}")
    print(f"  notes closer than the meh window: "
          f"{sum(1 for g in gaps if g < w['meh'])}")

    # Sample a dense stretch: show note times vs matched press offsets.
    print("\n  sample of column 0, first 40 objects near a dense patch:")
    dense_at = next((i for i, g in enumerate(gaps) if g < 60), 0)
    lo = max(0, dense_at - 5)
    objs = sorted([o for o in bm.hit_objects if o.column == 0], key=lambda o: o.start_time)
    press_times = sorted(pp.time_ms for pp in replay.presses if pp.column == 0)
    import bisect
    for o in objs[lo:lo + 40]:
        i = bisect.bisect_left(press_times, o.start_time)
        near = press_times[max(0, i - 1):i + 1]
        print(f"    note@{o.start_time:7d}  nearest presses {near}  ->offsets "
              f"{[t - o.start_time for t in near]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
