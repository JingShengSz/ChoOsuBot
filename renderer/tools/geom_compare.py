"""Dump the Python renderer's playfield geometry and receptor geometry for one
beatmap/skin, so it can be compared numerically with the WebGL page's state.

    python tools/geom_compare.py [bid] [skin] [cache-osu-path]

`window.__mania.state` on the page reports colX/colW/hitY/scale/texScale; this
prints the same quantities plus the rectangle the receptor sprite is blitted to,
which is where the two renderers are suspected to disagree.
"""
from __future__ import annotations

import json
import pathlib
import sys
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mania_render.fetch import load_beatmap_by_id  # noqa: E402
from mania_render.playfield import VIEW_H, VIEW_W, build_geometry  # noqa: E402
from mania_render.skin import load_skin  # noqa: E402

CACHE = ROOT / "cache"


def registered() -> dict[str, str]:
    """Ask the running service which skins it has — never hardcode skin paths.

    An earlier revision baked absolute paths in here and one of them carried a
    typo (`RealTBNerKenny`), which failed only when that skin was selected.
    """
    with urllib.request.urlopen("http://127.0.0.1:8760/api/skins", timeout=30) as r:
        data = json.loads(r.read().decode())
    return {s["key"]: s["path"] for s in data["skins"]}


def main() -> int:
    bid = sys.argv[1] if len(sys.argv) > 1 else "4399290"
    skin_key = sys.argv[2] if len(sys.argv) > 2 else "boj 1-10K"

    print(f"loading skin {skin_key!r} …")
    skin = load_skin(pathlib.Path(registered()[skin_key]))
    bm = load_beatmap_by_id(bid, CACHE)[0]
    keys = len(bm.columns) if hasattr(bm, "columns") else 4
    print(f"keys detected: {keys}")

    block = skin.block_for_keys(keys)
    geom = build_geometry(block, scroll_speed=30.0)

    print(f"\nview                     {VIEW_W}x{VIEW_H}")
    print(f"keys                     {geom.keys}")
    print(f"col_x                    {[round(v, 2) for v in geom.col_x]}")
    print(f"col_w                    {[round(v, 2) for v in geom.col_w]}")
    print(f"hit_y                    {round(geom.hit_y, 2)}")
    print(f"stage_left / right       {round(geom.stage_left, 2)} / {round(geom.stage_right, 2)}")
    print(f"scale (768-space→view)   {geom.scale:.5f}   (VIEW_H/768 = {VIEW_H/768:.5f})")

    print("\nreceptor sprites (what _static_stage draws):")
    for i in range(geom.keys):
        name = None
        if block and i in block.key_images:
            name = block.key_images[i].get("up")
        if not name:
            name = "mania-key1" if i % 2 == 0 else "mania-key2"
        img = skin.textures.get(name) or skin.textures.get("mania-keys")
        if not img:
            print(f"  col {i}: {name:<14} MISSING")
            continue
        w = max(2, int(geom.col_w[i]))
        h = max(4, int(img.height * geom.scale))
        x = int(geom.col_x[i])
        # LegacyKeyArea: width stretched to the column, height = the texture's own
        # height, anchored BottomCentre against the column.
        y = VIEW_H - h
        print(f"  col {i}: {name:<14} tex={img.width}x{img.height}  "
              f"-> rect=({x}, {y}, {w}, {h})  [bottom-anchored at {VIEW_H}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
