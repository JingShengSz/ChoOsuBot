"""Dump the 14 'holds' of the Freak Like Me chart - are they real LNs?"""
import sys, os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from mania_render.osu_file import parse_osu

txt = (ROOT / "cache" / "osu" / "4659456.osu").read_text(encoding="utf-8-sig", errors="replace")
bm = parse_osu(txt)

holds = [h for h in bm.hit_objects if h.is_hold]
notes = [h for h in bm.hit_objects if not h.is_hold]
print(f"notes={len(notes)} holds={len(holds)}")
print()
print(f"{'#':>3} {'col':>3} {'start':>9} {'end':>9} {'dur':>8}  {'raw line'}")
print("-" * 78)

# raw hitobject lines to see the declared type bits
raw = []
for line in txt.splitlines():
    s = line.strip()
    if not s or s.startswith("//") or s[0] not in "0123456789":
        continue
    parts = s.split(",")
    if len(parts) >= 5 and ":" in parts[0]:
        raw.append(parts)

hold_raw = [p for p in raw if int(p[3]) & 128]
print(f"raw lines with type&128 = {len(hold_raw)}")
for i, p in enumerate(hold_raw):
    st, et = int(p[2]), int(p[5]) if len(p) > 5 else -1
    print(f"{i:>3} {p[0]:>3} {st:>9} {et:>9} {et - st:>8}  {','.join(p)}")

print()
print("=== duration histogram of holds ===")
durs = sorted(h.end_time - h.start_time for h in holds)
print(durs)
print()
print("=== any hold shorter than 50ms? ===")
short = [h for h in holds if h.end_time - h.start_time < 50]
print(f"{len(short)} short holds")
for h in short:
    print(f"   col {h.column}  {h.start_time} -> {h.end_time}  ({(h.end_time - h.start_time)} ms)")

print()
print("=== type bits seen across all objects ===")
from collections import Counter
c = Counter(int(p[3]) for p in raw)
print(c)
