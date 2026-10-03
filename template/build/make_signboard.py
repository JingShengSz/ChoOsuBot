"""绿幕立绘 -> 模板 signboard 图层，一步到位。

输入：任意一张立绘（绿幕底 或 已经抠好的透明底 PNG）
输出：1920x1080 透明底 PNG，角色宽度 643px、底边贴 y=1080、右边贴 x=1920
      —— 就是模板里 signboard_s / signboard_b 的落位规则。

用法：
    python make_signboard.py 输入.png XH
    python make_signboard.py 输入.png SS --key green --tol 46 --despill 0.75
    python make_signboard.py 输入.png A  --preview        # 顺便出一张深色底预览

绿幕抠像参数一般不用动。抠完看 alpha 占比：
    正常立绘 20%~60%；<5% 说明颜色判定错了；>85% 说明绿幕没抠干净。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image

CANVAS = (1920, 1080)
TARGET_W = 643          # 立绘宽度，模板既定
ANCHOR_X = 1920         # 右边贴齐画布右缘
ANCHOR_BOTTOM = 1080    # 底边贴齐画布下缘
BG_DARK = (14, 17, 24)


def key_green(img: Image.Image, tol: int, despill: float) -> Image.Image:
    """把绿幕抠成透明，并压掉边缘的绿色溢出。"""
    rgb = np.asarray(img.convert("RGB"), np.float32)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]

    # 绿幕判定：绿通道明显高于红和蓝，且整体够亮
    greenness = g - np.maximum(r, b)
    mask = greenness > tol

    alpha = np.where(mask, 0, 255).astype(np.uint8)

    # 半透明边缘：在阈值附近做一个渐变带，避免锯齿
    band = np.clip((greenness - (tol - 28)) / 28.0, 0, 1)
    edge = (~mask) & (band > 0) & (band < 1)
    alpha[edge] = (255 * (1 - band[edge])).astype(np.uint8)

    out = rgb.copy()
    if despill > 0:
        # 只压绿色通道里"多出来"的那部分，保持亮度
        spill = np.clip(g - np.maximum(r, b), 0, None)
        out[..., 1] = g - spill * despill
        # 边缘一圈额外去绿
        halo = alpha < 255
        out[..., 1][halo] = np.minimum(out[..., 1][halo], np.maximum(out[..., 0][halo], out[..., 2][halo]))

    rgba = np.dstack([np.clip(out, 0, 255), alpha]).astype(np.uint8)
    return Image.fromarray(rgba, "RGBA")


def trim(img: Image.Image) -> Image.Image:
    a = np.asarray(img)[:, :, 3]
    ys, xs = np.where(a > 8)
    if len(xs) == 0:
        raise SystemExit("抠完是空的 —— alpha 全 0，检查 --key / --tol")
    return img.crop((int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1))


def compose(img: Image.Image) -> tuple[Image.Image, dict]:
    w, h = img.size
    scale = TARGET_W / w
    nw, nh = TARGET_W, max(1, round(h * scale))
    if nh > CANVAS[1]:
        # 太高就改成按高度贴，宽度相应变窄（保持比例，底边对齐）
        scale = CANVAS[1] / h
        nh, nw = CANVAS[1], max(1, round(w * scale))
    rs = img.resize((nw, nh), Image.LANCZOS)

    x = ANCHOR_X - nw
    y = ANCHOR_BOTTOM - nh
    canvas = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    canvas.alpha_composite(rs, (x, y))
    return canvas, {"src": (w, h), "placed": (nw, nh), "at": (x, y),
                    "right": x + nw, "bottom": y + nh}


def stats(img: Image.Image) -> dict:
    a = np.asarray(img)[:, :, 3]
    return {"opaque_pct": round(float((a > 200).mean() * 100), 2),
            "semi_pct": round(float(((a > 8) & (a <= 200)).mean() * 100), 2),
            "empty_pct": round(float((a <= 8).mean() * 100), 2)}


def preview(sheet: Image.Image, path: Path):
    bg = Image.new("RGBA", CANVAS, BG_DARK + (255,))
    bg.alpha_composite(sheet)
    bg.convert("RGB").resize((1180, 664), Image.LANCZOS).save(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("rank")
    ap.add_argument("--key", choices=["green", "none"], default="green")
    ap.add_argument("--tol", type=int, default=46)
    ap.add_argument("--despill", type=float, default=0.75)
    ap.add_argument("--outdir", default=None)
    ap.add_argument("--preview", action="store_true")
    a = ap.parse_args()

    src = Path(a.source)
    if not src.is_file():
        raise SystemExit(f"找不到 {src}")
    outdir = Path(a.outdir) if a.outdir else src.parent
    outdir.mkdir(parents=True, exist_ok=True)

    img = Image.open(src)
    img = img.convert("RGBA") if a.key == "none" else key_green(img, a.tol, a.despill)
    print(f"读入      {src.name}  {Image.open(src).size}")

    t = trim(img)
    print(f"裁到墨迹  {t.size}")
    print(f"alpha     {stats(t)}")

    sheet, info = compose(t)
    print(f"落位      {info['placed'][0]}x{info['placed'][1]} @ ({info['at'][0]},{info['at'][1]})"
          f"  右边={info['right']} 底边={info['bottom']}")

    out = outdir / f"signboard_{a.rank}.png"
    sheet.save(out)
    print(f"写出      {out}")

    if a.preview:
        preview(sheet, outdir / f"signboard_{a.rank}_preview.png")
        print(f"预览      {outdir / f'signboard_{a.rank}_preview.png'}")


if __name__ == "__main__":
    sys.exit(main())
