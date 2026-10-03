"""Are the 14 LNs real? Check the replay input against each hold's span.

If the chart revision the replay was played on really had LNs there, the player's
key must stay DOWN for the hold's duration. If the key is tapped, the played
revision had rice notes and the cached .osu is a different revision.
"""
import sys, os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from mania_render.osu_file import parse_osu
from mania_render import osr as osm

txt = (ROOT / "cache" / "osu" / "4659456.osu").read_text(encoding="utf-8-sig", errors="replace")
bm = parse_osu(txt)
holds = sorted([h for h in bm.hit_objects if h.is_hold], key=lambda h: h.start_time)

# fix: hit object lines are x,y,time,type,...
raw = []
for line in txt.splitlines():
    s = line.strip()
    parts = s.split(",")
    if len(parts) >= 5 and parts[2].strip().isdigit() and parts[3].strip().isdigit():
        raw.append(parts)
from collections import Counter
print("type bits:", Counter(int(p[3]) for p in raw))
print("raw lines with type&128:", sum(1 for p in raw if int(p[3]) & 128))
print()

OSR = Path(r"C:\Users\OwO\Downloads\Kxxn - DnsT3r_7 - Freak Like Me [Freaky Mode 1.4x] (2026-09-26) OsuMania.osr")
head, rep = osm.parse_osr(OSR)

# press intervals per column
from collections import defaultdict
intervals = defaultdict(list)
print("replay press/release counts:", len(rep.presses), len(rep.releases))

press_times = defaultdict(list)   # col -> sorted press times
for p in rep.presses:
    press_times[p.column].append(p.time_ms)
rel_times = defaultdict(list)
for r in rep.releases:
    rel_times[r.column].append(r.time_ms)
for c in press_times:
    press_times[c].sort()
    rel_times[c].sort()

print()
print(f"{'col':>3} {'ln start':>9} {'ln end':>9} {'dur':>5} | {'press':>8} {'release':>9} {'held':>6}  verdict")
print("-" * 82)
held_ok = 0
for h in holds:
    cand = [t for t in press_times[h.column] if abs(t - h.start_time) <= 120]
    pt = min(cand, key=lambda t: abs(t - h.start_time)) if cand else None
    rl = None
    if pt is not None:
        after = [t for t in rel_times[h.column] if t >= pt]
        rl = after[0] if after else None
    held = (rl - pt) if (pt is not None and rl is not None) else None
    want = h.end_time - h.start_time
    if held is not None and held >= want * 0.6:
        verdict = "HELD  -> real LN"
        held_ok += 1
    elif held is not None and held < 60:
        verdict = "TAPPED -> rice in played rev"
    else:
        verdict = "?"
    print(f"{h.column:>3} {h.start_time:>9} {h.end_time:>9} {want:>5} | "
          f"{pt if pt is not None else -1:>8} {rl if rl is not None else -1:>9} "
          f"{held if held is not None else -1:>6}  {verdict}")

print()
print(f"holds held >= 60% of duration: {held_ok} / {len(holds)}")
