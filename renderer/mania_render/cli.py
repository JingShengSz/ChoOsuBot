from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .fetch import load_beatmap_by_id, parse_range
from .osr import parse_osr
from .playfield import build_geometry
from .renderer import Renderer
from .skin import load_skin

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE = ROOT / "cache"

# Skin paths are resolved, not hard-coded: the first one found in the skins directory
# (MANIA_SKINS_DIR, default <root>/skins) or the legacy developer location wins. Absolute
# D:\ paths would simply never resolve on the Linux target.
_SKIN_DIRS = [Path(p) for p in (os.environ.get("MANIA_SKINS_DIR"),)] if os.environ.get("MANIA_SKINS_DIR") else []
_SKIN_DIRS += [ROOT / "skins", Path(r"D:\osu-lazer\exports")]
DEFAULT_SKIN_NAMES = (
    "owc Skin Remake v2 (RealTBNRKenny).osk",
    "# boj - pl0x Circles 1-10K (bojii 「 https) (1).osk",
)


def _find_skin(name: str) -> Path | None:
    for d in _SKIN_DIRS:
        p = d / name
        if p.is_file():
            return p
    return None


def _default_skins() -> list[Path]:
    found = [p for p in (_find_skin(n) for n in DEFAULT_SKIN_NAMES) if p is not None]
    return found


def _pick_skin(keys: int, skin_arg: str | None) -> Path:
    if skin_arg:
        p = Path(skin_arg)
        if not p.exists():
            raise FileNotFoundError(p)
        return p
    # Default first; fall back to the secondary when the first has no block for these keys.
    candidates = _default_skins()
    if not candidates:
        raise SystemExit(
            "没有可用皮肤：把 .osk 放进 skins/（或设置 MANIA_SKINS_DIR），或用 --skin 指定"
        )
    primary = candidates[0]
    skin = load_skin(primary)
    block = skin.block_for_keys(keys)
    if block is not None:
        return primary
    if keys > 10:
        raise SystemExit("暂不支持：键数 > 10")
    if len(candidates) > 1:
        return candidates[1]
    raise SystemExit(f"暂不支持：皮肤无 {keys}K [Mania] 配置")


def main(argv: list[str] | None = None) -> int:
    # web server mode: python -m mania_render --web [--port 8760]
    if argv is None:
        argv = sys.argv[1:]
    if "--web" in argv:
        # Bound to loopback by default; a public VPS needs `--web --host 0.0.0.0`
        # (preferably behind a reverse proxy).
        host = os.environ.get("MANIA_HOST") or "127.0.0.1"
        port = int(os.environ.get("MANIA_PORT") or 8760)
        for i, a in enumerate(argv):
            if a == "--host" and i + 1 < len(argv):
                host = argv[i + 1]
            elif a == "--port" and i + 1 < len(argv):
                port = int(argv[i + 1])
        from .webapp import main as web_main
        return web_main(host=host, port=port)
    p = argparse.ArgumentParser(prog="mania-render", description="osu!mania offline MP4 renderer")
    p.add_argument("--id", help="谱面ID (bid)")
    p.add_argument("--osu-file", help="本地 .osu 覆盖")
    p.add_argument("--audio", help="本地音频覆盖")
    p.add_argument("--skin", help=".osk 或皮肤目录")
    p.add_argument("--replay", help=".osr 回放（可选）")
    p.add_argument("--range", dest="range_", default=None, help="渲染片段 秒，如 0-100（闭区间）")
    p.add_argument(
        "--lead-in",
        type=float,
        default=None,
        help="片头引入秒数；range 从 0 起时默认 1.0s，便于 note 滚入",
    )
    p.add_argument("--scroll-speed", type=float, default=30.0)
    p.add_argument("--fps", type=int, default=60)
    p.add_argument("--no-hit-effects", action="store_true")
    p.add_argument("--no-background", action="store_true")
    p.add_argument("-o", "--out", default=None, help="输出 mp4 路径")
    p.add_argument("--cache", default=str(DEFAULT_CACHE))
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)

    if not args.id and not args.osu_file:
        p.error("需要 --id 或 --osu-file")

    cache = Path(args.cache)
    cache.mkdir(parents=True, exist_ok=True)

    try:
        bm, audio_path, bg_path = load_beatmap_by_id(
            bid=args.id or "",
            cache=cache,
            osu_override=Path(args.osu_file) if args.osu_file else None,
            audio_override=Path(args.audio) if args.audio else None,
        )
    except Exception as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1

    if bm.mode != 3:
        print("错误: 非 mania 谱面", file=sys.stderr)
        return 1

    keys = bm.keys
    if keys > 10:
        print("暂不支持：键数 > 10", file=sys.stderr)
        return 2

    try:
        skin_path = _pick_skin(keys, args.skin)
    except SystemExit as e:
        print(str(e), file=sys.stderr)
        return 2

    skin = load_skin(skin_path)
    block = skin.block_for_keys(keys)
    if block is None:
        print(f"暂不支持：{skin_path.name} 无 {keys}K [Mania]", file=sys.stderr)
        return 2
    block.keys = keys

    dur = bm.duration_s
    if args.range_:
        try:
            start, end = parse_range(args.range_)
        except ValueError as exc:
            print(f"错误: {exc}", file=sys.stderr)
            return 1
        if end > dur + 0.05:
            print(f"错误: 片段 {args.range_} 超过谱面时长 {dur:.3f}s", file=sys.stderr)
            return 1
    else:
        start, end = 0.0, dur

    replay_data = None
    if args.replay:
        _, replay_data = parse_osr(args.replay)

    geom = build_geometry(block, scroll_speed=args.scroll_speed)
    star = f"{bm.title} [{bm.version}]"
    out = Path(args.out) if args.out else cache / "renders" / f"{args.id or 'local'}.mp4"

    print(f"谱面: {bm.title} [{bm.version}]  {keys}K")
    print(f"皮肤: {skin_path.name}  layout_json={skin.has_layout_json}")
    print(f"片段: [{start}, {end}]  fps={args.fps}  scroll={args.scroll_speed}")
    print(f"音频: {audio_path}")
    if args.dry_run:
        return 0

    r = Renderer(
        bm,
        audio_path,
        skin,
        geom,
        scroll_speed=args.scroll_speed,
        fps=args.fps,
        hit_effects=not args.no_hit_effects,
        background=not args.no_background,
        bg_path=bg_path,
        replay=replay_data,
    )
    r.star_text = star
    lead = args.lead_in
    if lead is None:
        lead = 1.0 if start <= 1e-6 else 0.0
    print(f"lead-in: {lead}s" if lead else "lead-in: 无")
    path = r.render_mp4(out, start, end, lead_in_s=lead)
    print(f"已写入: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
