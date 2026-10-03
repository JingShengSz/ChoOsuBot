"""Diagnose the 'Freak Like Me' replay: object model vs judgement total."""
import sys, os, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from mania_render.osu_file import parse_osu
from mania_render import osr as osm

OSR = Path(r"C:\Users\OwO\Downloads\Kxxn - DnsT3r_7 - Freak Like Me [Freaky Mode 1.4x] (2026-09-26) OsuMania.osr")

head, replay = osm.parse_osr(OSR)
print("=== replay header ===")
print("version   ", head.version)
print("mods      ", head.mods)
print("md5       ", head.beatmap_md5)
print("max_combo ", head.max_combo)
print("counts    ", head.counts, "total", sum(head.counts.values()))
print("presses   ", len(replay.presses) if hasattr(replay, "presses") else "?")
print("frames    ", len(replay.frames) if hasattr(replay, "frames") else "?")

# locate chart
cands = []
for p in (ROOT / "cache" / "osu").glob("*.osu"):
    t = p.read_text(encoding="utf-8-sig", errors="replace")
    if "Freak Like Me" not in t:
        continue
    bm = parse_osu(t)
    notes = [h for h in bm.hit_objects if not h.is_hold]
    holds = [h for h in bm.hit_objects if h.is_hold]
    ver = "?"
    for line in t.splitlines():
        if line.lower().startswith("osu file format"):
            ver = line.split("v")[-1].strip()
    cands.append((p, bm, ver, len(notes), len(holds)))

print()
print("=== candidate charts in cache ===")
for p, bm, ver, nn, nh in cands:
    print(f"{p.name}  format v{ver}  OD={bm.od} keys={bm.keys}")
    print(f"    title={bm.title!r}  version={getattr(bm, 'version', '?')!r}")
    print(f"    notes={nn} holds={nh}  ->  N+2H = {nn + 2 * nh}")
    print(f"    (game total 1363 | renderer total 1377)")
