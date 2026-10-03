"""Is the game's matcher an optimal (nearest-press) assignment?

My engine implements lazer's OrderedHitPolicy faithfully: a press is offered to
the EARLIEST unjudged object in the column, so a single ghost press cascades.
That produced 1082/249/16/4/6/6.  The game shows 1082/258/16/1/0/6.

This script solves, per column, the minimum-total-|offset| assignment of presses
to notes (each press used at most once, each note gets at most one press) and
compares the resulting counts with the game's.
"""
import sys, os
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from mania_render.osu_file import parse_osu
from mania_render import osr as osm, judge

W = 10 ** 7          # penalty for an unmatched note (a miss)
P = 1                # penalty for wasting a press

OSR = Path(r"C:\Users\OwO\Downloads\Kxxn - DnsT3r_7 - Freak Like Me [Freaky Mode 1.4x] (2026-09-26) OsuMania.osr")
txt = (ROOT / "cache" / "osu" / "4659456.osu").read_text(encoding="utf-8-sig", errors="replace")
bm = parse_osu(txt)
head, rep = osm.parse_osr(OSR)

win = judge.mania_hit_windows(bm.od, classic=rep.classic)
MEH = win["meh"]
OK = win["ok"]
print("windows:", {k: round(v, 3) for k, v in win.items()})

by_col_notes = defaultdict(list)
for h in bm.hit_objects:
    by_col_notes[h.column].append(h)
by_col_press = defaultdict(list)
for p in rep.presses:
    by_col_press[p.column].append(p.time_ms)


def matchable(off):
    """Can a press with this offset be accepted by the note at all?"""
    if off > 0:
        # stable: the late OK window is OPEN -- beyond it is a Miss, and a Meh
        # is impossible when late.
        return off < OK
    return -off <= MEH


def solve(notes, press):
    n, m = len(notes), len(press)
    INF = float("inf")
    # dp[j] = best cost for notes[0..i) against press[0..j)
    prev = [P * j for j in range(m + 1)]
    choice = []
    for i in range(1, n + 1):
        cur = [0.0] * (m + 1)
        ch = [0] * (m + 1)
        cur[0] = prev[0] + W
        ch[0] = 0
        nt = notes[i - 1]
        for j in range(1, m + 1):
            off = press[j - 1] - nt
            best, bc = prev[j] + W, 0            # this note is missed
            w = cur[j - 1] + P                   # this press is wasted
            if w < best:
                best, bc = w, 2
            if matchable(off):
                c = prev[j - 1] + abs(off)
                if c < best:
                    best, bc = c, 1
            cur[j] = best
            ch[j] = bc
        choice.append(ch)
        prev = cur
    # backtrack
    pairs = []
    i, j = n, m
    while i > 0 and j >= 0:
        bc = choice[i - 1][j]
        if bc == 1:
            pairs.append((notes[i - 1], press[j - 1]))
            i -= 1
            j -= 1
        elif bc == 0:
            i -= 1
        else:
            j -= 1
    pairs.reverse()
    return pairs


counts = defaultdict(int)
missed = 0
for col in sorted(by_col_notes):
    notes = sorted(h.start_time for h in by_col_notes[col])
    press = sorted(by_col_press[col])
    pairs = solve(notes, press)
    matched = {t for t, _ in pairs}
    for nt, pt in pairs:
        r = judge.result_for_offset(pt - nt, win) or "miss"
        counts[r] += 1
    for nt in notes:
        if nt not in matched:
            counts["miss"] += 1
            missed += 1

GAME = {"perfect": 1082, "great": 258, "good": 16, "ok": 1, "meh": 0, "miss": 6}
tot = sum(counts.values())
print()
print(f"optimal-assignment: " + "  ".join(f"{k}={counts.get(k, 0)}" for k in
      ("perfect", "great", "good", "ok", "meh", "miss")))
print(f"game              : " + "  ".join(f"{k}={GAME[k]}" for k in
      ("perfect", "great", "good", "ok", "meh", "miss")))
print(f"total {tot}  (game 1363)")
print()
delta = {k: counts.get(k, 0) - GAME[k] for k in GAME}
print("delta:", delta)
print("EXACT MATCH" if all(v == 0 for v in delta.values()) else "still differs")
print()
print(f"ACC 305 : {judge.accuracy_percent(counts):.4f}%   (game 98.7961%)")
print(f"ACC 300 : {judge.accuracy_percent_stable(counts):.4f}%")
