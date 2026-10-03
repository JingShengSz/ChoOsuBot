# -*- coding: utf-8 -*-
"""检查抠底残留：找出仍然不透明的「近白」像素，按连通块报告位置和大小。"""
import numpy as np
from PIL import Image

SRC = r"C:\Users\OwO\Downloads\恶魔娘原图手肘顶牌出框合成图.png"
ALPHA = r"D:\Cho Osu Bot\template\build\b_rank_alpha.png"

src = np.asarray(Image.open(SRC).convert("RGB")).astype(np.int16)
al = np.asarray(Image.open(ALPHA).convert("L"))
H, W = al.shape

# 仍然不透明、且颜色接近白 = 疑似漏掉的背景
leftover = (al > 128) & ((255 - src.min(axis=2)) <= 30)
print("image %dx%d" % (W, H))
print("leftover near-white & opaque: %d px  (%.3f%%)" % (leftover.sum(), 100.0*leftover.mean()))

# 连通块标记（4 邻域）
lab = np.zeros((H, W), dtype=np.int32)
cur = 0
comps = []
ys, xs = np.nonzero(leftover)
visited = np.zeros((H, W), dtype=bool)
import sys
sys.setrecursionlimit(10000)
for y0, x0 in zip(ys, xs):
    if visited[y0, x0]:
        continue
    cur += 1
    stack = [(y0, x0)]
    visited[y0, x0] = True
    n = 0
    miny = maxy = y0; minx = maxx = x0
    while stack:
        y, x = stack.pop()
        n += 1
        if y < miny: miny = y
        if y > maxy: maxy = y
        if x < minx: minx = x
        if x > maxx: maxx = x
        for dy, dx in ((1,0),(-1,0),(0,1),(0,-1)):
            ny, nx = y+dy, x+dx
            if 0 <= ny < H and 0 <= nx < W and leftover[ny, nx] and not visited[ny, nx]:
                visited[ny, nx] = True
                stack.append((ny, nx))
    comps.append((n, minx, miny, maxx, maxy))

comps.sort(reverse=True)
print("clusters:", len(comps), "  (top 8 by size)")
for n, x0, y0, x1, y1 in comps[:8]:
    touches = ("L" if x0 == 0 else "") + ("R" if x1 >= W-1 else "") + \
              ("T" if y0 == 0 else "") + ("B" if y1 >= H-1 else "")
    print("  size=%7d  bbox x%d..%d y%d..%d  edge:%s" % (n, x0, x1, y0, y1, touches or "-"))

# 右边缘那一段到底是什么颜色
print()
print("right edge colour samples:")
for y in range(700, 940, 40):
    px = src[y, W-1]
    print("  y=%4d  R%3d G%3d B%3d" % (y, px[0], px[1], px[2]))
