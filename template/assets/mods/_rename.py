# -*- coding: utf-8 -*-
"""把交付的 10 张 mod 图按模组名重命名，并量出每张徽章本体的实际包围盒。"""
import os, glob
import numpy as np
from PIL import Image

SRC = r"D:\DeepSeek Harness\workspace1\_mods"
MAP = {1:"hd", 2:"dt", 3:"ht", 4:"hr", 5:"ez", 6:"fl", 7:"nf", 8:"so", 9:"sd", 10:"pf"}

files = {}
for p in glob.glob(os.path.join(SRC, "*.png")):
    b = os.path.basename(p)
    if b.startswith("_") or b == "w.png":
        continue
    idx = int(b.rsplit("-", 1)[-1].split(".")[0])
    files[idx] = p

print(" idx -> name     | canvas     | badge bbox                | aspect")
print("-" * 78)
for i in sorted(files):
    p = files[i]
    im = Image.open(p).convert("RGBA")
    A = np.asarray(im)[:, :, 3]
    ys, xs = np.nonzero(A > 8)
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    w, h = x1-x0+1, y1-y0+1

    new = os.path.join(SRC, "mod_%s.png" % MAP[i])
    im.save(new)
    if os.path.abspath(new) != os.path.abspath(p):
        os.remove(p)

    print(" %3d -> %-6s | %4dx%-4d | x%4d..%4d y%4d..%4d (%4dx%4d) | %.2f" % (
        i, MAP[i], im.size[0], im.size[1], x0, x1, y0, y1, w, h, w/h))

print()
print("remaining files:")
for p in sorted(glob.glob(os.path.join(SRC, "*.png"))):
    print("   ", os.path.basename(p))
