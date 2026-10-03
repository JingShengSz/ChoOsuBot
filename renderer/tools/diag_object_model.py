"""Decide the object model: does a hold note contribute 1 or 2 accuracy judgements?

For every cached replay we can locate a chart for, compare the header's stated
judgement total against N+H (one judgement per hold) and N+2H (head + tail).
"""
import sys, os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from mania_render.osu_file import parse_osu
from mania_render import osr as osm

CACHE = ROOT / "cache" / "osu"

charts = {}
for p in CACHE.glob("*.osu"):
    try:
        t = p.read_text(encoding="utf-8-sig", errors="replace")
        bm = parse_osu(t)
    except Exception:
        continue
    notes = [h for h in bm.hit_objects if not h.is_hold]
    holds = [h for h in bm.hit_objects if h.is_hold]
    charts[p.name] = (bm, len(notes), len(holds), p.stat().st_mtime)

# replay locations
osr_dirs = [Path(r"C:\Users\OwO\Downloads"), ROOT / "cache", ROOT / "samples",
            Path(r"C:\Users\OwO\AppData\Local\osu!\Replays")]
osrs = []
for d in osr_dirs:
    if d.is_dir():
        osrs.extend(sorted(d.glob("*.osr")))
osrs = sorted(set(osrs))

print(f"charts cached: {len(charts)}   replays found: {len(osrs)}")
print()
hdr = f"{'replay':<46}{'ver':>10}{'held':>6}{'note':>6}{'total':>7}{'N+H':>7}{'N+2H':>7}  verdict"
print(hdr)
print("-" * len(hdr))

stats = {"one": 0, "two": 0, "neither": 0}
rows = []
for rp in osrs:
    try:
        head, rep = osm.parse_osr(rp)
    except Exception as e:
        continue
    total = sum(head.counts.values())
    if total == 0:
        continue
    # match a chart by N+2H or N+H
    hit = None
    for name, (bm, nn, nh, mt) in charts.items():
        if nn + 2 * nh == total or nn + nh == total:
            hit = (name, nn, nh)
            break
    if not hit:
        continue
    name, nn, nh = hit
    one, two = nn + nh, nn + 2 * nh
    if total == two and total == one:
        verdict, k = "ambiguous (no holds)", "neither"
    elif total == two:
        verdict, k = "HOLD = 2 judgements", "two"
    elif total == one:
        verdict, k = "HOLD = 1 judgement", "one"
    else:
        verdict, k = "?", "neither"
    stats[k] += 1
    rows.append((rp.name, head.version, nh, nn, total, one, two, verdict))

for r in sorted(rows, key=lambda x: x[7]):
    nm = r[0]
    print(f"{nm[:44]:<46}{r[1]:>10}{r[2]:>6}{r[3]:>6}{r[4]:>7}{r[5]:>7}{r[6]:>7}  {r[7]}")

print()
print("=== verdict tally ===")
for k, v in stats.items():
    print(f"  {k:<10} {v}")

print()
print("=== by replay version (stable vs lazer) ===")
for r in sorted(rows, key=lambda x: x[1]):
    kind = "stable" if r[1] < 30000000 else "lazer "
    print(f"  {kind} v{r[1]:<10} holds={r[2]:<4} total={r[4]:<6} N+H={r[5]:<6} N+2H={r[6]:<6} {r[7]}")
