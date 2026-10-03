# -*- coding: utf-8 -*-
"""
osu! 成绩图图标生成器（脚本版 · 确定性出图）

产出两组：
  1. 判定图标 6 张  count_max / count_300 / count_200 / count_100 / count_50 / count_miss
  2. mod 徽章  8 张  mod_1(HD) ... mod_8(SO)

规格：512x512 PNG，真透明底，竖向双色渐变，2% 画布宽近黑描边，上边缘高光线。
所有参数集中在 CONFIG 区，改色值 / 改字体后直接重跑即可。
"""

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

# ---------------------------------------------------------------- CONFIG ----
S = 512                 # 输出边长
SS = 4                  # 超采样倍数（抗锯齿用）
BIG = S * SS            # 工作尺度 2048

OUTLINE_RATIO = 0.02    # 描边 = 画布宽度 2% -> 10.24px @512
OUTLINE_COLOR = (12, 10, 9, 255)
MARGIN_RATIO = 0.10     # 四周内边距 10%

GLYPH_HEIGHT_RATIO = 0.40   # 判定图标：以「字高」为统一基准，保证 6 张视觉重量一致
BADGE_SIZE_RATIO = 0.80     # 徽章外框边长 = 画布 80%（含描边）
BADGE_RADIUS_RATIO = 0.20   # 圆角 = 徽章宽度 20%
BADGE_TEXT_RATIO = 0.60     # 徽章字母宽度 = 徽章宽度 60%

HILITE_RATIO = 0.020    # 上边缘高光条带厚度（画布比例）
HILITE_BLEND = 0.80     # 高光向白色混合的比例
HILITE_BLUR = 6         # 高光边缘柔化（工作尺度像素）

FONT_PATH = "C:/Windows/Fonts/ariblk.ttf"   # Arial Black：重字重、圆角端点，最贴 osu! 原味

OUT_DIR = Path(r"D:\Cho Osu Bot\template\build\out")

JUDGEMENTS = [
    # (文件名, 字符, 浅色, 深色)
    ("count_max",  "MAX", (0xFF, 0xE0, 0x7A), (0xFF, 0xCC, 0x22)),
    ("count_300",  "300", (0x8E, 0xCB, 0xF0), (0x4F, 0xA3, 0xE3)),
    ("count_200",  "200", (0x9A, 0xD4, 0xE8), (0x5F, 0xB4, 0xCC)),
    ("count_100",  "100", (0xB5, 0xDC, 0x77), (0x8C, 0xC6, 0x3F)),
    ("count_50",   "50",  (0xED, 0xC7, 0x7A), (0xD9, 0xA4, 0x41)),
    ("count_miss", "X",   (0xF0, 0x90, 0x90), (0xE4, 0x5B, 0x5B)),
]

MODS = [
    # (图层名, 字母, 浅色, 深色, 模组全称)
    ("mod_1", "HD", (0xE8, 0xD2, 0x7A), (0xC9, 0xA2, 0x27), "Hidden"),
    ("mod_2", "DT", (0xB3, 0x9A, 0xE0), (0x7E, 0x57, 0xC2), "Double Time"),
    ("mod_3", "HR", (0xF0, 0x90, 0x90), (0xD0, 0x48, 0x3F), "Hard Rock"),
    ("mod_4", "FL", (0x8A, 0x8F, 0xD0), (0x4A, 0x4F, 0xA8), "Flashlight"),
    ("mod_5", "EZ", (0x9A, 0xD8, 0xA0), (0x5F, 0xAE, 0x6A), "Easy"),
    ("mod_6", "NF", (0xA8, 0xC4, 0xD8), (0x6E, 0x93, 0xAE), "No Fail"),
    ("mod_7", "HT", (0xA0, 0xC8, 0xE0), (0x5E, 0x8F, 0xB0), "Half Time"),
    ("mod_8", "SO", (0xC8, 0xB8, 0xA0), (0x8A, 0x76, 0x60), "Spun Out"),
]
# ------------------------------------------------------------- 工具函数 ----


def vertical_gradient(size: int, top: tuple, bottom: tuple) -> Image.Image:
    """生成 size×size 的竖向线性渐变 RGB 图。"""
    t = np.linspace(0.0, 1.0, size, dtype=np.float64)[:, None]
    a = np.array(top, dtype=np.float64)[None, :]
    b = np.array(bottom, dtype=np.float64)[None, :]
    row = a * (1.0 - t) + b * t                      # (size, 3)
    arr = np.repeat(row[:, None, :], size, axis=1)   # (size, size, 3)
    return Image.fromarray(arr.astype(np.uint8), "RGB")


def fit_font(text: str, max_w: int, max_h: int) -> ImageFont.FreeTypeFont:
    """二分查找能同时装进 max_w × max_h 的最大字号。"""
    lo, hi, best = 8, BIG, 8
    while lo <= hi:
        mid = (lo + hi) // 2
        font = ImageFont.truetype(FONT_PATH, mid)
        x0, y0, x1, y1 = font.getbbox(text)
        if (x1 - x0) <= max_w and (y1 - y0) <= max_h:
            best, lo = mid, mid + 1
        else:
            hi = mid - 1
    return ImageFont.truetype(FONT_PATH, best)


def glyph_masks(text: str, max_w: int, max_h: int):
    """返回 (填充 alpha 掩版, 描边 alpha 掩版)，均为 BIG×BIG 的 L 图。"""
    font = fit_font(text, max_w, max_h)
    # 描边是居中描边：一半在内一半在外，被内层渐变盖掉一半，
    # 所以 stroke_width 取 2 倍才能得到 2% 画布的「外」描边。
    stroke = int(round(OUTLINE_RATIO * BIG * 2))

    fill = Image.new("L", (BIG, BIG), 0)
    ImageDraw.Draw(fill).text((BIG / 2, BIG / 2), text, font=font,
                              fill=255, anchor="mm")

    edge = Image.new("L", (BIG, BIG), 0)
    ImageDraw.Draw(edge).text((BIG / 2, BIG / 2), text, font=font,
                              fill=255, stroke_width=stroke,
                              stroke_fill=255, anchor="mm")
    return fill, edge


def top_highlight(fill_mask: Image.Image) -> Image.Image:
    """取字形上边缘的一条细带，做高光线。"""
    band_px = int(round(HILITE_RATIO * BIG))
    shifted = Image.new("L", (BIG, BIG), 0)
    shifted.paste(fill_mask, (0, band_px))          # 整体下移
    a = np.asarray(fill_mask, dtype=np.int16)
    b = np.asarray(shifted, dtype=np.int16)
    diff = np.clip(a - b, 0, 255).astype(np.uint8)  # 顶部露出的条带
    return Image.fromarray(diff, "L").filter(ImageFilter.GaussianBlur(HILITE_BLUR))


def compose(fill_mask, edge_mask, top_color, bottom_color) -> Image.Image:
    """叠出最终 RGBA：描边 -> 渐变 -> 上边缘高光。"""
    canvas = Image.new("RGBA", (BIG, BIG), (0, 0, 0, 0))

    edge_layer = Image.new("RGBA", (BIG, BIG), OUTLINE_COLOR)
    canvas.paste(edge_layer, (0, 0), edge_mask)

    grad = vertical_gradient(BIG, top_color, bottom_color).convert("RGBA")
    canvas.paste(grad, (0, 0), fill_mask)

    light = tuple(int(c + (255 - c) * HILITE_BLEND) for c in top_color)
    hilite = Image.new("RGBA", (BIG, BIG), light + (255,))
    canvas.paste(hilite, (0, 0), top_highlight(fill_mask))

    return canvas.resize((S, S), Image.LANCZOS)


# --------------------------------------------------------------- 判定图标 ----


def make_judgement(name: str, text: str, top_color, bottom_color):
    box = int(round(S * (1 - 2 * MARGIN_RATIO))) * SS      # 0.8*S 内容区
    h_max = int(round(GLYPH_HEIGHT_RATIO * S)) * SS        # 统一字高基准
    fill_mask, edge_mask = glyph_masks(text, box, h_max)
    img = compose(fill_mask, edge_mask, top_color, bottom_color)
    img.save(OUT_DIR / f"{name}.png")
    return img


# -------------------------------------------------------------- mod 徽章 ----


def rounded_mask(size: int, radius: int, ox: int, oy: int) -> Image.Image:
    m = Image.new("L", (BIG, BIG), 0)
    ImageDraw.Draw(m).rounded_rectangle(
        [ox, oy, ox + size, oy + size], radius=radius, fill=255)
    return m


def make_badge(name: str, letters: str, top_color, bottom_color):
    outer = int(round(S * BADGE_SIZE_RATIO)) * SS
    stroke = int(round(OUTLINE_RATIO * S)) * SS
    inner = outer - 2 * stroke
    radius_o = int(round(outer * BADGE_RADIUS_RATIO))
    radius_i = max(radius_o - stroke, 1)
    off = (BIG - outer) // 2
    off_i = (BIG - inner) // 2

    canvas = Image.new("RGBA", (BIG, BIG), (0, 0, 0, 0))

    # 描边层：外框整体填近黑
    canvas.paste(Image.new("RGBA", (BIG, BIG), OUTLINE_COLOR),
                 (0, 0), rounded_mask(outer, radius_o, off, off))

    # 渐变内框
    grad = vertical_gradient(BIG, top_color, bottom_color).convert("RGBA")
    inner_mask = rounded_mask(inner, radius_i, off_i, off_i)
    canvas.paste(grad, (0, 0), inner_mask)

    # 徽章内高光：沿内框上沿一条细带
    band = int(round(HILITE_RATIO * BIG * 0.6))
    shifted = Image.new("L", (BIG, BIG), 0)
    shifted.paste(inner_mask, (0, band))
    a = np.asarray(inner_mask, dtype=np.int16)
    b = np.asarray(shifted, dtype=np.int16)
    diff = np.clip(a - b, 0, 255).astype(np.uint8)
    hl = Image.fromarray(diff, "L").filter(ImageFilter.GaussianBlur(HILITE_BLUR))
    canvas.paste(Image.new("RGBA", (BIG, BIG), (255, 255, 255, 120)), (0, 0), hl)

    # 字母：纯白 + 细深描边，宽度占徽章 60%
    target_w = int(round(outer * BADGE_TEXT_RATIO))
    font = fit_font(letters, target_w, int(round(inner * 0.62)))
    txt = Image.new("L", (BIG, BIG), 0)
    ImageDraw.Draw(txt).text((BIG / 2, BIG / 2), letters, font=font,
                             fill=255, anchor="mm")
    dark = Image.new("L", (BIG, BIG), 0)
    ImageDraw.Draw(dark).text((BIG / 2, BIG / 2), letters, font=font,
                              fill=255, stroke_width=int(stroke * 0.34),
                              stroke_fill=255, anchor="mm")
    canvas.paste(Image.new("RGBA", (BIG, BIG), OUTLINE_COLOR), (0, 0), dark)
    canvas.paste(Image.new("RGBA", (BIG, BIG), (255, 255, 255, 255)), (0, 0), txt)

    img = canvas.resize((S, S), Image.LANCZOS)
    img.save(OUT_DIR / f"{name}.png")
    return img


# ------------------------------------------------------------------ 预览 ----


def build_preview(items, title, path, cell=96, pad=18, thumb=40):
    """左：512 原尺寸缩略；右：真实 40px，分别叠在深/浅底上模拟成绩图环境。"""
    n = len(items)
    col_w = cell + pad * 2
    w = pad * 2 + col_w * n
    h = pad * 5 + cell + thumb * 2 + 70
    sheet = Image.new("RGB", (w, h), (34, 36, 42))
    d = ImageDraw.Draw(sheet)
    d.text((pad, pad), title, font=ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 22),
           fill=(235, 235, 235))

    y = pad * 2 + 26
    for i, (name, img) in enumerate(items):
        x = pad + i * col_w
        thumb_big = img.resize((cell, cell), Image.LANCZOS)
        sheet.paste(thumb_big, (x, y), thumb_big)
        d.text((x, y + cell + 6), name,
               font=ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 15),
               fill=(190, 190, 190))

    ty = y + cell + 34
    small = [(n, im.resize((thumb, thumb), Image.LANCZOS)) for n, im in items]

    rows = [((24, 25, 28), "40px on dark"), ((206, 190, 214), "40px on light")]
    for row, (bg, label) in enumerate(rows):
        ry = ty + row * (thumb + 14)
        d.rectangle([pad - 4, ry - 4, pad - 4 + col_w * n, ry + thumb + 4], fill=bg)
        for i, (_, im) in enumerate(small):
            sheet.paste(im.convert("RGBA"), (pad + i * col_w, ry), im)
        d.text((pad + col_w * n + 8, ry + 8), label,
               font=ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 15),
               fill=(200, 200, 200))

    sheet.save(path)


# -------------------------------------------------------------------- main ----


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    j_items = []
    for name, text, top_c, bot_c in JUDGEMENTS:
        j_items.append((name, make_judgement(name, text, top_c, bot_c)))
    print("判定图标:", ", ".join(n for n, _ in j_items))

    m_items = []
    for name, letters, top_c, bot_c, full in MODS:
        m_items.append((name, make_badge(name, letters, top_c, bot_c)))
    print("mod 徽章:", ", ".join(f"{m[0]}={m[1]}" for m in MODS))

    build_preview(j_items, "osu! judgement icons  ·  512px source / 40px actual",
                  OUT_DIR.parent / "preview_judgement.png")
    build_preview(m_items, "osu! mod badges  ·  512px source / 40px actual",
                  OUT_DIR.parent / "preview_mods.png")
    print("预览图已输出")


if __name__ == "__main__":
    main()
