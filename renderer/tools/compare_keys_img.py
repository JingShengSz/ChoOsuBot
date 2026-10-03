"""Stack the WebGL and Python renders of the same frame for direct comparison.

    python tools/compare_keys_img.py

Top strip  = WebGL page render (what the user says looks right)
Bottom strip = Python API render (what the user says is stretched)
Both cropped to the same receptor band of the 1920x1080 frame.
"""
from __future__ import annotations

import pathlib

from PIL import Image, ImageDraw

HERE = pathlib.Path(__file__).resolve().parents[1] / "out" / "res_compare"

# Receptor band: judgement line sits at y=972, so take a strip around it.
X0, Y0, W, H = 500, 840, 920, 240


def strip(path: pathlib.Path, label: str) -> Image.Image:
    img = Image.open(path).convert("RGB")
    assert img.size == (1920, 1080), f"{path.name} is {img.size}"
    crop = img.crop((X0, Y0, X0 + W, Y0 + H))
    out = Image.new("RGB", (W, H + 26), (24, 30, 38))
    out.paste(crop, (0, 26))
    ImageDraw.Draw(out).text((8, 7), label, fill=(255, 210, 90))
    return out


def main() -> int:
    top = strip(HERE / "webgl.png", "WEBGL (page) - receptors: circles, bottom-anchored")
    bot = strip(HERE / "1920x1080.png", "PYTHON (api) - receptors: ???")
    out = Image.new("RGB", (W, top.height + bot.height), (24, 30, 38))
    out.paste(top, (0, 0))
    out.paste(bot, (0, top.height))
    dest = HERE / "compare_keys.png"
    out.save(dest)
    print(f"wrote {dest}  ({out.width}x{out.height})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
