"""Raw timeline for the drifting column-3 stream (uses the parser's own output)."""
import sys, os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from mania_render.osu_file import parse_osu
from mania_render import osr as osm, judge

OSR = Path(r"C:\Users\OwO\Downloads\Kxxn - DnsT3r_7 - Freak Like Me [Freaky Mode 1.4x] (2026-09-26) OsuMania.osr")
txt = (ROOT / "cache" / "osu" / "4659456.osu").read_text(encoding="utf-8-sig", errors="replace")
bm = parse_osu(txt)
head, rep = osm.parse_osr(OSR)

COL = 3
LO, HI = 54300, 56200

c3notes = sorted([h for h in bm.hit_objects if h.column == COL], key=lambda h: h.start_time)
c3press = sorted(p.time_ms for p in rep.presses if p.column == COL)
c3rel = sorted(r.time_ms for r in rep.releases if r.column == COL)

js = {j.obj_start: j for j in judge.judge_replay(bm, rep, bm.od, classic=rep.classic)
      if j.kind == "head"}

# build a merged timeline
rows = []
for h in c3notes:
    if LO <= h.start_time <= HI:
        j = js.get(h.start_time)
        rows.append((h.start_time, "NOTE", f"{'HOLD' if h.is_hold else 'note'}"
                     + (f" end {h.end_time}" if h.is_hold else ""), j))
for t in c3press:
    if LO <= t <= HI:
        rows.append((t, "press", "", None))
for t in c3rel:
    if LO <= t <= HI:
        rows.append((t, "release", "", None))
rows.sort(key=lambda r: (r[0], r[1]))

print(f"column {COL}: {len(c3notes)} notes total, {len(c3press)} presses, {len(c3rel)} releases")
print()
print(f"{'time':>7}  {'kind':<8} {'note':<14} engine verdict")
print("-" * 78)
for t, kind, note, j in rows:
    if kind == "NOTE":
        verdict = (f"{j.result:<8} offset {j.offset:>7.1f}  press at "
                   f"{j.obj_start + j.offset if j.offset is not None else -1:.0f}"
                   if j else "(no head judgement)")
    else:
        # which note did the engine consume this press for?
        owner = [jj for jj in js.values()
                 if jj.by_press and jj.offset is not None
                 and abs(jj.obj_start + jj.offset - t) < 0.5]
        verdict = ("-> consumed by obj " + ", ".join(str(o.obj_start) for o in owner)) if owner else ""
    print(f"{t:>7}  {kind:<8} {note:<14} {verdict}")

print()
print("=== presses in window (raw) ===")
print([t for t in c3press if LO <= t <= HI])
print()
print("=== inter-press gaps ===")
pw = [t for t in c3press if LO - 500 <= t <= HI + 500]
print([pw[i + 1] - pw[i] for i in range(len(pw) - 1)])
print()
print("=== note gaps ===")
nw = [h.start_time for h in c3notes if LO - 500 <= h.start_time <= HI + 500]
print([nw[i + 1] - nw[i] for i in range(len(nw) - 1)])
