"""Decide the object model by exact reproduction of the in-game counts.

The game reported:  Max 1082 / 300 258 / 200 16 / 100 1 / 50 0 / MISS 6  (total 1363)
The renderer produced: Max 1092 / 300 253 / 200 16 / 100 4 / 50 6 / MISS 6 (total 1377)
The chart has N=1349 rice + H=14 holds -> N+2H = 1377, N+H = 1363.

Whichever model reproduces the game's per-category counts exactly is correct.
"""
import sys, os
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from mania_render.osu_file import parse_osu
from mania_render import osr as osm, judge

OSR = Path(r"C:\Users\OwO\Downloads\Kxxn - DnsT3r_7 - Freak Like Me [Freaky Mode 1.4x] (2026-09-26) OsuMania.osr")
txt = (ROOT / "cache" / "osu" / "4659456.osu").read_text(encoding="utf-8-sig", errors="replace")
bm = parse_osu(txt)
head, rep = osm.parse_osr(OSR)

GAME = {"perfect": 1082, "great": 258, "good": 16, "ok": 1, "meh": 0, "miss": 6}
RENDERER = {"perfect": 1092, "great": 253, "good": 16, "ok": 4, "meh": 6, "miss": 6}
NOTE_TOTAL = sum(1 for h in bm.hit_objects if not h.is_hold)
HOLD_TOTAL = sum(1 for h in bm.hit_objects if h.is_hold)

print(f"chart: OD={bm.od}  keys={bm.keys}  notes={NOTE_TOTAL} holds={HOLD_TOTAL}")
print(f"replay: version={head.version} classic={rep.classic} presses={len(rep.presses)}")
print()


def tally(js):
    c = Counter(j.result for j in js)
    return {k: c.get(k, 0) for k in ("perfect", "great", "good", "ok", "meh", "miss")}


def show(label, counts):
    total = sum(counts.values())
    acc305 = judge.accuracy_percent(counts)
    acc300 = judge.accuracy_percent_stable(counts)
    print(f"{label}")
    print(f"   " + "  ".join(f"{k}={counts[k]}" for k in ("perfect", "great", "good", "ok", "meh", "miss")))
    print(f"   total={total}   ACC(lazer 305)={acc305:.4f}%   ACC(stable 300)={acc300:.4f}%")


for classic in (rep.classic, True, False):
    js = judge.judge_replay(bm, rep, bm.od, classic=classic)
    print(f"########## classic={classic}  ({len(js)} judgements) ##########")
    heads_only = [j for j in js if j.kind == "head"]
    tails_only = [j for j in js if j.kind == "tail"]
    print(f"   heads={len(heads_only)}  tails={len(tails_only)}")
    show("   ALL (head + tail)", tally(js))
    show("   HEADS ONLY", tally(heads_only))
    print()

print("=" * 70)
print("TARGETS")
show("GAME (in-game score)", GAME)
show("RENDERER (what we shipped)", RENDERER)
print()
print("delta renderer - game:", {k: RENDERER[k] - GAME[k] for k in GAME})
