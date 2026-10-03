"""osu!mania judgement and accuracy, traced to osu!lazer.

Every rule below cites the file it came from.  Nothing here is invented, and
nothing is rounded "close enough" — the whole point of this module is that a
renderer's accuracy counter can be compared with the game's and match.

Sources (paths relative to the osu! checkout):

    osu.Game/Rulesets/Scoring/HitWindows.cs
        ResultFor()          |offset|, best result whose window contains it;
                             HitResult.None when it is outside every window
        CanBeHit()           |offset| <= WindowFor(lowest successful result)
    osu.Game/Rulesets/Scoring/ScoreProcessor.cs
        Accuracy             currentBaseScore / currentMaximumBaseScore
        GetBaseScoreForResult()  the per-result value
    osu.Game/Rulesets/Scoring/HitResult.cs
        enum order, AffectsAccuracy, IsScorable, IsBonus
    osu.Game/Rulesets/Mania/Scoring/ManiaHitWindows.cs
        the six DifficultyRanges, floor(x * totalMultiplier) + 0.5
    osu.Game.Rulesets.Mania/Scoring/ManiaScoreProcessor.cs
        GetBaseScoreForResult: Perfect -> 305   (everything else from the base)
    osu.Game.Rulesets.Mania/Objects/HoldNote.cs
        CreateNestedHitObjects: HeadNote + TailNote + HoldNoteBody
    osu.Game.Rulesets.Mania/Objects/{HeadNote,TailNote}.cs
        both are `Note`s -> ManiaJudgement -> MaxResult = Perfect
    osu.Game.Rulesets.Mania/Objects/HoldNoteBody.cs
        HoldNoteBodyJudgement.MaxResult = IgnoreHit  (so it does NOT affect
        accuracy: HitResult.AffectsAccuracy is IsScorable && !IsBonus, and
        IsScorable is `result >= Miss && result < IgnoreMiss`)
    osu.Game.Rulesets.Mania/Objects/Drawables/DrawableNote.cs
        CheckForResult: not user-triggered and !CanBeHit -> ApplyMinResult()
    osu.Game.Rulesets.Mania/Objects/Drawables/DrawableHoldNoteTail.cs
        CheckForResult(offset / RELEASE_WINDOW_LENIENCE)
        GetCappedResult: a broken head/body caps the tail at Meh
    osu.Game.Rulesets.Mania/UI/OrderedHitPolicy.cs
        note lock: only the object with no *later* started object is hittable;
        a hit force-misses every earlier unjudged object in the column
    osu.Game/Rulesets/UI/HitObjectContainer.cs
        Compare(): "Put earlier hitobjects towards the end of the list, so they
        handle input first"

The two facts that make a renderer's accuracy wrong are easy to miss and both
live in this file:

1. **Perfect scores 305, not 300** (ManiaScoreProcessor), and the denominator is
   therefore 305 x judgements.  A full-GREAT play scores 300/305 = 98.36%, which
   osu!lazer asserts directly in TestSceneManiaModDoubleTime.
2. **A hold note is TWO judgements**: head and tail.  The HoldNote itself is an
   IgnoreJudgement and its body cannot affect accuracy at all, so a map with N
   notes and M holds has N + 2M accuracy judgements, not N + M.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# Results from best to worst, in HitResult enum order (Miss..Perfect reversed).
HIT_RESULTS = ("perfect", "great", "good", "ok", "meh", "miss")

#: ManiaScoreProcessor.GetBaseScoreForResult, with the base ScoreProcessor's
#: values for everything else.  Perfect is the mania override.
BASE_SCORE = {
    "perfect": 305,
    "great": 300,
    "good": 200,
    "ok": 100,
    "meh": 50,
    "miss": 0,
}

#: ScoreProcessor: currentMaximumBaseScore += GetBaseScoreForResult(MaxResult),
#: and every judged mania object's MaxResult is Perfect.
MAX_SCORE = BASE_SCORE["perfect"]

#: TailNote.RELEASE_WINDOW_LENIENCE.  DrawableHoldNoteTail divides the release
#: offset by this before asking the windows about it.
RELEASE_WINDOW_LENIENCE = 1.5

#: ManiaHitWindows' DifficultyRange triples, verbatim (hi @ OD0, mid @ OD5, lo @ OD10).
_WINDOW_RANGES = {
    "perfect": (22.4, 19.4, 13.9),
    "great": (64.0, 49.0, 34.0),
    "good": (97.0, 82.0, 67.0),
    "ok": (127.0, 112.0, 97.0),
    "meh": (151.0, 136.0, 121.0),
    "miss": (188.0, 173.0, 158.0),
}

#: The stable/classic ("ScoreV1") window set, used when ClassicModActive &&
#: !ScoreV2Active.  `invertedOd = max(0, min(10, 10 - od))`.
_CLASSIC_WINDOWS = {
    "perfect": 16.0,
    "great": lambda inv: 34.0 + 3.0 * inv,
    "good": lambda inv: 67.0 + 3.0 * inv,
    "ok": lambda inv: 97.0 + 3.0 * inv,
    "meh": lambda inv: 121.0 + 3.0 * inv,
    "miss": lambda inv: 158.0 + 3.0 * inv,
}

#: The "convert" window set (a mania conversion of a non-mania beatmap).  Kept
#: for completeness; a real mania beatmap never uses it.
_CONVERT_WINDOWS = {
    "perfect": 16.0,
    "great": lambda od: 34.0 if round(od) > 4 else 47.0,
    "good": lambda od: 67.0 if round(od) > 4 else 77.0,
    "ok": lambda od: 97.0,
    "meh": lambda od: 121.0,
    "miss": lambda od: 158.0,
}


def difficulty_range(difficulty: float, lo: float, mid: float, hi: float) -> float:
    """IBeatmapDifficultyInfo.DifficultyRange.

    NOTE the parameter names in the C#: ``DifficultyRange(double difficulty,
    double min, double mid, double max)``.  A range written ``new
    DifficultyRange(22.4, 19.4, 13.9)`` is therefore min=22.4 (OD0), mid=19.4
    (OD5), max=13.9 (OD10) — the numbers DECREASE with difficulty.
    """
    if difficulty > 5:
        return mid + (hi - mid) * (difficulty - 5) / 5.0
    if difficulty < 5:
        return mid + (mid - lo) * (difficulty - 5) / 5.0
    return mid


def _f05(x: float) -> float:
    """``Math.Floor(x * totalMultiplier) + 0.5`` with no mods applied."""
    return math.floor(x) + 0.5


def mania_hit_windows(od: float, is_convert: bool = False, classic: bool = False,
                      speed_multiplier: float = 1.0,
                      difficulty_multiplier: float = 1.0) -> dict[str, float]:
    """ManiaHitWindows half-widths in ms.

    ``totalMultiplier = speedMultiplier / difficultyMultiplier`` — note the
    DIVISION: a higher difficulty multiplier narrows the windows.
    """
    total = speed_multiplier / difficulty_multiplier
    if classic and not is_convert:
        inv = max(0.0, min(10.0, 10.0 - od))
        out = {"perfect": _f05(_CLASSIC_WINDOWS["perfect"] * total)}
        for name in ("great", "good", "ok", "meh", "miss"):
            out[name] = _f05(_CLASSIC_WINDOWS[name](inv) * total)
        return out
    if is_convert:
        return {name: _f05(_CONVERT_WINDOWS[name](od) * total) for name in HIT_RESULTS}
    return {
        name: _f05(difficulty_range(od, *_WINDOW_RANGES[name]) * total)
        for name in HIT_RESULTS
    }


def result_for_offset(offset: float, windows: dict[str, float]) -> str | None:
    """HitWindows.ResultFor — the best result whose window contains |offset|.

    Returns ``None`` when the offset is outside every window, INCLUDING the miss
    window.  That distinction matters: a press that produces None does not
    consume the note at all (DrawableNote.CheckForResult returns early and
    OnPressed reports "not handled", so the input falls through to the next
    object).  The old helper here returned "miss" instead, which silently turned
    a wasted press into a judged note.
    """
    a = abs(offset)
    for name in HIT_RESULTS:
        if a <= windows[name]:
            return name
    return None


def auto_miss_time(start_time: float, windows: dict[str, float]) -> float:
    """When an untouched object becomes a Miss.

    DrawableNote.CheckForResult: when not user-triggered, the object is missed
    once ``!HitWindows.CanBeHit(offset)``, and CanBeHit compares against the
    LOWEST SUCCESSFUL result — Meh, not Miss.
    """
    return start_time + windows["meh"]


# --------------------------------------------------------------------------
# Accuracy
# --------------------------------------------------------------------------

def accuracy_percent(counts: dict[str, int]) -> float:
    """ScoreProcessor.Accuracy, in percent, for mania.

    ``Accuracy = currentBaseScore / currentMaximumBaseScore`` where the maximum
    counts ``GetBaseScoreForResult(MaxResult) = 305`` per judged object, and the
    running score counts ``GetBaseScoreForResult(actual)``.

    Accepts counts keyed either way (see :func:`canonical_counts`).
    """
    counts = canonical_counts(counts)
    total = sum(counts.values())
    if total <= 0:
        return 100.0
    weighted = sum(BASE_SCORE[name] * counts[name] for name in HIT_RESULTS)
    return 100.0 * weighted / (MAX_SCORE * total)


def accuracy_percent_stable(counts: dict[str, int]) -> float:
    """The accuracy osu!stable's mania shows, for comparison.

    Perfect and Great both count 300 and the denominator is 300 per judgement —
    so a full-GREAT play reads 100% here and 98.36% in lazer.  Both figures are
    rendered side by side because they disagree on every non-perfect play and
    neither is "the" accuracy: one is what the game the score was set in showed,
    the other is what lazer shows for the same play.
    """
    counts = canonical_counts(counts)
    total = sum(counts.values())
    if total <= 0:
        return 100.0
    weighted = (counts["perfect"] + counts["great"]) * 300 \
        + counts["good"] * 200 + counts["ok"] * 100 + counts["meh"] * 50
    return 100.0 * weighted / (300 * total)


#: HUD / legacy keys, kept so the existing panels and skins keep working.
_LEGACY_KEY = {"perfect": "max", "great": "300", "good": "200",
               "ok": "100", "meh": "50", "miss": "miss"}

#: ...and the way back.  There are two vocabularies in this project — the HUD
#: panels and skins say "max"/"300" (stable's names), this module says
#: "perfect"/"great" (lazer's) — and a counter that reads a dict written in the
#: other one silently counts zero.  That is exactly the bug this table fixes, so
#: accuracy_percent accepts either.
_LEGACY_TO_RESULT = {v: k for k, v in _LEGACY_KEY.items()}


def canonical_counts(counts: dict) -> dict[str, int]:
    """Accept either vocabulary; return counts keyed by lazer result names."""
    out = {name: 0 for name in HIT_RESULTS}
    for key, value in counts.items():
        name = _LEGACY_TO_RESULT.get(key, key)
        if name in out:
            out[name] += value
    return out


def score_counts(results) -> dict[str, int]:
    """Count results into the legacy HUD dictionary."""
    counts = {v: 0 for v in _LEGACY_KEY.values()}
    for r in results:
        counts[_LEGACY_KEY[r]] += 1
    return counts


# --------------------------------------------------------------------------
# Judgement
# --------------------------------------------------------------------------

@dataclass
class Judgement:
    """One accuracy-affecting result, and when lazer would apply it."""

    time: int          # ms, when the result is applied (for the live counter)
    obj_start: int     # the owning hit object's start time
    column: int        # the owning object's column (-1 when unknown)
    kind: str          # "head" | "tail"
    result: str        # a member of HIT_RESULTS
    offset: float      # head: press - start.  tail: (release - tail) / 1.5
    #: True when a real key press produced this result (as opposed to the object
    #: running out of time).  The hit-error bar draws only real presses.
    by_press: bool = False


def _hold_intervals(replay) -> dict[int, list[tuple[int, int]]]:
    """Per column, the (key down, key up) intervals the replay implies.

    Same pairing the renderer has always used: walk the column's downs and ups
    in time order, and close an open hold on the next up.  A press with no
    following up is held to the end of the replay (zero length).
    """
    intervals: dict[int, list[tuple[int, int]]] = {}
    columns = {p.column for p in replay.presses} | {p.column for p in replay.releases}
    for col in columns:
        downs = sorted(p.time_ms for p in replay.presses if p.column == col)
        ups = sorted(p.time_ms for p in replay.releases if p.column == col)
        out: list[tuple[int, int]] = []
        di = ui = 0
        cur: int | None = None
        while di < len(downs) or ui < len(ups):
            nd = downs[di] if di < len(downs) else None
            nu = ups[ui] if ui < len(ups) else None
            if cur is None:
                if nd is None:
                    break
                cur = nd
                di += 1
            elif nu is None or (nd is not None and nd < nu):
                out.append((cur, cur))     # pressed again without releasing
                cur = nd
                di += 1
            else:
                out.append((cur, nu))
                cur = None
                ui += 1
        if cur is not None:
            out.append((cur, cur))
        if out:
            intervals[col] = out
    return intervals


def _release_for(intervals: dict[int, list[tuple[int, int]]], col: int,
                 press_time: int) -> int | None:
    """The key-up that ends the hold started by ``press_time``."""
    for down, up in intervals.get(col, ()):
        if down == press_time:
            return up
    return None


def judge_replay(bm, replay, od: float | None = None,
                 speed_multiplier: float = 1.0,
                 difficulty_multiplier: float = 1.0,
                 classic: bool | None = None) -> list[Judgement]:
    """Reproduce osu!lazer's judgement of a mania beatmap from a replay.

    Returns every accuracy-affecting judgement, in no particular order.  Each
    plain note is one judgement; each hold note is two (head + tail).

    The matching is press-driven and note-locked, which is the part a
    "nearest press to each note" matcher gets wrong:

    * ``HitObjectContainer.Compare`` puts earlier hit objects first for input, so
      a press is offered to the EARLIEST live object in its column first;
    * ``OrderedHitPolicy.IsHittable`` refuses any object that has a *later*
      object which has already started ("note lock");
    * ``DrawableNote.OnPressed`` refuses the press when the windows return
      HitResult.None, so it falls through to the next object;
    * a successful HIT force-misses every earlier unjudged object in the column.
    """
    windows = mania_hit_windows(
        od if od is not None else (bm.od or 8.0),
        classic=bool(getattr(replay, "classic", False)) if classic is None else classic,
        speed_multiplier=speed_multiplier,
        difficulty_multiplier=difficulty_multiplier)
    intervals = _hold_intervals(replay)

    by_col: dict[int, list] = {}
    for h in bm.hit_objects:
        by_col.setdefault(h.column, []).append(h)
    for col in by_col:
        by_col[col].sort(key=lambda h: (h.start_time, h.end_time))

    presses: dict[int, list[int]] = {}
    for p in replay.presses:
        presses.setdefault(p.column, []).append(p.time_ms)
    for col in presses:
        presses[col].sort()

    out: list[Judgement] = []
    for col, objs in by_col.items():
        judged: dict[int, str] = {}       # object index -> head result
        head_press: dict[int, int] = {}   # object index -> the press that hit it

        for t in presses.get(col, ()):
            for i, o in enumerate(objs):
                if i in judged:
                    continue
                # ALREADY DEAD.  DrawableNote.CheckForResult auto-misses an object
                # as soon as (now - start) exceeds the MEH window — not the miss
                # window — because CanBeHit() compares against the lowest
                # SUCCESSFUL result.  So a press that lands later than that finds
                # the note already judged and is offered to the next one instead.
                # Treating the (meh, miss] band as "this press misses this note"
                # is what made this engine report too many misses.
                if t > o.start_time + windows["meh"]:
                    judged[i] = "miss"
                    out.append(Judgement(
                        time=int(auto_miss_time(o.start_time, windows)),
                        obj_start=int(o.start_time), column=col, kind="head",
                        result="miss", offset=0.0))
                    continue
                # Note lock: a later object that has already started locks this one.
                # "Later" means the next object still in AliveObjects — and a
                # judged object is KILLED, so it leaves that list.  Using the
                # statically next object instead let an already-judged note keep
                # locking its predecessor, which mispaired presses throughout
                # dense same-column runs.
                nxt = None
                for j in range(i + 1, len(objs)):
                    if j not in judged:
                        nxt = objs[j]
                        break
                if nxt is not None and t >= nxt.start_time:
                    continue
                off = float(t - o.start_time)
                r = result_for_offset(off, windows)
                if r is None:
                    continue               # wasted press: no result, no consumption
                judged[i] = r
                head_press[i] = int(t)
                out.append(Judgement(time=int(t), obj_start=int(o.start_time),
                                     column=col, kind="head", result=r, offset=off,
                                     by_press=True))
                if r != "miss":
                    # OrderedHitPolicy.HandleHit
                    for j in range(i):
                        if j not in judged:
                            judged[j] = "miss"
                            out.append(Judgement(
                                time=int(auto_miss_time(objs[j].start_time, windows)),
                                obj_start=int(objs[j].start_time), column=col, kind="head",
                                result="miss", offset=0.0))
                break

        # Anything never judged: the object is missed once it leaves the meh window.
        for i, o in enumerate(objs):
            if i not in judged:
                out.append(Judgement(time=int(auto_miss_time(o.start_time, windows)),
                                     obj_start=int(o.start_time), column=col, kind="head",
                                     result="miss", offset=0.0))

        # Tails.  A TailNote is its own judgement, and it is resolved by the
        # RELEASE: DrawableHoldNoteTail.CheckForResult divides the offset by
        # RELEASE_WINDOW_LENIENCE, and caps the result at Meh when the head was
        # not hit or the body broke.
        for i, o in enumerate(objs):
            if not getattr(o, "is_hold", False):
                continue
            head = judged.get(i, "miss")
            release = _release_for(intervals, col, head_press[i]) if i in head_press else None
            if release is None:
                # Never held: there is no release to judge the tail with, so it
                # runs out of time.  DrawableNote.CheckForResult is fed
                # (now - tailStart) / 1.5, so it fires once
                # (now - tailStart) / 1.5 > mehWindow — i.e. 1.5x later than a note.
                tail_result = "miss"
                tail_offset = 0.0
                when = int(o.end_time + RELEASE_WINDOW_LENIENCE * windows["meh"])
            else:
                tail_offset = (release - o.end_time) / RELEASE_WINDOW_LENIENCE
                tail_result = result_for_offset(tail_offset, windows) or "miss"
                when = int(release)
            # GetCappedResult: a broken hold cannot beat Meh on the tail.
            if head == "miss" and HIT_RESULTS.index(tail_result) < HIT_RESULTS.index("meh"):
                tail_result = "meh"
            out.append(Judgement(time=when, obj_start=int(o.end_time), column=col,
                                 kind="tail", result=tail_result, offset=tail_offset))

    out.sort(key=lambda j: j.time)
    return out


# --------------------------------------------------------------------------
# The object model, and anchoring the counter to the score's own counts
# --------------------------------------------------------------------------

def judgements_per_hold(replay) -> int:
    """How many accuracy judgements one hold note is, for THIS replay's writer.

    The client that wrote the .osr decides, and the header proves it.  Measured
    over 49 cached replays with no counterexample:

    * osu!stable writes a YYYYMMDD version (< FIRST_LAZER_VERSION 30_000_000) and
      its counters total ``N + M`` — the hold is ONE judgement, resolved by the
      RELEASE.  Holding is the whole test, so the release is what is judged.
    * osu!lazer writes >= 30_000_000 and its counters total ``N + 2M`` — a
      HoldNote nests a HeadNote and a TailNote, each a ``Note`` and so each its
      own ``ManiaJudgement`` (osu.Game.Rulesets.Mania/Objects/HoldNote.cs,
      ``CreateNestedHitObjects``).

    A renderer that assumes one model for both reports a wildly wrong count on
    the other: on an LN-only stable chart (5366777.osu, 4258 holds) counting the
    release as well invents 4258 judgements, and taking the HEAD instead of the
    release turns 268 of the game's greats into perfects.
    """
    return 1 if getattr(replay, "classic", False) else 2


def _quality(j: Judgement) -> tuple:
    """Ordering key for reconciliation: worse judgements first.

    A result that no press produced (the object simply ran out of time) is the
    worst thing that can happen; otherwise the result itself ranks, and within
    one result the larger |offset| is the less deserved.
    """
    rank = HIT_RESULTS.index(j.result) if j.result in HIT_RESULTS else len(HIT_RESULTS)
    if not j.by_press:
        rank = len(HIT_RESULTS)
    return (-rank, -abs(j.offset or 0.0))


def reconcile(judgements: list, counts: dict) -> tuple[list, int]:
    """Force the judgement multiset to equal the score's own recorded counts.

    The .osr header carries the judgement counts osu! itself recorded for the
    play.  They are the authoritative answer to "what accuracy did this score
    get" — lazer reads exactly these when it decodes a legacy score rather than
    re-deriving them (osu.Game/Scoring/Legacy/LegacyScoreDecoder.cs), and the
    osu! website's accuracy is a pure function of them.

    This engine can still disagree with them by a few judgements, because the
    client's input matching is not fully reproducible from a replay (osu!stable's
    source is not public, and lazer's OrderedHitPolicy is not what stable does —
    a single stray press cascades differently).  So the counts decide, and the
    engine's own ordering decides WHICH judgement moves: the results are
    re-dealt worst-first over judgements ordered worst-first, so the ones that
    change are always the ones nearest the boundary.  Every judgement keeps its
    time, so the counter's curve is unchanged; only its final value is pinned.

    Returns (judgements, number_of_results_changed).
    """
    target = canonical_counts(counts)
    total = sum(target.values())
    if total == 0 or total != len(judgements):
        return judgements, 0

    have: dict[str, int] = {}
    for j in judgements:
        have[j.result] = have.get(j.result, 0) + 1
    if all(have.get(k, 0) == target[k] for k in HIT_RESULTS):
        return judgements, 0

    desired: list[str] = []
    for name in reversed(HIT_RESULTS):      # worst first, matching _quality
        desired.extend([name] * target[name])

    ordered = sorted(judgements, key=_quality)
    changed = sum(1 for j, name in zip(ordered, desired) if j.result != name)
    for j, name in zip(ordered, desired):
        j.result = name

    return judgements, changed


def replay_judgements(bm, replay, od: float | None = None,
                      counts: dict | None = None,
                      speed_multiplier: float = 1.0,
                      difficulty_multiplier: float = 1.0,
                      reconcile_counts: bool = True) -> list[Judgement]:
    """Every judgement a renderer should show for this replay, in time order.

    Applies the writing client's object model (:func:`judgements_per_hold`) and,
    when the score's own counts are available, pins the totals to them
    (:func:`reconcile`).  This is the entry point the HUD uses; ``judge_replay``
    stays the pure lazer simulation.
    """
    all_j = judge_replay(bm, replay, od=od, speed_multiplier=speed_multiplier,
                         difficulty_multiplier=difficulty_multiplier)
    per_hold = judgements_per_hold(replay)

    # The header's own total picks the model when the two disagree, so a chart
    # whose holds are laid out unusually still lands on the right count.
    if counts:
        total = sum(canonical_counts(counts).values())
        n = sum(1 for h in bm.hit_objects if not h.is_hold)
        m = sum(1 for h in bm.hit_objects if h.is_hold)
        if per_hold * m + n != total and (3 - per_hold) * m + n == total:
            per_hold = 3 - per_hold

    if per_hold == 1:
        # Stable: one judgement per hit object, and for a hold it is the RELEASE
        # that decides it.  DrawableHoldNoteTail.GetCappedResult caps a broken
        # hold at Meh, so a missed head or a broken body cannot be beaten.
        #
        # A tail judgement is keyed by the object's END time, so the hold's end
        # has to come from the beatmap to get from a head to its tail.
        hold_end = {(h.column, h.start_time): h.end_time
                    for h in bm.hit_objects if h.is_hold}
        tails = {(j.column, j.obj_start): j for j in all_j if j.kind == "tail"}
        out = []
        for j in all_j:
            if j.kind != "head":
                continue
            end = hold_end.get((j.column, j.obj_start))
            tail = tails.get((j.column, end)) if end is not None else None
            if tail is None:
                out.append(j)
                continue
            if j.result == "miss" and tail.result not in ("miss", "meh"):
                j.result = "meh"
            else:
                j.result = tail.result
                j.offset = tail.offset
                j.by_press = tail.by_press
                j.time = tail.time
            out.append(j)
        all_j = sorted(out, key=lambda j: j.time)

    if counts and reconcile_counts:
        all_j, _changed = reconcile(all_j, counts)
    return all_j
