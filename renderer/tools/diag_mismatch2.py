"""Keyed by (column, obj_start) now, so chords cannot collide."""
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
print(f"head judgements: {len(js)}")
win = judge.mania_hit_windows(bm.od, classic=rep.classic)
print("windows:", {k: round(v, 3) for k, v in win.items()})
print()

bad = [j for j in js if j.result in ("ok", "meh")]
print(f"rated ok/meh: {len(bad)}   (game: 1 ok, 0 meh)")
print()

presses = defaultdict(list)
for p in rep.presses:
    presses[p.column].append(p.time_ms)
for c in presses:
    presses[c].sort()

obj_by = {}
for h in bm.hit_objects:
    obj_by[(h.column, h.start_time)] = h

for j in sorted(bad, key=lambda j: j.time):
    o = obj_by.get((j.column, j.obj_start))
    ps = presses[j.column]
    near = [t for t in ps if abs(t - j.obj_start) <= 160]
    # what result WOULD each nearby press give?
    detail = " ".join(
        f"{t}({t - j.obj_start:+d}->{judge.result_for_offset(t - j.obj_start, win) or 'None'})"
        for t in near)
    print(f"col {j.column}  obj {j.obj_start}  hold={getattr(o,'is_hold',None)}  "
          f"engine={j.result} off={j.offset:+.1f}")
    print(f"      nearby presses: {detail}")

print()
print("=== do the ok/meh results cluster by column? ===")
c = defaultdict(int)
for j in bad:
    c[j.column] += 1
print(dict(c))
print()
print("=== sign of offset (late = positive) ===")
print("late:", sum(1 for j in bad if j.offset > 0), " early:", sum(1 for j in bad if j.offset < 0))
print()
print("=== all head results by column ===")
byc = defaultdict(lambda: defaultdict(int))
for j in js:
    byc[j.column][j.result] += 1
for col in sorted(byc):
    print(f"  col {col}: {dict(byc[col])}")
