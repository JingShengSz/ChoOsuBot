# -*- coding: utf-8 -*-
"""
从纯白背景里抠出主体，生成带 alpha 的 PNG。

策略：只在「近白」像素上做从边框出发的泛洪。
      内部的白色（头发高光）不与边框连通，因此不会被误伤。
然后对背景掩版膨胀 1px，把主体边缘的抗锯齿白圈一起吃掉，避免留下白边。
"""
import numpy as np
from PIL import Image, ImageFilter

SRC = r"C:\Users\OwO\Downloads\恶魔娘原图手肘顶牌出框合成图.png"
OUT = r"D:\Cho Osu Bot\template\build\b_rank_alpha.png"
PREVIEW = r"D:\Cho Osu Bot\template\build\b_rank_check.png"

TOL = 38          # 距纯白多少以内算背景
DILATE = 2        # 背景掩版膨胀像素数（吃掉白边）
FEATHER = 0.6     # alpha 羽化

img = Image.open(SRC).convert("RGB")
arr = np.asarray(img).astype(np.int16)
H, W = arr.shape[:2]
print("source:", W, "x", H)

# 近白掩版
near_white = (255 - arr.min(axis=2)) <= TOL
print("near-white pixels: %.2f%%" % (100.0 * near_white.mean()))

# 从四条边出发做连通标记
bg = np.zeros((H, W), dtype=bool)
stack = []
for x in range(W):
    for y in (0, H - 1):
        if near_white[y, x] and not bg[y, x]:
            bg[y, x] = True; stack.append((y, x))
for y in range(H):
    for x in (0, W - 1):
        if near_white[y, x] and not bg[y, x]:
            bg[y, x] = True; stack.append((y, x))
print("border seeds:", len(stack))

while stack:
    y, x = stack.pop()
    for dy, dx in ((1,0),(-1,0),(0,1),(0,-1)):
        ny, nx = y+dy, x+dx
        if 0 <= ny < H and 0 <= nx < W and near_white[ny, nx] and not bg[ny, nx]:
            bg[ny, nx] = True; stack.append((ny, nx))

print("background (flooded): %.2f%%" % (100.0 * bg.mean()))

# 膨胀，把边缘抗锯齿圈一起吃掉
if DILATE > 0:
    b = bg.copy()
    for _ in range(DILATE):
        n = b.copy()
        n[1:, :] |= b[:-1, :]; n[:-1, :] |= b[1:, :]
        n[:, 1:] |= b[:, :-1]; n[:, :-1] |= b[:, 1:]
        b = n
    bg = b

alpha = np.where(bg, 0, 255).astype(np.uint8)
alpha_img = Image.fromarray(alpha, "L")
if FEATHER > 0:
    alpha_img = alpha_img.filter(ImageFilter.GaussianBlur(FEATHER))

out = Image.merge("RGBA", (
    img.getchannel("R"), img.getchannel("G"), img.getchannel("B"), alpha_img))
out.save(OUT)
print("wrote", OUT)

# 复核：边框是否还有不透明像素
a = np.asarray(alpha_img)
edges = np.concatenate([a[0, :], a[-1, :], a[:, 0], a[:, -1]])
print("border alpha  max=%d  mean=%.1f  (越接近 0 越好)" % (edges.max(), edges.mean()))
print("fully transparent: %.2f%%" % (100.0 * (a == 0).mean()))

# 在模板底色上做一张检查图
bgcol = Image.new("RGBA", out.size, (11, 13, 17, 255))
comp = Image.alpha_composite(bgcol, out)
comp.convert("RGB").resize((out.size[0]//2, out.size[1]//2)).save(PREVIEW)
print("wrote", PREVIEW)

