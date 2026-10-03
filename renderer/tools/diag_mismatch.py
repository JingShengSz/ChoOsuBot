"""Find the 9 head judgements that my engine rates too harshly.

Engine (heads only): perfect 1082, great 249, good 16, ok 4, meh 6, miss 6  = 1363
Game               : perfect 1082, great 258, good 16, ok 1, meh 0, miss 6  = 1363

perfect/good/miss agree exactly.  The engine calls 9 results ok/meh that the
game calls GREAT.  Print each of them with full context.
"""
import sys, os
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from mania_render.osu_file import parse_osu
from mania_render import osr as osm, judge

OSR = Path(r"C:\Users\OwO\Downloads\Kxxn - DnsT3r_7 - Freak Like Me [Freaky Mode 1.4x] (2026-09-26) OsuMania.osr")
txt = (ROOT / "cache" / "osu" / "4659456.osu").read_text(encoding="utf-8-sig", errors="replace")
bm = parse_osu(txt)
head, rep = osm.parse_osr(OSR)

js = [j for j in judge.judge_replay(bm, rep, bm.od, classic=rep.classic) if j.kind == "head"]
by_start = {h.start_time: h for h in bm.hit_objects}

win = judge.mania_hit_windows(bm.od, False, rep.classic)
print("windows:", {k: round(v, 2) for k, v in win.items()})
print()

bad = [j for j in js if j.result in ("ok", "meh")]
print(f"engine head judgements rated ok/meh: {len(bad)}  (game has 1 ok, 0 meh)")
print()
hdr = f"{'obj time':>9} {'col':>3} {'hold?':>6} {'result':>7} {'offset':>8} {'by_press':>9} {'prev obj':>9} {'gap':>6}"
print(hdr)
print("-" * len(hdr))
press_times = defaultdict(list)
for p in rep.presses:
    press_times[p.column].append(p.time_ms)
for c in press_times:
    press_times[c].sort()

for j in sorted(bad, key=lambda j: j.time):
    o = by_start.get(j.obj_start)
    is_hold = o.is_hold if o else None
    # previous object in the same column
    prev = [h.start_time for h in bm.hit_objects if h.column == o.column and h.start_time < o.start_time]
    prev_t = max(prev) if prev else -1
    print(f"{j.obj_start:>9} {o.column:>3} {str(is_hold):>6} {j.result:>7} "
          f"{j.offset if j.offset is not None else float('nan'):>8.1f} {str(j.by_press):>9} "
          f"{prev_t:>9} {o.start_time - prev_t if prev_t >= 0 else -1:>6}")

print()
print("=== how many of the 14 hold heads are involved? ===")
hold_starts = {h.start_time for h in bm.hit_objects if h.is_hold}
involved = [j for j in bad if j.obj_start in hold_starts]
print(f"{len(involved)} / {len(bad)} bad judgements are HOLD heads (14 holds total)")
for j in involved:
    print(f"   hold head at {j.obj_start} col {by_start[j.obj_start].column} -> {j.result} offset {j.offset}")

print()
print("=== nearest press for each bad judgement (any column) ===")
allp = sorted((p.time_ms, p.column) for p in rep.presses)
import bisect
for j in sorted(bad, key=lambda j: j.time):
    times = [t for t, c in allp]
    i = bisect.bisect_left(times, j.obj_start)
    near = allp[max(0, i - 3):i + 3]
    s = " ".join(f"{t}(c{c},{t - j.obj_start:+d})" for t, c in near)
    print(f"  obj {j.obj_start} c{by_start[j.obj_start].column} [{j.result}]: {s}")
