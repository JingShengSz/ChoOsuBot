# -*- coding: utf-8 -*-
"""复制三张属性图标到工作区，并做两种尺寸的检查图（512 原大小 + 32px 实际显示）。"""
import os, shutil
import numpy as np
from PIL import Image, ImageDraw, ImageFont

SRC = r"C:\Users\OwO\Documents\Codex\2026-10-02\referenced-chatgpt-conversation-this-is-an\outputs"
DST = r"D:\DeepSeek Harness\workspace1\_attrs"
os.makedirs(DST, exist_ok=True)

names = ["bpm.png", "od.png", "hp.png"]
for n in names:
    shutil.copy2(os.path.join(SRC, n), os.path.join(DST, n))

print("idx | file    | canvas    | 墨迹 bbox                 | 占画布 | 缩到32px")
print("-" * 84)
info = []
for n in names:
    im = Image.open(os.path.join(DST, n)).convert("RGBA")
    A = np.asarray(im)[:, :, 3]
    ys, xs = np.nonzero(A > 8)
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    w, h = x1-x0+1, y1-y0+1
    big = max(w, h)
    at32 = big / 512 * 32
    print("%-3s | %-7s | %-9s | x%3d..%3d y%3d..%3d (%3dx%-3d) | %4.1f%%  | %.1fpx" % (
        names.index(n)+1, n, "%dx%d" % im.size, x0, x1, y0, y1, w, h,
        big/512*100, at32))
    info.append((n, im))

# 检查图：深色底，左列 512 原大小（缩到 128），右列 32px 实际尺寸放大 4 倍显示
PAD, CW, CH = 20, 150, 150
sheet = Image.new("RGB", (PAD*3 + CW*2 + 260, PAD + len(info)*(CH+PAD)), (11, 13, 17))
d = ImageDraw.Draw(sheet)
try: font = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 18)
except Exception: font = ImageFont.load_default()

for i, (n, im) in enumerate(info):
    y = PAD + i*(CH+PAD)
    # 缩略
    t = im.copy(); t.thumbnail((CH-20, CH-20), Image.LANCZOS)
    sheet.paste(t, (PAD + (CW-t.width)//2, y + (CH-t.height)//2), t)
    # 32px 实际尺寸，放大 4 倍看清楚
    small = im.resize((32, 32), Image.LANCZOS)
    big32 = small.resize((128, 128), Image.NEAREST)
    sheet.paste(big32, (PAD*2 + CW, y + (CH-128)//2), big32)
    d.text((PAD*2 + CW + 140, y + 60), "%s   512px" % n, fill=(160,170,190), font=font)
    d.text((PAD*2 + CW + 140, y + 86), "-> 32px (x4)" % (), fill=(110,120,140), font=font)

sheet.save(os.path.join(DST, "_check.png"))
print()
print("wrote", os.path.join(DST, "_check.png"), sheet.size)
