"""Checks for the lazer-faithful mania judgement engine.

    python tools/test_judge_lazer.py

The first section is the important one: it re-creates the assertions osu!lazer
itself makes, so if these pass the engine agrees with the game by construction
rather than by opinion.

    osu.Game.Tests/Beatmaps/Formats/LegacyScoreDecoderTest.cs:392
        a mania score with 198 perfects, 1 great and 1 miss
        -> Accuracy == (198 * 305 + 300) / (200 * 305)

    osu.Game.Rulesets.Mania.Tests/TestSceneManiaModDoubleTime.cs:31
        an all-GREAT play
        -> Accuracy ≈ 0.9836          (= 300 / 305, i.e. Perfect is worth 305)
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mania_render import judge  # noqa: E402
from mania_render.models import HitObject, OsuBeatmap, ReplayData, ReplayPress  # noqa: E402

PASSED = 0
FAILED: list[str] = []


def check(label, condition, detail=""):
    global PASSED
    if condition:
        PASSED += 1
        print(f"  ok   {label}")
    else:
        FAILED.append(f"{label} {detail}")
        print(f"  FAIL {label} {detail}")


def near(a, b, eps=1e-9):
    return abs(a - b) <= eps


def note(col, start, end=None, hold=False):
    return HitObject(flags=0, start_time=start, end_time=end if end is not None else start,
                     column=col, is_hold=hold)


def repl(pairs):
    """pairs: [(col, press_ms, release_ms | None)]"""
    r = ReplayData()
    for col, down, up in pairs:
        r.presses.append(ReplayPress(time_ms=down, column=col))
        if up is not None:
            r.releases.append(ReplayPress(time_ms=up, column=col))
    return r


def main() -> int:
    # ------------------------------------------------------------------
    print("== the value table (ManiaScoreProcessor.GetBaseScoreForResult)")
    check("perfect is worth 305, not 300", judge.BASE_SCORE["perfect"] == 305)
    check("great is 300", judge.BASE_SCORE["great"] == 300)
    check("good/ok/meh/miss", [judge.BASE_SCORE[k] for k in ("good", "ok", "meh", "miss")] == [200, 100, 50, 0])
    check("the maximum per judgement is 305", judge.MAX_SCORE == 305)

    print("\n== osu!lazer's own assertions")
    # LegacyScoreDecoderTest: 198 perfects + 1 great + 1 miss out of 200.
    counts = {"perfect": 198, "great": 1, "good": 0, "ok": 0, "meh": 0, "miss": 1}
    expected = 100.0 * (198 * 305 + 300) / (200 * 305)
    got = judge.accuracy_percent(counts)
    check("198P/1G/1M matches LegacyScoreDecoderTest", near(got, expected, 1e-9),
          f"{got!r} vs {expected!r}")
    check("  …and that is 99.4918%", near(round(got, 4), 99.4918, 1e-4), round(got, 4))

    # TestSceneManiaModDoubleTime: an all-GREAT play is 0.9836, not 1.
    all_great = judge.accuracy_percent({"perfect": 0, "great": 1000, "good": 0, "ok": 0, "meh": 0, "miss": 0})
    check("all-GREAT is 98.36%, not 100%", near(round(all_great / 100, 4), 0.9836, 1e-4),
          round(all_great / 100, 6))
    check("all-PERFECT is exactly 100%",
          judge.accuracy_percent({"perfect": 999, "great": 0, "good": 0, "ok": 0, "meh": 0, "miss": 0}) == 100.0)
    check("an empty score is 100% (ScoreProcessor returns 1 when there is nothing)",
          judge.accuracy_percent({"perfect": 0, "great": 0, "good": 0, "ok": 0, "meh": 0, "miss": 0}) == 100.0)
    check("all-MISS is 0%",
          judge.accuracy_percent({"perfect": 0, "great": 0, "good": 0, "ok": 0, "meh": 0, "miss": 42}) == 0.0)

    # ------------------------------------------------------------------
    print("\n== hit windows (ManiaHitWindows at OD8)")
    w = judge.mania_hit_windows(8.0)
    check("perfect 16.5", w["perfect"] == 16.5, w["perfect"])
    check("great 40.5", w["great"] == 40.5, w["great"])
    check("good 73.5", w["good"] == 73.5, w["good"])
    check("ok 103.5", w["ok"] == 103.5, w["ok"])
    check("meh 127.5", w["meh"] == 127.5, w["meh"])
    check("miss 164.5", w["miss"] == 164.5, w["miss"])
    check("OD0 widens", judge.mania_hit_windows(0.0)["perfect"] == 22.5,
          judge.mania_hit_windows(0.0)["perfect"])
    check("OD10 narrows", judge.mania_hit_windows(10.0)["perfect"] == 13.5,
          judge.mania_hit_windows(10.0)["perfect"])

    print("\n== ResultFor's None (the press that consumes nothing)")
    check("inside perfect", judge.result_for_offset(0.0, w) == "perfect")
    check("at the perfect edge", judge.result_for_offset(16.5, w) == "perfect")
    check("just past perfect", judge.result_for_offset(16.6, w) == "great")
    check("at the meh edge", judge.result_for_offset(127.5, w) == "meh")
    check("just past meh is a MISS (Miss is an allowed result)",
          judge.result_for_offset(130.0, w) == "miss")
    check("past the miss window is None, not miss",
          judge.result_for_offset(200.0, w) is None, judge.result_for_offset(200.0, w))
    check("negative offsets use |offset|", judge.result_for_offset(-130.0, w) == "miss")

    print("\n== auto-miss timing uses the MEH window")
    check("a plain note misses at start + meh", judge.auto_miss_time(1000, w) == 1127.5,
          judge.auto_miss_time(1000, w))

    # ------------------------------------------------------------------
    print("\n== a hold note is TWO judgements")
    bm = OsuBeatmap(od=8.0)
    bm.hit_objects = [note(0, 1000, 2000, hold=True)]
    js = judge.judge_replay(bm, repl([(0, 1000, 2000)]), od=8.0)
    check("head + tail", len(js) == 2, [(j.kind, j.result) for j in js])
    check("both perfect", all(j.result == "perfect" for j in js), [j.result for j in js])
    check("kinds are head then tail", [j.kind for j in js] == ["head", "tail"],
          [j.kind for j in js])
    check("one LN gives exactly one accuracy judgement pair, so 100%",
          judge.accuracy_percent(judge.score_counts([j.result for j in js])) == 100.0)

    print("\n== releasing early costs the tail only")
    # Held 1000..1900 for a tail at 2000 -> offset -100/1.5 = -66.67 -> great.
    js = judge.judge_replay(bm, repl([(0, 1000, 1900)]), od=8.0)
    got = {j.kind: j.result for j in js}
    check("the head is still perfect", got["head"] == "perfect", got)
    check("the tail is judged from the release (-66.7/1 -> good)", got["tail"] == "good", got)
    # Released 300 late: (2300-2000)/1.5 = 200 > miss window -> miss.
    js = judge.judge_replay(bm, repl([(0, 1000, 2300)]), od=8.0)
    got = {j.kind: j.result for j in js}
    check("a very late release misses the tail", got["tail"] == "miss", got)

    print("\n== never holding misses BOTH")
    js = judge.judge_replay(bm, repl([(0, 5000, None)]), od=8.0)
    check("head and tail both miss", [j.result for j in js] == ["miss", "miss"],
          [(j.kind, j.result) for j in js])
    check("so the LN is 0%", judge.accuracy_percent(judge.score_counts([j.result for j in js])) == 0.0)

    print("\n== the head missed but the key held: the tail is capped at Meh")
    # Press far too early for the head (outside the miss window), then hold.
    js = judge.judge_replay(bm, repl([(0, 860, 2000)]), od=8.0)
    tails = [j for j in js if j.kind == "tail"]
    check("head is a miss", any(j.kind == "head" and j.result == "miss" for j in js),
          [(j.kind, j.result) for j in js])
    check("tail capped to meh by GetCappedResult",
          tails and tails[0].result == "meh", [j.result for j in tails])

    # ------------------------------------------------------------------
    print("\n== note lock (OrderedHitPolicy + HitObjectContainer.Compare)")
    bm2 = OsuBeatmap(od=8.0)
    bm2.hit_objects = [note(0, 1000), note(0, 1100)]
    # One press at 1100: it cannot hit the 1000 note (the 1100 note has started),
    # so it hits the 1100 note and force-misses the 1000 note.
    js = judge.judge_replay(bm2, repl([(0, 1100, None)]), od=8.0)
    by = {j.obj_start: j.result for j in js}
    check("the earlier note is locked and missed", by[1000] == "miss", by)
    check("the later note takes the press as perfect", by[1100] == "perfect", by)

    # A press BEFORE the next note starts may hit the current one.
    js = judge.judge_replay(bm2, repl([(0, 1050, None)]), od=8.0)
    by = {j.obj_start: j.result for j in js}
    check("a press before the next note hits the current one (+50 -> good)", by[1000] == "good", by)
    check("and the later note then misses", by[1100] == "miss", by)

    # An early press aims at the upcoming note when the current one is out of range.
    bm3 = OsuBeatmap(od=8.0)
    bm3.hit_objects = [note(0, 1000), note(0, 3000)]
    js = judge.judge_replay(bm3, repl([(0, 2960, None)]), od=8.0)
    by = {j.obj_start: j.result for j in js}
    check("an early press takes the upcoming note (-40 -> great)", by[3000] == "great", by)
    check("and the stale note is a miss", by[1000] == "miss", by)

    print("\n== presses are consumed, not reused")
    bm4 = OsuBeatmap(od=8.0)
    bm4.hit_objects = [note(0, 1000), note(0, 3000)]
    js = judge.judge_replay(bm4, repl([(0, 1000, None)]), od=8.0)
    by = {j.obj_start: j.result for j in js}
    check("one press judges one note", by[1000] == "perfect" and by[3000] == "miss", by)

    print("\n" + "=" * 60)
    print(f"PASSED: {PASSED}    FAILED: {len(FAILED)}")
    for f in FAILED:
        print("  - " + f)
    print("=" * 60)
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
