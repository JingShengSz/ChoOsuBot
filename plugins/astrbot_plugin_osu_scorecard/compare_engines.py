# -*- coding: utf-8 -*-
"""并排对比两套渲染引擎：PIL（新，默认）vs Photoshop（旧，设计源）。

用同一份 fixture、同一批栅格、同一张成绩，只换渲染器 —— 这样差异只可能来自
渲染实现本身，不会混进数据或素材的差别。

    python compare_engines.py            # 两个引擎都跑，出并排图 + 差异图
    python compare_engines.py --pil-only # 只跑 PIL（不用开 Photoshop）

产出（tests/out/）：
    cmp_pil.png         PIL 成品
    cmp_ps.png          Photoshop 成品
    cmp_side.png        并排（上 PIL / 下 PS）
    cmp_diff.png        像素差异放大
    cmp_zoom_*.png      关键区域 2 倍对比
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from io import BytesIO
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from PIL import Image, ImageChops  # noqa: E402

import card as cardmod  # noqa: E402
import raster  # noqa: E402
import render as rendermod  # noqa: E402

FIXTURE = HERE / "tests" / "fixture_score.json"
OUT = HERE / "tests" / "out"
TEMPLATE = Path(r"D:\Cho Osu Bot\template\osu_score_template_v1.psd")
SPEC = Path(r"D:\Cho Osu Bot\template\layer_mapping.json")
ASSETS = Path(r"D:\Cho Osu Bot\template\assets")


def build(info):
    """fixture -> (CardData, rasters)。和 main._build_rasters 同一套素材。"""
    OUT.mkdir(parents=True, exist_ok=True)
    payload = info
    score = payload.get("score") or payload
    beatmap = payload.get("beatmap") or score.get("beatmap") or {}
    beatmapset = payload.get("beatmapset") or score.get("beatmapset") or {}
    profile = payload.get("profile") or {}
    data = cardmod.build_card(score, beatmap, beatmapset, profile)

    def blank():
        return Image.new("RGBA", (1920, 1080), (0, 0, 0, 0))

    def fetch(url):
        if not url:
            return None
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "scorecard-cmp/1.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except Exception:
            return None

    rasters = []
    b = fetch(data.background_url)
    if b:
        bg = raster.cover_fit(Image.open(BytesIO(b)))
        p = OUT / "cmp_bg.png"
        bg.save(p)
        rasters.append({"layer": "beatmap_bg", "group": "bg", "path": p.as_posix()})

    a = fetch(data.avatar_url)
    if a:
        sheet = blank()
        sheet.alpha_composite(
            raster.render_avatar(Image.open(BytesIO(a)).convert("RGBA")), (922, 60))
        p = OUT / "cmp_avatar.png"
        sheet.save(p)
        rasters.append({"layer": "player_avatar", "group": "player_info", "path": p.as_posix()})

    sheet = blank()
    sheet.alpha_composite(raster.render_star_strip(data.star_value, 600), (60, 310))
    p = OUT / "cmp_strip.png"
    sheet.save(p)
    rasters.append({"layer": "star_strip", "group": "beatmap_stats", "path": p.as_posix()})

    for name, value, rng, y in (("od_bar", data.od_value, data.od_range, 520),
                                ("hp_bar", data.hp_value, data.hp_range, 588)):
        sheet = blank()
        sheet.alpha_composite(raster.render_stat_bar(value, rng[0], rng[1], width=600, height=12),
                              (60, y))
        p = OUT / f"cmp_{name}.png"
        sheet.save(p)
        rasters.append({"layer": name, "group": "beatmap_stats", "path": p.as_posix()})

    mod_sheet, _placed = raster.render_mod_row(list(data.mods or []), ASSETS / "mods" / "ready")
    p = OUT / "cmp_mods.png"
    mod_sheet.save(p)
    rasters.append({"layer": "mod_1", "group": "mods_block", "path": p.as_posix()})
    empty_p = OUT / "cmp_empty.png"
    blank().save(empty_p)
    for i in range(2, raster.MOD_SLOTS + 1):
        rasters.append({"layer": f"mod_{i}", "group": "mods_block", "path": empty_p.as_posix()})
    # 这一行是问题 2 的回归检查：非 DT/HT 时不该画倍率
    print(f"  mods = {list(data.mods or [])}   （空 = 不该出现任何 x1.5）")

    grade = (data.grade or "D").upper()
    tint = ASSETS / "rank_svg" / f"tint_{grade}.png"
    glow = ASSETS / "rank_svg" / f"glow_{grade}.png"
    if tint.is_file():
        rasters.append({"layer": "_deco_bg_gradient", "group": "bg", "path": tint.as_posix()})
    if glow.is_file():
        rasters.append({"layer": "rank_glow", "group": "signboard", "blend": True,
                        "path": glow.as_posix()})

    jobs = []
    for name, value in data.to_layers().items():
        text = "" if value is None else str(value)
        jobs.append({"name": name, "value": text,
                     "font": "YuGothic-Medium" if any(ord(c) > 0x2E7F for c in text) else None,
                     "accent": None})
    return data, grade, jobs, rasters


def crop_pair(a: Image.Image, b: Image.Image, box, label, scale=2):
    ca, cb = a.crop(box), b.crop(box)
    w, h = ca.size
    out = Image.new("RGB", (w * scale * 2 + 8, h * scale + 24), (8, 9, 12))
    from PIL import ImageDraw
    d = ImageDraw.Draw(out)
    d.text((4, 4), f"{label}   left=PIL  right=Photoshop  ({scale}x)", fill=(210, 220, 235))
    out.paste(ca.resize((w * scale, h * scale), Image.LANCZOS), (0, 24))
    out.paste(cb.resize((w * scale, h * scale), Image.LANCZOS), (w * scale + 8, 24))
    return out


def main() -> int:
    pil_only = "--pil-only" in sys.argv
    info = json.loads(FIXTURE.read_text(encoding="utf-8"))
    data, grade, jobs, rasters = build(info)

    print("\n=== 字体解析 ===")
    missing = 0
    for r in rendermod.fonts_report():
        print(f"  {'ok ' if r['found'] else 'BAD'}  {r['font']:24} {r['path'] or '(没找到)'}")
        if not r["found"]:
            missing += 1
    print(f"  缺字体: {missing}")

    spec = SPEC if SPEC.is_file() else Path(r"D:\Cho Osu Bot\template\layer_mapping.json")

    print("\n=== PIL 渲染 ===")
    r = rendermod.PilScoreCardRenderer(spec, ASSETS, OUT / "work_pil")
    pil_png = OUT / "cmp_pil.png"
    t0 = time.perf_counter()
    res = r.render(jobs, rasters, r.signboard_chain(grade), pil_png)
    pil_s = time.perf_counter() - t0
    print(f"  文字 {res['text']} 层，位图 {res['rasters']} 张，立绘 {res['signboard']}")
    print(f"  用时 {pil_s:.3f} s")

    ps_png = OUT / "cmp_ps.png"
    ps_s = None
    if not pil_only:
        print("\n=== Photoshop 渲染（对照基线）===")
        try:
            import psd
            pr = psd.ScoreCardRenderer(TEMPLATE, OUT / "work_ps", timeout_seconds=300)
            t0 = time.perf_counter()
            pres = pr.render(jobs, rasters, pr.signboard_chain(grade), ps_png)
            ps_s = time.perf_counter() - t0
            print(f"  文字 {pres.get('textApplied')} 层，位图 {len(pres.get('rasters') or [])} 张")
            print(f"  用时 {ps_s:.3f} s")
        except Exception as exc:  # noqa: BLE001
            print(f"  Photoshop 失败（{type(exc).__name__}: {exc}）—— 只比 PIL")

    a = Image.open(pil_png).convert("RGB")
    print()
    if pil_s and ps_s:
        print(f"=== 耗时对比 ===\n  PIL {pil_s:.3f}s   Photoshop {ps_s:.3f}s   加速 {ps_s/pil_s:.1f}x")

    if ps_png.is_file():
        b = Image.open(ps_png).convert("RGB")
        diff = ImageChops.difference(a, b)
        # 差异放大后入图
        d = diff.convert("L").point(lambda v: min(255, v * 4)).convert("RGB")
        d.save(OUT / "cmp_diff.png")
        bbox = diff.getbbox()
        import numpy as np
        arr = np.asarray(diff, "float32")
        print(f"\n=== 像素差异 ===")
        print(f"  平均 {arr.mean():.2f}/255   最大 {arr.max():.0f}   有差异区域 {bbox}")

        W, H = 1180, 664
        side = Image.new("RGB", (W, H * 2 + 30), (8, 9, 12))
        from PIL import ImageDraw
        dd = ImageDraw.Draw(side)
        dd.text((6, 6), "PIL (new default)", fill=(210, 220, 235))
        side.paste(a.resize((W, H), Image.LANCZOS), (0, 22))
        dd.text((6, H + 30), "Photoshop (previous)", fill=(210, 220, 235))
        side.paste(b.resize((W, H), Image.LANCZOS), (0, H + 46))
        side.save(OUT / "cmp_side.png")

        for label, box in (("left_column", (40, 40, 700, 640)),
                           ("right_column", (700, 280, 1160, 720)),
                           ("bottom_rows", (40, 690, 1160, 920)),
                           ("signboard", (1240, 0, 1920, 1080))):
            crop_pair(a, b, box, label).save(OUT / f"cmp_zoom_{label}.png")
        print(f"  写出 cmp_side.png / cmp_diff.png / cmp_zoom_*.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
