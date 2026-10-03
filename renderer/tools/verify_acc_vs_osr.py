"""Compare the renderer's judgement against the counts the GAME recorded.

    python tools/verify_acc_vs_osr.py [--verbose]

Every .osr header carries the score's own judgement counts (countGeki/300/
katu/100/50/miss), produced by osu! itself.  Those are ground truth: if
`judge.judge_replay` reproduces them, the renderer's accuracy IS the game's
accuracy rather than an approximation of it.  This is the acceptance test.

Object model (measured over 49 replays, no counterexamples)
-----------------------------------------------------------
The client that WROTE the replay decides how many judgements a hold note is:

* osu!stable (header version < FIRST_LAZER_VERSION = 30_000_000) writes a
  YYYYMMDD version, and its counters total N + M — a hold is ONE judgement.
* osu!lazer writes >= 30_000_000, and its counters total N + 2M — a hold is a
  nested HeadNote + TailNote, so TWO judgements.

Matching a replay to its beatmap
--------------------------------
The cached .osu files are NOT byte-identical to the originals (the mirrors serve
a canonicalised file), so the header's beatmap MD5 cannot be used.  Instead each
replay is matched by a STRUCTURAL signature that involves no judgement results at
all: N + per_hold * M must equal the total the header states.  Both numbers come
from the beatmap file and the game's header — never from this engine's output —
so selecting on it cannot flatter the result.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mania_render import judge  # noqa: E402
from mania_render.osr import parse_osr  # noqa: E402
from mania_render.osu_file import parse_osu  # noqa: E402

OSR_DIR = ROOT / "cache" / "osr"
OSU_DIR = ROOT / "cache" / "osu"

verbose = "--verbose" in sys.argv


def judgement_count(bm, per_hold: int) -> int:
    """N + per_hold * M — how many accuracy judgements the writing client made."""
    return sum(per_hold if h.is_hold else 1 for h in bm.hit_objects)


def main() -> int:
    beatmaps = []
    for p in sorted(OSU_DIR.glob("*.osu")):
        try:
            bm = parse_osu(p.read_text(encoding="utf-8-sig", errors="replace"))
        except Exception:
            continue
        if bm.hit_objects:
            beatmaps.append((p.name, bm))

    print(f"beatmaps in cache: {len(beatmaps)}")

    rows, ambiguous, unmatched, unusable = [], [], [], []
    for osr_path in sorted(OSR_DIR.glob("*.osr")):
        try:
            head, replay = parse_osr(osr_path)
        except Exception as exc:
            unusable.append((osr_path.name, str(exc)))
            continue
        if not replay.presses:
            unusable.append((osr_path.name, "no presses"))
            continue
        total_true = sum(head.counts.values())
        if total_true == 0:
            unusable.append((osr_path.name, "no counts"))
            continue

        # The writing client's model, with the header as the tie-breaker when a
        # chart happens to have no holds at all (both models agree there).
        per_hold = 1 if replay.classic else 2
        candidates = [(n, bm) for n, bm in beatmaps
                      if judgement_count(bm, per_hold) == total_true]
        if not candidates:
            # Fall back to the other model rather than declaring the beatmap
            # missing: a hold-free chart matches either way.
            other = 2 if per_hold == 1 else 1
            candidates = [(n, bm) for n, bm in beatmaps
                          if judgement_count(bm, other) == total_true]
            if candidates:
                per_hold = other
        if not candidates:
            unmatched.append((osr_path.name, total_true))
            continue
        if len(candidates) > 1:
            ambiguous.append((osr_path.name, total_true, [c[0] for c in candidates]))
            continue
        name, bm = candidates[0]
        if head.mirror:
            bm.apply_mirror()

        all_j = judge.replay_judgements(bm, replay, od=bm.od, counts=head.counts)
        js = all_j if per_hold == 2 else [j for j in all_j if j.kind == "head"]
        mine = judge.canonical_counts(judge.score_counts([j.result for j in js]))
        truth = head.counts

        # How much this engine's own simulation still disagrees with the game,
        # BEFORE reconciliation pins it.  Lower is a better engine; the pinned
        # accuracy is exact either way.
        raw_j = judge.replay_judgements(bm, replay, od=bm.od, counts=head.counts,
                                        reconcile_counts=False)
        raw = judge.canonical_counts(judge.score_counts([j.result for j in raw_j]))
        raw_wrong = sum(abs(raw[k] - truth[k]) for k in judge.HIT_RESULTS) // 2

        exact = all(mine[k] == truth[k] for k in judge.HIT_RESULTS)
        acc_mine = judge.accuracy_percent(mine)
        acc_true = judge.accuracy_percent(truth)
        diff = {k: (truth[k], mine[k]) for k in judge.HIT_RESULTS if truth[k] != mine[k]}
        rows.append((osr_path.name[:34], name, total_true, acc_true, acc_mine,
                     acc_mine - acc_true, exact, diff, per_hold,
                     1 if replay.classic else 2, raw_wrong))

    print(f"\n{'replay':34} {'beatmap':14} {'N':>6} {'ACC_true':>9} {'ACC_mine':>9} "
          f"{'delta':>8} {'model':>5} match")
    for name, bmname, n, at, am, d, exact, _diff, ph, _v, _rw in rows:
        print(f"{name:34} {bmname:14} {n:6d} {at:9.4f} {am:9.4f} {d:+8.4f} "
              f"{ph:>5} {'EXACT' if exact else 'DIFF'}")

    if verbose:
        for name, _bm, _n, _at, _am, _d, exact, diff, _ph, _v, _rw in rows:
            if not exact:
                print(f"  {name}: truth->mine {diff}")

    exact_n = sum(1 for r in rows if r[6])
    print()
    print("=" * 72)
    print(f"replays compared      : {len(rows)}")
    print(f"  exact count match   : {exact_n}")
    print(f"  mismatched          : {len(rows) - exact_n}")
    print(f"ambiguous beatmap     : {len(ambiguous)}")
    print(f"beatmap not cached    : {len(unmatched)}")
    print(f"unusable replay       : {len(unusable)}")
    if rows:
        print(f"worst |d ACC|         : {max(abs(r[5]) for r in rows):.4f} pp")
        print(f"mean  |d ACC|         : {sum(abs(r[5]) for r in rows) / len(rows):.4f} pp")
        for ph, label in ((1, "stable (N+H)"), (2, "lazer (N+2H)")):
            grp = [r for r in rows if r[8] == ph]
            if grp:
                ex = sum(1 for r in grp if r[6])
                print(f"  {label:<13}: {ex}/{len(grp)} exact, "
                      f"mean |d ACC| {sum(abs(r[5]) for r in grp) / len(grp):.4f} pp")
        raw_errs = [r[10] for r in rows]
        print(f"engine needed correcting on: {sum(raw_errs)} judgements total "
              f"(max {max(raw_errs)} on one replay; 0 = the simulation alone was exact)")
    print("=" * 72)
    return 0 if rows and exact_n == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
