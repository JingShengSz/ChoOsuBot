"""Measure the server-side memory cost of this project, so "will it fit in 2 GB?"
can be answered with numbers instead of a guess.

Reports Windows PROCESS_MEMORY_COUNTERS (WorkingSet + PeakWorkingSet) around each
heavy operation. No third-party deps.

    python tools/mem_probe.py                # stats + per-skin load_skin + zip read
    python tools/mem_probe.py --render 3     # additionally render a 3-second clip
"""
from __future__ import annotations

import argparse
import ctypes
import gc
import sys
import time
import zipfile
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class _PMC(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


_PSAPI = ctypes.WinDLL("psapi", use_last_error=True)
_PSAPI.GetProcessMemoryInfo.argtypes = [
    wintypes.HANDLE, ctypes.POINTER(_PMC), wintypes.DWORD
]
_PSAPI.GetProcessMemoryInfo.restype = wintypes.BOOL


def mem() -> tuple[float, float, float]:
    """(working set MB, peak working set MB, private/commit MB)."""
    c = _PMC()
    c.cb = ctypes.sizeof(c)
    ok = _PSAPI.GetProcessMemoryInfo(
        ctypes.windll.kernel32.GetCurrentProcess(), ctypes.byref(c), c.cb
    )
    if not ok:
        raise OSError(f"GetProcessMemoryInfo failed: {ctypes.get_last_error()}")
    mb = 1024 * 1024
    return c.WorkingSetSize / mb, c.PeakWorkingSetSize / mb, c.PagefileUsage / mb


def report(label: str, before: tuple[float, float, float]) -> None:
    w, pk, priv = mem()
    print(
        f"  {label:<34} ws={w:7.1f} MB  delta={w - before[0]:+7.1f}  "
        f"peak={pk:7.1f}  commit={priv:7.1f}"
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--render", type=float, default=0.0, metavar="SECONDS")
    ap.add_argument("--bid", default="2467450")
    ap.add_argument("--skin", default=None)
    ap.add_argument("--css", action="store_true", help="only measure the browser-CSS path")
    ap.add_argument(
        "--only-render",
        action="store_true",
        help="skip the per-skin / zip scan (which always loads Suisei and leaves a "
             "1.6 GB high-water mark on the process), so the render cost is measurable alone",
    )
    args = ap.parse_args()

    print("=" * 92)
    print(f"python {sys.version.split()[0]}  ({sys.executable})")
    print("=" * 92)

    base = mem()
    print(f"[0] interpreter baseline            ws={base[0]:7.1f} MB  commit={base[2]:7.1f}")
    if args.css:
        return

    from mania_render.webapp import SKINS  # noqa: E402

    report("after `import webapp`", base)
    after_import = mem()

    print("\n[1] raw .osk read (this is what /api/skin_file/ does per request)")
    for key, path in sorted(SKINS.items(), key=lambda kv: -Path(kv[1]).stat().st_size):
        p = Path(path)
        if not p.is_file():
            continue
        if args.only_render:
            continue
        size = p.stat().st_size / 1024 / 1024
        before = mem()
        data = p.read_bytes()
        w, pk, _ = mem()
        print(
            f"  {key:<22} file={size:7.1f} MB  ws={w:7.1f} (+{w - before[0]:.1f})  "
            f"peak={pk:7.1f}"
        )
        del data
        gc.collect()

    print("\n[2] load_skin()  — decodes EVERY png/jpg into RGBA and keeps them")
    from mania_render.skin import load_skin  # noqa: E402

    for key, path in sorted(SKINS.items(), key=lambda kv: -Path(kv[1]).stat().st_size):
        p = Path(path)
        if not p.is_file():
            continue
        if args.only_render:
            continue
        gc.collect()
        before = mem()
        t0 = time.perf_counter()
        skin = load_skin(p)
        dt = time.perf_counter() - t0
        w, pk, _ = mem()
        raw_px = sum(i.width * i.height for i in skin.textures.images.values()) * 4
        print(
            f"  {key:<22} textures={len(skin.textures.images):5d}  "
            f"decoded={raw_px / 1024 / 1024:7.1f} MB  ws={w:7.1f} (+{w - before[0]:6.1f})  "
            f"peak={pk:7.1f}  {dt:5.1f}s"
        )
        del skin
        gc.collect()

    print("\n[3] zipfile index only (names, no pixel decode)")
    for key, path in sorted(SKINS.items(), key=lambda kv: -Path(kv[1]).stat().st_size):
        p = Path(path)
        if not p.is_file():
            continue
        if args.only_render:
            continue
        gc.collect()
        before = mem()
        n_entries = 0
        with zipfile.ZipFile(p) as zf:
            for info in zf.infolist():
                n_entries += 1
        w, pk, _ = mem()
        print(
            f"  {key:<22} entries={n_entries:5d}  ws={w:7.1f} (+{w - before[0]:.1f})  peak={pk:7.1f}"
        )

    if args.render > 0:
        print(f"\n[4] render_mp4({args.render}s @1080p) — server-side video export")
        from mania_render.playfield import build_geometry  # noqa: E402
        from mania_render.renderer import Renderer  # noqa: E402
        from mania_render.webapp import load_beatmap_by_id  # noqa: E402

        cache = ROOT / "cache"
        bm, audio_path, bg_path = load_beatmap_by_id(args.bid, cache)
        skin_path = Path(SKINS[args.skin]) if args.skin else Path(next(iter(SKINS.values())))
        skin = load_skin(skin_path)
        block = skin.block_for_keys(bm.keys)
        geom = build_geometry(block, scroll_speed=30)
        gc.collect()
        before = mem()
        r = Renderer(
            bm, audio_path, skin, geom, scroll_speed=30, fps=60,
            background=True, bg_path=bg_path, replay=None,
        )
        out = cache / "renders" / "_memprobe.mp4"
        out.parent.mkdir(parents=True, exist_ok=True)

        def cb(i, n, reused):
            if i % 30 == 0:
                w, pk, _ = mem()
                print(f"    frame {i + 1}/{n}   ws={w:7.1f}  peak={pk:7.1f}")

        t0 = time.perf_counter()
        r.render_mp4(out, 0.0, args.render, progress_cb=cb)
        dt = time.perf_counter() - t0
        w, pk, priv = mem()
        print(
            f"  done in {dt:.1f}s -> {out.name} ({out.stat().st_size / 1024 / 1024:.1f} MB)  "
            f"ws={w:.1f}  peak={pk:.1f}  commit={priv:.1f}"
        )
        out.unlink(missing_ok=True)

    print("\n" + "=" * 92)
    w, pk, priv = mem()
    print(f"FINAL  ws={w:.1f} MB   peak={pk:.1f} MB   commit={priv:.1f} MB")
    print("=" * 92)


if __name__ == "__main__":
    main()
