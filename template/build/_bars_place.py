# -*- coding: utf-8 -*-
"""
把 OD / HP 进度条预先合成到 1920x1080 透明画布的正确位置上。
（和 mod 徽章同一套路：置入 PS 时图层保留绝对坐标，不需要 translate）
"""
import os
import numpy as np
from PIL import Image, ImageDraw

OUT = r"D:\Cho Osu Bot\template\build\bars_placed"
os.makedirs(OUT, exist_ok=True)

BW, BH, R = 600, 12, 6          # 条宽、条高、圆角
TRACK = (46, 53, 67, 255)       # #2E3543
TICK = (11, 13, 17, 90)
X0 = 60

def bar_png(value, lo, hi, color_hex):
    """画一条进度条，返回 (RGBA 图, 填充比例)"""
    img = Image.new("RGBA", (BW, BH), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, BW - 1, BH - 1], radius=R, fill=TRACK)

    frac = min(max((value - lo) / (hi - lo), 0.0), 1.0)
    bipolar = lo < 0 < hi
    x_zero = ((0 - lo) / (hi - lo) * BW) if bipolar else 0.0
    x_val = frac * BW
    a, b = sorted((x_zero, x_val))

    if b - a > 0.4:
        col = tuple(int(color_hex[i:i+2], 16) for i in (1, 3, 5)) + (255,)
        fill = Image.new("RGBA", (BW, BH), (0, 0, 0, 0))
        ImageDraw.Draw(fill).rounded_rectangle([0, 0, BW - 1, BH - 1], radius=R, fill=col)
        mask = Image.new("L", (BW, BH), 0)
        ImageDraw.Draw(mask).rectangle([int(round(a)), 0, int(round(b)) - 1, BH - 1], fill=255)
        img.alpha_composite(Image.composite(fill, Image.new("RGBA", (BW, BH), (0,0,0,0)), mask))

    # 刻度线：每隔 1 个单位
    t = np.ceil(lo)
    while t < hi:
        if abs(t) > 1e-9:
            x = (t - lo) / (hi - lo) * BW
            if 1 < x < BW - 1:
                d.rectangle([x - 0.5, 0, x + 0.5, BH - 1], fill=TICK)
        t += 1
    return img, frac

JOBS = [
    # 名字, 数值, 量程下限, 量程上限, 颜色, 顶边 y
    # OD 行实际占 477..510，HP 行实际占 545..578（查过文档，不是估的）
    ("od_bar", 9.0, 0, 10, "#ffa022", 520),
    ("hp_bar", 6.0, 0, 10, "#f29183", 588),
]

for name, val, lo, hi, colr, top in JOBS:
    bimg, frac = bar_png(val, lo, hi, colr)
    canvas = Image.new("RGBA", (1920, 1080), (0, 0, 0, 0))
    canvas.alpha_composite(bimg, (X0, top))
    canvas.save(os.path.join(OUT, name + ".png"))

    A = np.asarray(canvas)[:, :, 3]
    ys, xs = np.nonzero(A > 8)
    print("%-8s value=%-5s fill=%3d%%  colour=%s  placed x%d..%d y%d..%d" % (
        name, val, round(frac*100), colr, xs.min(), xs.max(), ys.min(), ys.max()))

print()
print("wrote to", OUT)
