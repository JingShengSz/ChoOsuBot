# -*- coding: utf-8 -*-
"""裁掉画布空白，按统一高度重采样，输出可直接置入模板的徽章素材。"""
import os, glob
import numpy as np
from PIL import Image

SRC = r"D:\DeepSeek Harness\workspace1\_mods"
OUT = os.path.join(SRC, "ready")
os.makedirs(OUT, exist_ok=True)

TARGET_H = 50          # 模板里的显示高度
TARGET_H_BIG = 200     # 同时存一份大图备用

print("name     | cropped     | -> %dpx tall" % TARGET_H)
print("-" * 52)
for p in sorted(glob.glob(os.path.join(SRC, "mod_*.png"))):
    name = os.path.basename(p)[:-4]
    im = Image.open(p).convert("RGBA")
    A = np.asarray(im)[:, :, 3]
    ys, xs = np.nonzero(A > 8)
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    crop = im.crop((x0, y0, x1 + 1, y1 + 1))

    for tag, h in (("", TARGET_H), ("@4x", TARGET_H_BIG)):
        w = max(1, round(crop.width * h / crop.height))
        r = crop.resize((w, h), Image.LANCZOS)
        r.save(os.path.join(OUT, "%s%s.png" % (name, tag)))

    w = round(crop.width * TARGET_H / crop.height)
    print("%-8s | %4dx%-4d -> %4dx%-3d" % (name, crop.width, crop.height, w, TARGET_H))

print()
print("ready/ 内容:")
for p in sorted(glob.glob(os.path.join(OUT, "*.png"))):
    im = Image.open(p)
    print("   %-16s %dx%d" % (os.path.basename(p), im.size[0], im.size[1]))
