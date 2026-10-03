from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass, field

from . import judge
from .judge import (  # re-exported: renderer.py and the tools import these from here
    mania_hit_windows,
    result_for_offset,
)
from .models import FrameEvents, HitObject, OsuBeatmap, ReplayData


@dataclass
class HudState:
    combo: int = 0
    max_combo: int = 0
    accuracy: float = 100.0
    #: osu!stable's mania accuracy, shown next to the lazer one.  The two differ
    #: on any play that is not all-perfect; see judge.accuracy_percent_stable.
    accuracy_stable: float = 100.0
    clicks_window: list[int] = field(default_factory=list)
    bpm: float = 0.0
    time_s: float = 0.0
    length_s: float = 0.0
    error_ms: float | None = None


def build_fc_sim(bm: OsuBeatmap) -> FrameEvents:
    """Perfect play: every Note/head/tail is a CPS click (ADR-0001)."""
    ev = FrameEvents()
    combo = 0
    pairs: list[tuple[int, int]] = []
    for h in bm.hit_objects:
        ev.clicks.append(h.start_time)  # press = note / LN head only（LN 尾不计 CPS）
        if h.is_hold:
            ev.key_held.setdefault(h.column, []).append((h.start_time, h.end_time))
        else:
            ev.key_held.setdefault(h.column, []).append((h.start_time, h.start_time))
    # Combo trail. An LN contributes 2 (head + tail), a note 1 — but they must be
    # NUMBERED in the order the judgements actually happen, not head-then-tail-immediately.
    #
    # Two bugs lived here. The list was not sorted, and `hud_state_at` stops at the first
    # sample later than the frame, so an LN's far-future tail in the middle froze the
    # counter for the whole hold. And the tail was numbered right after its own head, so
    # notes landing during the hold were numbered after it and the count went *down* when
    # the tail finally arrived. Collect milestones, sort, then number.
    marks: list[int] = []
    for h in bm.hit_objects:
        marks.append(h.start_time)
        if h.is_hold:
            marks.append(h.end_time)
    marks.sort()
    ev.combo_samples = [(t, i + 1) for i, t in enumerate(marks)]
    ev.clicks.sort()
    # FC: every object judged at t=0 offset.  A hold note is TWO judgements
    # (head + tail) — see mania_render/judge.py for why.
    ev.hit_events = []
    ev.hit_pairs = []
    for h in sorted(bm.hit_objects, key=lambda x: x.start_time):
        ev.hit_events.append((h.start_time, 0.0))
        ev.hit_pairs.append((h.start_time, 0.0))
    ev.hit_offsets = [0.0] * len(ev.hit_events)
    ev.judgements = []
    for h in sorted(bm.hit_objects, key=lambda x: x.start_time):
        ev.judgements.append(judge.Judgement(time=int(h.start_time), obj_start=int(h.start_time),
                                             kind="head", result="perfect", offset=0.0))
        if h.is_hold:
            ev.judgements.append(judge.Judgement(time=int(h.end_time), obj_start=int(h.end_time),
                                                 kind="tail", result="perfect", offset=0.0))
    ev.judgements.sort(key=lambda j: j.time)
    return ev


def build_from_replay(bm: OsuBeatmap, replay: ReplayData) -> FrameEvents:
    """CPS from real presses only; combo via perfect-object match against presses."""
    ev = FrameEvents()
    ev.clicks = [p.time_ms for p in replay.presses]

    # held intervals per column from press/release pairs
    for col in range(20):
        downs = [p.time_ms for p in replay.presses if p.column == col]
        ups = [p.time_ms for p in replay.releases if p.column == col]
        holds: list[tuple[int, int]] = []
        di = 0
        ui = 0
        cur: int | None = None
        while di < len(downs) or ui < len(ups):
            nxt_d = downs[di] if di < len(downs) else None
            nxt_u = ups[ui] if ui < len(ups) else None
            if cur is None:
                if nxt_d is None:
                    break
                cur = nxt_d
                di += 1
            else:
                if nxt_u is None or (nxt_d is not None and nxt_d < nxt_u):
                    # next press without release
                    holds.append((cur, cur))
                    cur = nxt_d
                    di += 1
                else:
                    holds.append((cur, nxt_u))
                    cur = None
                    ui += 1
        if cur is not None:
            holds.append((cur, cur))
        if holds:
            ev.key_held[col] = holds

    # Judgement: press-driven and note-locked, exactly as osu!lazer does it.
    # This replaced a "nearest press to each object" matcher, which is not the
    # same algorithm and is the reason the rendered accuracy used to sit a
    # couple of points away from the game's on dense charts.  See judge.py.
    #
    # `replay_judgements` (not `judge_replay`) is the entry point: it applies the
    # object model of the client that WROTE the replay -- osu!stable counts a
    # hold once, osu!lazer twice -- and pins the totals to the counts that same
    # client recorded in the header, so the rendered accuracy is the game's.
    od = bm.od if bm.od is not None else 8.0
    judgements = judge.replay_judgements(bm, replay, od=od,
                                         counts=getattr(replay, "counts", None))
    ev.judgements = judgements

    # The hit-error bar / unstable rate only care about real presses.
    ev.hit_events = sorted((j.time, j.offset) for j in judgements
                           if j.kind == "head" and j.by_press)
    ev.hit_pairs = sorted((j.obj_start, j.offset) for j in judgements
                          if j.kind == "head" and j.by_press)
    ev.hit_offsets = [off for _t, off in ev.hit_events]

    # Combo follows the judgements in the order they are applied: +1 per hit,
    # back to zero on a miss.  Numbering the samples this way is what keeps the
    # counter monotonic while an LN's tail lands after later notes.
    combo = 0
    samples: list[tuple[int, int]] = []
    for j in judgements:
        if j.result == "miss":
            combo = 0
        else:
            combo += 1
        samples.append((int(j.time), combo))
    ev.combo_samples = samples
    return ev


def _bpm_at(bm: OsuBeatmap, t_ms: float) -> float:
    red = [tp for tp in bm.timings if tp.is_red_line and tp.beat_length > 0]
    if not red:
        return 0.0
    red.sort(key=lambda x: x.time)
    chosen = red[0]
    for tp in red:
        if tp.time <= t_ms + 1e-6:
            chosen = tp
        else:
            break
    return float(chosen.bpm)


def hud_state_at(ev: FrameEvents, bm: OsuBeatmap, now_ms: float, length_s: float) -> HudState:
    """SongProgress follows lazer: elapsed song time / full beatmap duration.

    `length_s` is ignored for that readout (kept for API compat); clip range is
    not the denominator — mixing absolute t with clip length is the 35s/30s bug.
    """
    st = HudState()
    song_len = max(0.0, float(getattr(bm, "duration_s", 0.0) or 0.0))
    if song_len <= 0 and bm.hit_objects:
        song_len = max(h.end_time for h in bm.hit_objects) / 1000.0
    st.length_s = song_len
    # absolute position in the song (lead-in frames clamp to 0)
    st.time_s = max(0.0, now_ms / 1000.0)
    if song_len > 0:
        st.time_s = min(st.time_s, song_len)

    combo = 0
    for t, c in ev.combo_samples:
        if t <= now_ms:
            combo = c
        else:
            break
    st.combo = combo
    st.max_combo = combo  # running display; max tracked below
    running = 0
    best = 0
    for t, c in ev.combo_samples:
        if t > now_ms:
            break
        if c == 0:
            running = 0
        else:
            running = c
        if running > best:
            best = running
    st.max_combo = best

    # live BPM from the active red timing point (must change when the map does)
    st.bpm = _bpm_at(bm, now_ms)

    # clicks in last 1000ms (presses / FC clicks)
    win = [t for t in ev.clicks if now_ms - 1000 < t <= now_ms]
    st.clicks_window = win

    # Accuracy, exactly as ScoreProcessor computes it for mania: a PERFECT is
    # worth 305 (not 300), the denominator is 305 per judged object, and a hold
    # note contributes TWO judgements (head + tail).  See mania_render/judge.py
    # for the source citations — the old formula here was "close" and agreed
    # only on an all-perfect play.
    counts = judge_counts(bm, ev, now_ms=now_ms)
    st.accuracy = judge.accuracy_percent(counts)
    # ...and the stable figure beside it, so both are visible at once.
    st.accuracy_stable = judge.accuracy_percent_stable(counts)

    if ev.hit_offsets:
        # nearest offset to now for bar meter trail — show last few
        st.error_ms = None
        recent = [o for t, o in zip(
            [h for h in range(len(ev.hit_offsets))],  # placeholder
            ev.hit_offsets,
        )]
        st.error_ms = ev.hit_offsets[-1] if ev.hit_offsets else None

    return st


def recent_errors(ev: FrameEvents, bm: OsuBeatmap, now_ms: float, count: int = 24) -> list[tuple[int, float]]:
    """(time, offset) samples near now for the bar meter."""
    out: list[tuple[int, float]] = []
    for t, off in ev.hit_events:
        if t <= now_ms <= t + 3000:
            out.append((t, off))
    return out[-count:]


def judge_counts(bm: OsuBeatmap, ev: FrameEvents, od: float | None = None, now_ms: float | None = None) -> dict[str, int]:
    """Mania judgement tallies (stable names).

    MAX/彩=Perfect, 300/黄=Great, 200=Good, 100=Ok, 50=Meh, 0=Miss.
    now_ms: only count judgements already applied by this time (live panel).

    Counted straight from ``ev.judgements``, which is every accuracy-affecting
    judgement — including hold-note TAILS.  The previous version counted only
    ``ev.hit_pairs`` (one entry per matched object, so an LN counted once) and
    re-derived the result from the offset with a matcher of its own; both are
    now judge.py's job.
    """
    counts = {"max": 0, "300": 0, "200": 0, "100": 0, "50": 0, "miss": 0}
    for j in ev.judgements:
        if now_ms is not None and j.time > now_ms:
            continue
        counts[judge._LEGACY_KEY[j.result]] += 1
    return counts


def unstable_rate(ev: FrameEvents, od: float | None = None, default_od: float = 8.0, now_ms: float | None = None) -> float | None:
    """HitEventExtensions.CalculateUnstableRate — UR = 10 * sqrt(M2/n).

    AffectsUnstableRate: only successful hits (result.IsHit()); misses excluded.
    Welford's online algorithm for population variance. now_ms = live cutoff.
    """
    windows = mania_hit_windows(od if od is not None else default_od)
    n = 0
    mean = 0.0
    m2 = 0.0
    for t, off in ev.hit_events:
        if now_ms is not None and t > now_ms:
            continue
        x = float(off)
        r = result_for_offset(x, windows)
        # None means the offset is outside every window (the press judged nothing),
        # so there is no result to include either.
        if r is None or r == "miss":
            continue  # !IsHit()
        n += 1
        next_mean = mean + (x - mean) / n
        m2 += (x - mean) * (x - next_mean)
        mean = next_mean
    if n == 0:
        return None
    return 10.0 * (m2 / n) ** 0.5


def ratio_label(counts: dict[str, int]) -> str:
    """Ratio = MAX/300, 1 decimal. 300==0 → ∞ (n/0, n=MAX)."""
    mx, g = counts.get("max", 0), counts.get("300", 0)
    if g == 0:
        return "∞"
    return f"{mx / g:.1f}"
