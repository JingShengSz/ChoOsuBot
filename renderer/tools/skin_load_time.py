"""Time `load_skin` for a full .osk versus a slimmed copy of the same skin.

The render service re-loads the skin for EVERY job, so this fixed cost is paid per
render. Suisei (181 MB / 1798 files) dominates its wall-clock time; a slimmed copy
should collapse it.

    python tools/skin_load_time.py [skin-key]
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import urllib.request
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mania_render.skin import load_skin  # noqa: E402


def registered() -> dict[str, str]:
    """Ask the running service which skins it has — never hardcode paths."""
    with urllib.request.urlopen("http://127.0.0.1:8760/api/skins", timeout=30) as r:
        data = json.loads(r.read().decode())
    return {s["key"]: s["path"] for s in data["skins"]}


def timed(path: pathlib.Path) -> tuple[float, int, int]:
    t0 = time.monotonic()
    skin = load_skin(path)
    dt = time.monotonic() - t0
    n = len(skin.textures.images)
    mb = path.stat().st_size / 1048576
    return dt, n, mb


def main() -> int:
    skins = registered()
    order = [sys.argv[1]] if len(sys.argv) > 1 else list(skins)
    with tempfile.TemporaryDirectory() as td:
        for key in order:
            src = pathlib.Path(skins[key])
            dt, n, mb = timed(src)
            print(f"{key}")
            print(f"  full    {mb:8.1f} MB  {n:5d} textures  load {dt:7.2f}s")

            slim_path = pathlib.Path(td) / f"{key.replace(chr(39), '').replace(' ', '_')}_slim.osk"
            r = subprocess.run(
                [sys.executable, str(ROOT / "tools" / "slim_skin.py"), str(src), str(slim_path)],
                capture_output=True, text=True, cwd=str(ROOT),
            )
            if r.returncode != 0 or not slim_path.is_file():
                print(f"  slim    FAILED: {(r.stderr or r.stdout).strip()[:200]}")
                print()
                continue
            dt2, n2, mb2 = timed(slim_path)
            speed = dt / dt2 if dt2 > 0 else float("inf")
            print(f"  slimmed {mb2:8.1f} MB  {n2:5d} textures  load {dt2:7.2f}s   "
                  f"({speed:.1f}x faster, {mb2 / mb * 100:.1f}% of original size)")
            print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
