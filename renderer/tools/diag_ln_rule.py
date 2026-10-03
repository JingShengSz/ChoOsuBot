"""What rule turns a stable hold's head+release into its ONE judgement?

Print the head-offset and release-offset histograms for the LN-only chart so the
threshold that yields the game's 3691 perfect / 662 great can be read off.
"""
import sys, os
from pathlib import Path
from collections import Counter, defaultdict

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from mania_render.osu_file import parse_osu
from mania_render import judge
from mania_render.osr import parse_osr

bm = parse_osu((ROOT / "cache" / "osu" / "5366777.osu").read_text(encoding="utf-8-sig", errors="replace"))
head, rep = parse_osr(ROOT / "cache" / "osr" / "01a45e0c040247dc9eef4fedd138e099_replay.osr")
truth = head.counts
print("truth:", truth, "total", sum(truth.values()))
print(f"N={sum(1 for h in bm.hit_objects if not h.is_hold)} "
      f"M={sum(1 for h in bm.hit_objects if h.is_hold)}")

js = judge.judge_replay(bm, rep, od=bm.od)
by = {}
for j in js:
    by[(j.column, j.obj_start, j.kind)] = j

heads, rels, held = [], [], []
for h in bm.hit_objects:
    hj = by.get((h.column, h.start_time, "head"))
    tj = by.get((h.column, h.end_time, "tail"))
    if h.is_hold:
        heads.append(hj.offset if hj and hj.by_press else None)
        rels.append(tj.offset if tj else None)   # already /1.5
        held.append((hj.result if hj else "miss", tj.result if tj else "miss"))

print()
print("=== head offset histogram (LN only, by_press) ===")
c = Counter()
for o in heads:
    if o is None:
        c["no-press"] += 1
    else:
        c[int(round(o))] += 1
neg = sorted(k for k in c if isinstance(k, int) and k < 0)
pos = sorted(k for k in c if isinstance(k, int) and k >= 0)
print("  negatives (early):", [(k, c[k]) for k in neg][:40])
print("  positives (late) :", [(k, c[k]) for k in pos][:40])

print()
print("=== cumulative: perfects if head perfect window = W ===")
print(f"{'W':>4} {'perfect':>8} {'great':>8} {'good':>8}")
for W in (4, 6, 8, 9, 10, 11, 12, 13, 14, 15, 16, 16.5):
    p = sum(1 for o in heads if o is not None and abs(o) <= W)
    g = sum(1 for o in heads if o is not None and W < abs(o) <= 40.5)
    d = sum(1 for o in heads if o is not None and 40.5 < abs(o) <= 73.5)
    print(f"{W:>4} {p:>8} {g:>8} {d:>8}")

print()
print("=== release offset (/1.5) histogram ===")
cr = Counter()
for o in rels:
    if o is None:
        cr["none"] += 1
    else:
        cr[int(round(o))] += 1
print("  negatives:", [(k, cr[k]) for k in sorted(k for k in cr if isinstance(k, int) and k < 0)][:40])
print("  positives:", [(k, cr[k]) for k in sorted(k for k in cr if isinstance(k, int) and k >= 0)][:40])
print()
print(f"{'W':>4} {'perfect':>8} {'great':>8} {'good':>8}  (release/1.5)")
for W in (4, 6, 8, 10, 12, 14, 16, 16.5):
    p = sum(1 for o in rels if o is not None and abs(o) <= W)
    g = sum(1 for o in rels if o is not None and W < abs(o) <= 40.5)
    d = sum(1 for o in rels if o is not None and 40.5 < abs(o) <= 73.5)
    print(f"{W:>4} {p:>8} {g:>8} {d:>8}")

print()
print("=== cross-tab head vs tail result (LN only) ===")
ct = Counter(held)
for k, v in sorted(ct.items(), key=lambda kv: -kv[1])[:12]:
    print(f"   head={k[0]:<8} tail={k[1]:<8} n={v}")

print()
print("=== how often is |head| <= 16 but |release| > 16? ===")
bad = sum(1 for hh, rr in zip(heads, rels)
          if hh is not None and rr is not None and abs(hh) <= 16 and abs(rr) > 16)
print(f"   {bad}  (truth needs ~268 head-perfects to become greats)")
print("=== how often is |head| <= 16 and |release| > 26? ===")
print("  ", sum(1 for hh, rr in zip(heads, rels)
              if hh is not None and rr is not None and abs(hh) <= 16 and abs(rr) > 26))
