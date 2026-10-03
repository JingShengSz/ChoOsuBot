"""Does the .osu file we hold actually match the one the play was made on?

The header stores the beatmap MD5 of the file the game loaded.  If the cached
.osu is a DIFFERENT revision (the map was updated after the play, which is
common), the note times have moved and no matcher can reproduce the score — the
input data is simply wrong.  This correlates "MD5 matches" against "accuracy
matches", which distinguishes an algorithm bug from a stale-beatmap problem.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mania_render import judge  # noqa: E402
from mania_render.osr import parse_osr  # noqa: E402
from mania_render.osu_file import parse_osu  # noqa: E402

OSU = ROOT / "cache" / "osu"
OSR = ROOT / "cache" / "osr"


def main() -> int:
    maps = {}
    for p in OSU.glob("*.osu"):
        bm = parse_osu(p.read_text(encoding="utf-8-sig", errors="replace"))
        maps[p.stem] = (bm, sum(2 if h.is_hold else 1 for h in bm.hit_objects),
                        hashlib.md5(p.read_bytes()).hexdigest())

    print(f"{'replay':30} {'map':9} {'md5==':6} {'dACC':>9}")
    both = []
    for p in sorted(OSR.glob("*.osr")):
        try:
            head, replay = parse_osr(p)
        except Exception:
            continue
        total = sum(head.counts.values())
        cands = [(k, v) for k, v in maps.items() if v[1] == total]
        if len(cands) != 1 or not replay.presses:
            continue
        bid, (bm, _n, md5) = cands[0]
        same_md5 = md5 == head.beatmap_md5
        mine = judge.canonical_counts(
            judge.score_counts([j.result for j in judge.judge_replay(bm, replay, od=bm.od)]))
        d = judge.accuracy_percent(mine) - judge.accuracy_percent(head.counts)
        exact = judge.canonical_counts(mine) == judge.canonical_counts(head.counts)
        both.append((same_md5, exact, abs(d)))
        print(f"{p.name[:30]:30} {bid:9} {str(same_md5):6} {d:+9.4f}  {'EXACT' if exact else ''}")

    print()
    yes = [b for b in both if b[0]]
    no = [b for b in both if not b[0]]
    print(f"MD5 matches    : {len(yes):2d}   exact counts: {sum(1 for b in yes if b[1])}   "
          f"worst |dACC|: {max((b[2] for b in yes), default=0):.4f}")
    print(f"MD5 differs    : {len(no):2d}   exact counts: {sum(1 for b in no if b[1])}   "
          f"worst |dACC|: {max((b[2] for b in no), default=0):.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
