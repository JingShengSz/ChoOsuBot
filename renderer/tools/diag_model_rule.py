"""Does the header's judgement total equal N+H or N+2H, split by replay version?

A stable replay's header is written by osu!stable, a lazer one's by lazer, so this
separates the two object models using the game's own tally.
"""
import sys, os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from mania_render.osu_file import parse_osu
from mania_render.osr import parse_osr

DIRS = [ROOT / "cache" / "osr", Path(r"C:\Users\OwO\Downloads"),
        Path(r"C:\Users\OwO\AppData\Local\osu!\Replays"), Path(r"D:\DeepSeek Harness\workspace\_diag")]

charts = []
for p in sorted((ROOT / "cache" / "osu").glob("*.osu")):
    try:
        bm = parse_osu(p.read_text(encoding="utf-8-sig", errors="replace"))
    except Exception:
        continue
    if not bm.hit_objects:
        continue
    n = sum(1 for h in bm.hit_objects if not h.is_hold)
    m = sum(1 for h in bm.hit_objects if h.is_hold)
    charts.append((p.name, n, m, bm))

replays = []
for d in DIRS:
    if d.is_dir():
        replays.extend(sorted(d.glob("*.osr")))
seen = set()
rows = []
for rp in replays:
    if rp.name in seen:
        continue
    seen.add(rp.name)
    try:
        head, rep = parse_osr(rp)
    except Exception:
        continue
    total = sum(head.counts.values())
    if total == 0:
        continue
    one = [(c[0], c[1], c[2]) for c in charts if c[1] + c[2] == total]
    two = [(c[0], c[1], c[2]) for c in charts if c[1] + 2 * c[2] == total]
    rows.append((rp.name, head.version, total, one, two))

print(f"{'replay':<40} {'version':>10} {'total':>6}  fits N+H        fits N+2H")
print("-" * 100)
for name, ver, total, one, two in sorted(rows, key=lambda r: r[1]):
    kind = "stable" if ver < 30000000 else "lazer"
    o = f"{len(one)}" + (f" {one[0]}" if len(one) == 1 else "")
    t = f"{len(two)}" + (f" {two[0]}" if len(two) == 1 else "")
    print(f"{name[:38]:<40} {ver:>10} {total:>6}  {o:<15} {t:<15} {kind}")

print()
print("=== summary ===")
for ver_min, ver_max, label in ((0, 30000000, "stable"), (30000000, 1 << 31, "lazer")):
    grp = [r for r in rows if ver_min <= r[1] < ver_max]
    only_one = [r for r in grp if r[3] and not r[4]]
    only_two = [r for r in grp if r[4] and not r[3]]
    both = [r for r in grp if r[3] and r[4]]
    neither = [r for r in grp if not r[3] and not r[4]]
    print(f"{label:<7} n={len(grp):<3} only N+H={len(only_one):<3} only N+2H={len(only_two):<3} "
          f"both={len(both):<3} unresolved={len(neither)}")
