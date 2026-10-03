"""The object model and the header anchor.

    python tools/test_object_model.py

Two rules that together make the rendered accuracy the GAME's accuracy rather
than an approximation of it, both measured against replays whose headers record
what osu! itself decided:

1. Which client wrote the replay decides how many judgements a hold note is.
   osu!stable (a YYYYMMDD header version) counts it ONCE; osu!lazer (>= 30000000)
   counts it TWICE, because its HoldNote nests a HeadNote and a TailNote and each
   is its own ManiaJudgement.  Measured over the cached replays there is no
   counterexample in either direction.

2. The header's counts are authoritative, so the counter is pinned to them.
   lazer reads exactly these when it decodes a legacy score, and the osu! website
   computes accuracy as a pure function of them.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mania_render import judge                      # noqa: E402
from mania_render.hud import build_from_replay, judge_counts   # noqa: E402
from mania_render.osr import parse_osr              # noqa: E402
from mania_render.osu_file import parse_osu         # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok   {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name}" + (f"   {detail}" if detail else ""))


OSU = ROOT / "cache" / "osu"
OSR = ROOT / "cache" / "osr"


def load(osu_name, osr_name):
    bm = parse_osu((OSU / osu_name).read_text(encoding="utf-8-sig", errors="replace"))
    head, replay = parse_osr(OSR / osr_name)
    if head.mirror:
        bm.apply_mirror()
    return bm, head, replay


def main() -> int:
    print("=" * 68)
    print("1. judgements_per_hold follows the replay's writer")
    print("=" * 68)

    class R:
        def __init__(self, classic):
            self.classic = classic

    check("stable replay (legacy version) -> one judgement per hold",
          judge.judgements_per_hold(R(True)) == 1)
    check("lazer replay -> two judgements per hold",
          judge.judgements_per_hold(R(False)) == 2)

    # The header total must then equal N + per_hold*M on a real chart pair.
    bm, head, replay = load("5366777.osu", "01a45e0c040247dc9eef4fedd138e099_replay.osr")
    n = sum(1 for h in bm.hit_objects if not h.is_hold)
    m = sum(1 for h in bm.hit_objects if h.is_hold)
    total = sum(head.counts.values())
    check(f"stable LN-only chart: N={n} M={m} header={total} == N+M",
          n + m == total, f"{n}+{m}={n+m} vs {total}")
    check("   ...and NOT N+2M", n + 2 * m != total)

    js = judge.replay_judgements(bm, replay, od=bm.od, counts=head.counts)
    check("one judgement per hit object", len(js) == total,
          f"{len(js)} vs {total}")

    print()
    print("=" * 68)
    print("2. a stable hold is judged by its RELEASE, not its head")
    print("=" * 68)

    # The release-based result must differ from the head-based one on this chart
    # (otherwise the rule is not actually doing anything).
    raw = judge.replay_judgements(bm, replay, od=bm.od, reconcile_counts=False)
    all_j = judge.judge_replay(bm, replay, od=bm.od)
    heads = judge.canonical_counts(judge.score_counts(
        [j.result for j in all_j if j.kind == "head"]))
    model = judge.canonical_counts(judge.score_counts([j.result for j in raw]))
    check("release-based counts differ from head-based counts",
          heads != model,
          f"{heads} vs {model}")

    # The game's own counts are the tie-breaker, and the release model is closer.
    truth = head.counts
    err_head = sum(abs(heads[k] - truth[k]) for k in judge.HIT_RESULTS) // 2
    err_rel = sum(abs(model[k] - truth[k]) for k in judge.HIT_RESULTS) // 2
    check(f"release model is closer to the game than the head model "
          f"({err_rel} vs {err_head} wrong)",
          err_rel < err_head)

    print()
    print("=" * 68)
    print("3. reconcile pins the totals and touches only the boundary")
    print("=" * 68)

    mk = lambda result, offset, by_press=True: judge.Judgement(
        time=0, obj_start=0, column=0, kind="head", result=result,
        offset=offset, by_press=by_press)

    lst = [mk("perfect", 1), mk("perfect", 2), mk("perfect", 30), mk("great", 35)]
    out, changed = judge.reconcile(lst, {"perfect": 2, "great": 2, "good": 0,
                                         "ok": 0, "meh": 0, "miss": 0})
    counts = judge.canonical_counts(judge.score_counts([j.result for j in out]))
    check("counts now equal the target",
          counts == {"perfect": 2, "great": 2, "good": 0, "ok": 0, "meh": 0, "miss": 0},
          str(counts))
    check("exactly one judgement changed", changed == 1, str(changed))
    check("the WORST perfect was the one demoted (offset 30, not offset 1)",
          [j.result for j in out] == ["perfect", "perfect", "great", "great"],
          str([j.result for j in out]))

    same = [mk("perfect", 1), mk("great", 2)]
    _o, ch = judge.reconcile(same, {"perfect": 1, "great": 1, "good": 0,
                                    "ok": 0, "meh": 0, "miss": 0})
    check("a no-op when the counts already agree", ch == 0, str(ch))

    _o, ch = judge.reconcile(same, {"perfect": 5, "great": 0, "good": 0,
                                    "ok": 0, "meh": 0, "miss": 0})
    check("refuses when the total does not match (model mismatch)", ch == 0)

    print()
    print("=" * 68)
    print("4. end to end: the HUD's accuracy is the game's")
    print("=" * 68)

    for osu_name, osr_name, label in (
        ("4659456.osu", "0dc096f1a2964265907d926fec494438_short_nomods.osr",
         "Freak Like Me (stable, 1363 judgements)"),
        ("5510352.osu", "97cdd460ec724524bb50accd06b2ba6c_long_nomods.osr",
         "lazer, 10300 judgements"),
        ("5366777.osu", "01a45e0c040247dc9eef4fedd138e099_replay.osr",
         "LN-only stable chart, 4359 judgements"),
    ):
        if not (OSU / osu_name).exists() or not (OSR / osr_name).exists():
            continue
        bm, head, replay = load(osu_name, osr_name)
        # Exactly what the renderer does.
        ev = build_from_replay(bm, replay)
        counts = judge_counts(bm, ev, now_ms=10 ** 9)
        acc = judge.accuracy_percent(counts)
        acc_stable = judge.accuracy_percent_stable(counts)
        want = judge.accuracy_percent(head.counts)
        want_stable = judge.accuracy_percent_stable(head.counts)
        check(f"{label}: lazer acc == game", abs(acc - want) < 1e-9,
              f"{acc:.4f} vs {want:.4f}")
        check(f"{label}: stable acc == game's counts",
              abs(acc_stable - want_stable) < 1e-9,
              f"{acc_stable:.4f} vs {want_stable:.4f}")

    print()
    print("=" * 68)
    print(f"PASSED: {PASS}    FAILED: {FAIL}")
    print("=" * 68)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
