"""Why is the LN tail missing, and where does a note actually land?

Prints, per column: which note sprites the skin resolves (body/head/tail/hold) and
what rectangle the renderer computes for each. Then walks one real hold note and
prints the y of its head, tail and the judgement line at several moments, so the
"tail never shows" and "note lands in the wrong place" reports can be checked
against numbers instead of the picture.
"""
from __future__ import annotations

import json
import pathlib
import sys
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mania_render.fetch import load_beatmap_by_id  # noqa: E402
from mania_render.playfield import VIEW_H, build_geometry, y_for_time  # noqa: E402
from mania_render.skin import load_skin  # noqa: E402

CACHE = ROOT / "cache"


def registered() -> dict[str, str]:
    with urllib.request.urlopen("http://127.0.0.1:8760/api/skins", timeout=30) as r:
        return {s["key"]: s["path"] for s in json.loads(r.read().decode())["skins"]}


def main() -> int:
    skin_key = sys.argv[1] if len(sys.argv) > 1 else "boj 1-10K"
    bid = sys.argv[2] if len(sys.argv) > 2 else "4399290"

    skin = load_skin(pathlib.Path(registered()[skin_key]))
    bm = load_beatmap_by_id(bid, CACHE)[0]
    keys = bm.keys
    block = skin.block_for_keys(keys)
    geom = build_geometry(block, scroll_speed=30.0)

    print(f"skin={skin_key!r}  bid={bid}  keys={keys}")
    print(f"hit_y={geom.hit_y:.1f}  col_x={[round(v,1) for v in geom.col_x]}")
    print(f"col_w={[round(v,1) for v in geom.col_w]}")

    print("\nnote_images from skin.ini:")
    for col in range(keys):
        entry = (block.note_images.get(col) if block else None) or {}
        print(f"  col {col}: {entry or '(none — fall back to mania-note*)'}")

    print("\nresolved sprites (what _note_sprite returns):")
    suffix = {"body": "", "head": "H", "hold": "L", "tail": "T"}
    for col in range(keys):
        row = []
        for kind, sfx in suffix.items():
            name = None
            if block and col in block.note_images:
                name = block.note_images[col].get(kind)
            if not name:
                n = keys
                dist = min(col, (n - 1) - col)
                bank = "S" if n >= 10 else ("1" if dist % 2 == 0 else "2")
                name = f"mania-note{bank}{sfx}"
            img = skin.textures.get(name)
            row.append(f"{kind}={name}{'' if img else ' **MISSING**'}"
                       + (f"({img.width}x{img.height})" if img else ""))
        print(f"  col {col}: " + "  ".join(row))

    holds = [h for h in bm.hit_objects if h.is_hold]
    if not holds:
        print("\nno hold notes in this beatmap")
        return 0
    h = max(holds, key=lambda x: x.end_time - x.start_time)
    print(f"\nlongest hold: col={h.column} {h.start_time}→{h.end_time} "
          f"({(h.end_time-h.start_time)/1000:.2f}s)")

    # note height, as _note_height_px computes it
    w768 = 0.0
    if block and block.column_width and h.column < len(block.column_width):
        w768 = block.column_width[h.column]
    ref = (block.width_for_note_height if block and block.width_for_note_height else w768) or w768
    nh = max(8.0, ref * geom.scale)
    print(f"note height nh={nh:.1f}px  (widthForNoteHeight={getattr(block,'width_for_note_height',None)} w768={w768})")

    print(f"\n{'t(ms)':>8} {'y_head':>8} {'y_tail':>8} {'body bot':>9} {'tail rect y':>12} {'vs hit_y':>9}")
    for frac in (0.0, 0.25, 0.5, 0.9, 0.99):
        t = h.start_time + (h.end_time - h.start_time) * frac
        y1 = y_for_time(geom, h.start_time, t)
        y2 = y_for_time(geom, h.end_time, t)
        bot = min(geom.hit_y, y1) if t >= h.start_time else y1
        tail_y = y2 - nh          # _cap(..., bottom_align=True)
        tail_drawn = y2 < geom.hit_y + nh
        print(f"{int(t):>8} {y1:>8.1f} {y2:>8.1f} {bot:>9.1f} {tail_y:>12.1f} "
              f"{'drawn' if tail_drawn else 'SKIPPED':>9}  (y_tail {y2:.0f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
