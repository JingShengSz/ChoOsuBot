# -*- coding: utf-8 -*-
"""把 _mods 里的 mod 图拼成一张联系表，并报告每张的 alpha 情况。"""
import os, glob
import numpy as np
from PIL import Image, ImageDraw, ImageFont

SRC = r"D:\DeepSeek Harness\workspace1\_mods"
OUT = os.path.join(SRC, "_contact.png")

files = sorted([p for p in glob.glob(os.path.join(SRC, "*.png"))
                if os.path.basename(p) not in ("_contact.png", "w.png")],
               key=lambda p: int(p.rsplit("-", 1)[-1].split(".")[0]))

print("found %d files" % len(files))
print()
print(" idx | file tail | size        | alpha<10  alpha>245  partial")
imgs = []
for i, p in enumerate(files, 1):
    im = Image.open(p)
    a = np.asarray(im)
    if a.ndim == 3 and a.shape[2] == 4:
        A = a[:, :, 3]
        t = 100.0*(A < 10).mean(); o = 100.0*(A > 245).mean()
        pa = 100.0*((A >= 10) & (A <= 245)).mean()
    else:
        t = o = pa = float("nan")
    print(" %3d | %-9s | %-11s | %7.2f%%  %8.2f%%  %6.2f%%" % (
        i, os.path.basename(p)[-12:], "%dx%d" % im.size, t, o, pa))
    imgs.append((i, im.convert("RGBA")))

# 联系表：5 列 x 2 行，深色底
CELL, PAD, LBL = 230, 14, 26
COLS = 5
ROWS = (len(imgs) + COLS - 1) // COLS
W = COLS * (CELL + PAD) + PAD
H = ROWS * (CELL + PAD + LBL) + PAD
sheet = Image.new("RGB", (W, H), (11, 13, 17))
d = ImageDraw.Draw(sheet)
try:
    font = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 18)
except Exception:
    font = ImageFont.load_default()

for n, (i, im) in enumerate(imgs):
    c, r = n % COLS, n // COLS
    x = PAD + c * (CELL + PAD)
    y = PAD + r * (CELL + PAD + LBL)
    thumb = im.copy()
    thumb.thumbnail((CELL, CELL), Image.LANCZOS)
    sheet.paste(thumb, (x + (CELL - thumb.width)//2, y + (CELL - thumb.height)//2), thumb)
    d.text((x + 4, y + CELL + 2), "  #%d" % i, fill=(180, 190, 210), font=font)

sheet.save(OUT)
print()
print("wrote", OUT, sheet.size)
