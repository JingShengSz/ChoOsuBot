"""Does the mismatch correlate with WHICH GAME made the play?

The .osr header counts were produced by the game that recorded the play.  A
version below LegacyScoreEncoder.FIRST_LAZER_VERSION (30_000_000) is an
osu!stable score; anything above is osu!lazer.  If the mismatching replays are
all one kind, then the disagreement is between two engines' judgement — not a
bug in this one, which follows lazer.

Prints, per comparable replay: version, which game, whether the beatset OD makes
the classic and standard window sets differ, and the accuracy delta.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mania_render import judge  # noqa: E402
from mania_render.osr import parse_osr  # noqa: E402
from mania_render.osu_file import parse_osu  # noqa: E402

FIRST_LAZER_VERSION = 30_000_000
OSU = ROOT / "cache" / "osu"
OSR = ROOT / "cache" / "osr"


def main() -> int:
    maps = {}
    for p in OSU.glob("*.osu"):
        bm = parse_osu(p.read_text(encoding="utf-8-sig", errors="replace"))
        maps[p.stem] = (bm, sum(2 if h.is_hold else 1 for h in bm.hit_objects))

    print(f"{'replay':22} {'game':7} {'OD':>5} {'classic?':9} {'dACC':>9} result")
    rows = []
    for p in sorted(OSR.glob("*.osr")):
        try:
            head, replay = parse_osr(p)
        except Exception:
            continue
        total = sum(head.counts.values())
        cands = [(k, v) for k, v in maps.items() if v[1] == total]
        if len(cands) != 1 or not replay.presses:
            continue
        bid, (bm, _n) = cands[0]
        od = bm.od
        cw = judge.mania_hit_windows(od, classic=True)
        sw = judge.mania_hit_windows(od, classic=False)
        spread = max(abs(cw[k] - sw[k]) for k in judge.HIT_RESULTS)

        mine = judge.canonical_counts(
            judge.score_counts([j.result for j in judge.judge_replay(bm, replay, od=od)]))
        d = judge.accuracy_percent(mine) - judge.accuracy_percent(head.counts)
        exact = mine == judge.canonical_counts(head.counts)
        game = "stable" if head.version < FIRST_LAZER_VERSION else "lazer"
        rows.append((game, exact, abs(d), od, spread))
        print(f"{p.name[:22]:22} {game:7} {od:5.1f} {spread:6.1f}ms {d:+9.4f} "
              f"{'EXACT' if exact else ''}")

    print()
    for g in ("stable", "lazer"):
        sel = [r for r in rows if r[0] == g]
        if sel:
            print(f"{g:7}: {len(sel):2d} replays, {sum(1 for r in sel if r[1])} exact, "
                  f"worst |dACC| {max(r[2] for r in sel):.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
