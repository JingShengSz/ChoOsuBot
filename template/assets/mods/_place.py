# -*- coding: utf-8 -*-
"""
把每个徽章预先放到 1920x1080 透明画布的正确位置上。

这样置入 Photoshop 时图层会保留绝对坐标，完全不需要 translate —— 绕开
ExtendScript 里 translate 在多层场景下位移取反的问题。
"""
import os
import numpy as np
from PIL import Image

SRC = r"D:\DeepSeek Harness\workspace1\_mods\ready"
OUT = r"D:\DeepSeek Harness\workspace1\_mods\placed"
os.makedirs(OUT, exist_ok=True)

CANVAS = (1920, 1080)
BADGE_H, PITCH, X0, Y0 = 48, 110, 60, 842
MODS = [("mod_1", "mod_hd"), ("mod_2", "mod_dt"), ("mod_3", "mod_hr"),
        ("mod_4", "mod_fl"), ("mod_5", "mod_ez"), ("mod_6", "mod_nf")]

for i, (slot, asset) in enumerate(MODS):
    im = Image.open(os.path.join(SRC, asset + ".png")).convert("RGBA")
    w = round(im.width * BADGE_H / im.height)
    im = im.resize((w, BADGE_H), Image.LANCZOS)

    cx = X0 + i * PITCH + PITCH // 2
    cy = Y0 + BADGE_H // 2
    x = round(cx - w / 2)
    y = round(cy - BADGE_H / 2)

    canvas = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    canvas.alpha_composite(im, (x, y))
    canvas.save(os.path.join(OUT, slot + ".png"))

    # 校验：合成后内容的实际包围盒
    A = np.asarray(canvas)[:, :, 3]
    ys, xs = np.nonzero(A > 8)
    print("%-6s <- %-8s  %3dx%-3d  placed x%4d..%4d y%4d..%4d   centre=(%.1f,%.1f) want=(%d,%d)" % (
        slot, asset, w, BADGE_H, xs.min(), xs.max(), ys.min(), ys.max(),
        (xs.min()+xs.max())/2, (ys.min()+ys.max())/2, cx, cy))

print()
print("wrote to", OUT)
