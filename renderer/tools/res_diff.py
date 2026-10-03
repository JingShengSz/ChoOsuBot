"""Compare a native 720p render against a 1080p render downscaled to 720p.

    python tools/res_diff.py

If 720p is what the renderer claims -- an ffmpeg downscale of the same 1080p
frame -- the two frames must agree to within resampling error. A large or
structured difference would mean 720p takes a different layout path.
"""
from __future__ import annotations

import pathlib

from PIL import Image, ImageChops

HERE = pathlib.Path(__file__).resolve().parents[1] / "out" / "res_compare"
SMALL = HERE / "1280x720.png"
BIG = HERE / "1920x1080.png"


def main() -> int:
    a = Image.open(SMALL).convert("RGB")
    b = Image.open(BIG).convert("RGB").resize(a.size, Image.Resampling.BICUBIC)
    print(f"native 720p : {a.size}")
    print(f"1080p->720p : {b.size}")

    diff = ImageChops.difference(a, b)
    hist = diff.convert("L").histogram()
    total = sum(hist)
    mean = sum(i * n for i, n in enumerate(hist)) / total
    over8 = sum(n for i, n in enumerate(hist) if i > 8) / total
    over32 = sum(n for i, n in enumerate(hist) if i > 32) / total
    print(f"\nmean abs diff : {mean:.2f} / 255")
    print(f"pixels >8/255  : {over8 * 100:.3f} %")
    print(f"pixels >32/255 : {over32 * 100:.3f} %")

    diff.convert("L").point(lambda v: min(255, v * 6)).save(HERE / "diff_x6.png")
    print(f"\nwrote {HERE / 'diff_x6.png'} (difference amplified 6x)")

    verdict = "SAME LAYOUT (only resampling error)" if mean < 4 else "DIFFERENT LAYOUT"
    print(f"\nVERDICT: {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
