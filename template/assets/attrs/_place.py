# -*- coding: utf-8 -*-
"""
把三张属性图标预先合成到 1920x1080 透明画布上，位置对齐到各行的
「数值文本墨迹中心」。置入 PS 时图层保留绝对坐标，不需要 translate。
"""
import os
import numpy as np
from PIL import Image

SRC = r"D:\DeepSeek Harness\workspace1\_attrs"
OUT = r"D:\DeepSeek Harness\workspace1\_attrs\placed"
os.makedirs(OUT, exist_ok=True)

CANVAS = (1920, 1080)
BOX = 40          # 图标框边长；源图墨迹占 64% -> 实际墨迹约 26px

# 对齐目标：数值文本墨迹的垂直中心（从文档查到的真实值）
JOBS = [
    ("_deco_attr_bpm", "bpm.png", 76, 422),
    ("_deco_attr_od",  "od.png",  76, 490),
    ("_deco_attr_hp",  "hp.png",  76, 558),
]

for name, src, cx, cy in JOBS:
    im = Image.open(os.path.join(SRC, src)).convert("RGBA")
    im = im.resize((BOX, BOX), Image.LANCZOS)

    canvas = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    canvas.alpha_composite(im, (round(cx - BOX/2), round(cy - BOX/2)))
    canvas.save(os.path.join(OUT, name + ".png"))

    A = np.asarray(canvas)[:, :, 3]
    ys, xs = np.nonzero(A > 8)
    print("%-18s <- %-8s box %dx%d  ink x%d..%d y%d..%d (centre %.1f,%.1f)  want (%.1f,%.1f)" % (
        name, src, BOX, BOX, xs.min(), xs.max(), ys.min(), ys.max(),
        (xs.min()+xs.max())/2, (ys.min()+ys.max())/2, cx, cy))

print()
print("wrote to", OUT)
