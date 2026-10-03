"""Which half of a stable hold note carries its single judgement?

Stable counts a hold as ONE judgement (N+H, proven over 31 replays).  This engine
currently uses the HEAD result.  On an LN-only chart (5366777.osu: 101 notes,
4258 holds) that yields 3959 perfect against the game's 3691 -- i.e. the head is
too easy.  Test the release instead.
"""
import sys, os
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from mania_render.osu_file import parse_osu
from mania_render import judge
from mania_render.osr import parse_osr

KEYS = ("perfect", "great", "good", "ok", "meh", "miss")


def tally(results):
    c = Counter(results)
    return {k: c.get(k, 0) for k in KEYS}


def run(osr_path, osu_path, label):
    bm = parse_osu(Path(osu_path).read_text(encoding="utf-8-sig", errors="replace"))
    head, rep = parse_osr(Path(osr_path))
    if head.mirror:
        bm.apply_mirror()
    truth = head.counts
    js = judge.judge_replay(bm, rep, od=bm.od)

    # index judgements by (column, time, kind)
    by = {}
    for j in js:
        by[(j.column, j.obj_start, j.kind)] = j

    heads, tails, release_based = [], [], []
    for h in bm.hit_objects:
        hj = by.get((h.column, h.start_time, "head"))
        hr = hj.result if hj else "miss"
        heads.append(hr)
        if h.is_hold:
            tj = by.get((h.column, h.end_time, "tail"))
            tr = tj.result if tj else "miss"
            tails.append(tr)
            # GetCappedResult: a broken hold cannot beat Meh on the tail.
            release_based.append("meh" if (hr == "miss" and tr not in ("miss", "meh")) else tr)
        else:
            release_based.append(hr)

    n_hold = sum(1 for h in bm.hit_objects if h.is_hold)
    print(f"--- {label}  (N={len(bm.hit_objects) - n_hold}, M={n_hold}, "
          f"total={sum(truth.values())}) ---")
    for nm, got in (("HEAD  ", tally(heads)), ("TAIL  ", tally(tails)),
                    ("RELEASE", tally(release_based))):
        same = all(got[k] == truth[k] for k in KEYS)
        print(f"   {nm}: " + "  ".join(f"{k}={got[k]}" for k in KEYS)
              + ("   <== EXACT" if same else ""))
    print(f"   TRUTH : " + "  ".join(f"{k}={truth[k]}" for k in KEYS))
    print()


CASES = [
    ("cache/osr/01a45e0c040247dc9eef4fedd138e099_replay.osr", "cache/osu/5366777.osu",
     "5366777 LN-only (stable, 4359)"),
    ("cache/osr/129074a49bd649a1b02ca7e6a543cdc8_replay.osr", "cache/osu/4045169.osu",
     "4045169 (stable, 1393)"),
    (r"C:\Users\OwO\Downloads\Kxxn - DnsT3r_7 - Freak Like Me [Freaky Mode 1.4x] (2026-09-26) OsuMania.osr",
     "cache/osu/4659456.osu", "4659456 Freak Like Me (stable, 1363)"),
    ("cache/osr/1c275085088d40e8a2eabecefefe7ade_short_good.osr", "cache/osu/2553926.osu",
     "2553926 (stable, 1705)"),
    ("cache/osr/a25824a24c5d4868a783170c4b071034_replay.osr", "cache/osu/5075177.osu",
     "5075177 (stable, 3022)"),
]
for osr, osu, label in CASES:
    if Path(osr).exists() and Path(osu).exists():
        try:
            run(osr, osu, label)
        except Exception as e:
            print(f"--- {label}: ERROR {e}\n")
