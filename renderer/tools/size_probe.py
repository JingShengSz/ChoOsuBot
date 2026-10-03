"""How big does a rendered clip actually get? (disk, not RAM)

The web UI's own export is client-side, but the QQ-bot / API path writes every
render to `cache/renders/`, and nothing ever sweeps that directory.

    python tools/size_probe.py --start 60 --seconds 20
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bid", default="2467450")
    ap.add_argument("--skin", default="owc (default)")
    ap.add_argument("--start", type=float, default=60.0)
    ap.add_argument("--seconds", type=float, default=20.0)
    ap.add_argument("--fps", type=int, default=60)
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()

    from mania_render.playfield import build_geometry
    from mania_render.renderer import Renderer
    from mania_render.skin import load_skin
    from mania_render.webapp import SKINS, load_beatmap_by_id

    cache = ROOT / "cache"
    bm, audio_path, bg_path = load_beatmap_by_id(args.bid, cache)
    skin = load_skin(Path(SKINS[args.skin]))
    block = skin.block_for_keys(bm.keys)
    geom = build_geometry(block, scroll_speed=30)

    out = cache / "renders" / "_sizeprobe.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)

    r = Renderer(bm, audio_path, skin, geom, scroll_speed=30, fps=args.fps,
                 background=True, bg_path=bg_path)
    t0 = time.perf_counter()
    r.render_mp4(out, args.start, args.start + args.seconds)
    dt = time.perf_counter() - t0

    mb = out.stat().st_size / 1048576
    mbps = mb * 8 / args.seconds
    print(
        f"\n{args.seconds:.0f}s of real {args.fps}p gameplay, skin={args.skin}\n"
        f"  file      {mb:.1f} MB   ({mbps:.1f} Mbps)\n"
        f"  encoded   in {dt:.1f}s  ({args.seconds / dt * 1.0:.2f}x realtime)\n"
        f"  a 3-minute chart -> about {mb * (180 / args.seconds):.0f} MB on disk"
    )
    if not args.keep:
        out.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
