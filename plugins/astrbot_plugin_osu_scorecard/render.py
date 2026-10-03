"""Pillow score-card renderer — 完全不碰 Photoshop。

为什么要它：走 Photoshop 那条路（psd.py）等于每次渲染都要
  打开 16 MB 的 PSD → 改 26 个文字层 → 替换 13 张位图 → 导出 PNG → 关闭，
光打开和导出本身就要十几秒。这是架构性的慢，调不动。

版式不是硬编码的：全部来自 `layer_mapping.json`。那份规格里每个文字层都记着
INK 框 (x, y, r, b) / font / sizePx / color / justify，所以 PIL 直接照着画。

z 序（自下而上，和 PSD 里 TEMPLATE_ROOT 的分组顺序一致）：
    beatmap_bg（压暗 74.9%）
    _deco_bg_gradient
    panel_glass / panel_border        <- 本模块自己画
    rank_glow（screen 混合）
    立绘
    player_avatar / star_strip / od_bar / hp_bar / mod_*
    所有文字层

psd.py 保留不动 —— 它是设计源，模板改了还要从它导出参考图。
"""
from __future__ import annotations

import functools
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

# ─────────────────────────── 字体 ───────────────────────────

# 查找顺序：随插件分发的 fonts/ 优先（跨平台、可控），然后 Windows，最后 Linux。
# 顺序很重要 —— 服务器上系统字体里没有 Inter，只有自带那份才有，
# 所以自带目录必须排在最前面，避免被系统里的同名近似字体顶掉。
_BUNDLED_FONTS = Path(__file__).resolve().parent / "fonts"
# 商业字体（Yu Gothic 等）放这里 —— 不进公开仓库，只在自己服务器上放。
_FONTS_PRIVATE = Path(__file__).resolve().parent / "fonts_private"
# 也可以把私有字体放到 data 目录（AstrBot 升级不会清它）
_FONTS_IN_DATA = Path(__file__).resolve().parent / "data" / "fonts"

_FONT_DIRS = [
    _BUNDLED_FONTS,
    _FONTS_PRIVATE,
    _FONTS_IN_DATA,
    # 允许部署时用环境变量追加一个目录（比如把字体放在 data/ 下方便管理）
    *( [Path(__import__("os").environ["SCORECARD_FONT_DIR"])]
       if __import__("os").environ.get("SCORECARD_FONT_DIR") else [] ),
    Path.home() / "AppData/Local/Microsoft/Windows/Fonts",
    Path("C:/Windows/Fonts"),
    Path("/usr/share/fonts"),
    Path("/usr/local/share/fonts"),
    Path.home() / ".fonts",
    Path.home() / ".local/share/fonts",
]

# Photoshop 的 PostScript 名 -> 磁盘上的文件名。
# 这些名字来自 layer_mapping.json 的 font 字段。
_FONT_FILES = {
    "Inter18pt-Regular":   "Inter_18pt-Regular.ttf",
    "Inter18pt-Medium":    "Inter_18pt-Medium.ttf",
    "Inter18pt-SemiBold":  "Inter_18pt-SemiBold.ttf",
    "Inter18pt-Bold":      "Inter_18pt-Bold.ttf",
    "Inter18pt-ExtraBold": "Inter_18pt-ExtraBold.ttf",
    "Inter18pt-Black":     "Inter_18pt-Black.ttf",
    "Montserrat-Black":    "Montserrat-Black.ttf",
    "Montserrat-Bold":     "Montserrat-Bold.ttf",
    "Montserrat-Medium":   "Montserrat-Medium.ttf",
    "Montserrat-Regular":  "Montserrat-Regular.ttf",
    "JetBrainsMono-Regular": "JetBrainsMono-Regular.ttf",
    "JetBrainsMono-Bold":  "JetBrainsMono-Bold.ttf",
}

# 日文/中文回退。YuGothic-Medium 在模板里就是标题的 cjkFont，
# 但 Yu Gothic 是商业字体、不能随包分发，所以 Linux 上退到 Noto Sans CJK
# （Ubuntu 自带，OFL 许可）。两者字形都是日式哥特体，观感接近。
_CJK_CANDIDATES = [
    "YuGothM.ttc", "YuGothR.ttc",             # Windows 日文（商业，仅本机可用）
    "NotoSansCJK-Regular.ttc",                # Linux 常见（OFL，可分发）
    "NotoSansCJKjp-Regular.otf",
    "SourceHanSansJP-Regular.otf",
    "meiryo.ttc", "msgothic.ttc", "msyh.ttc",  # Windows 其它日文/中文
    "segoeui.ttf", "arial.ttf",                # 最后的纯拉丁兜底
    "DejaVuSans.ttf",                          # Linux 最后的兜底
]

# .ttc 需要 index。Noto Sans CJK 的 ttc 里 index 0 是 JP（实测 Ubuntu 22.04）。
_CJK_INDEX = {"YuGothM.ttc": 0, "YuGothR.ttc": 0, "meiryo.ttc": 0, "msgothic.ttc": 0,
              "msyh.ttc": 0, "NotoSansCJK-Regular.ttc": 0}

_font_cache: dict[tuple, ImageFont.FreeTypeFont | None] = {}


@functools.lru_cache(maxsize=1)
def _font_index() -> dict:
    """文件名(小写) -> 路径。首次调用扫一遍，之后走缓存。

    必须递归：Linux 的字体是嵌套的（/usr/share/fonts/truetype/dejavu/...），
    直接 d / name 是找不到的 —— 这是 Windows 上不会暴露的差异。
    """
    idx = {}
    for d in _FONT_DIRS:
        if not d.is_dir():
            continue
        try:
            for p in d.rglob("*"):
                if p.is_file() and p.suffix.lower() in (".ttf", ".otf", ".ttc"):
                    # 先到先得：_FONT_DIRS 的顺序就是优先级
                    idx.setdefault(p.name.lower(), p)
        except OSError:
            continue
    return idx


def _find_file(name: str) -> Path | None:
    return _font_index().get(Path(name).name.lower())


def _first_existing(names: list[str]) -> Path | None:
    for n in names:
        p = _find_file(n)
        if p:
            return p
    return None


def _load(path: Path, size: int) -> ImageFont.FreeTypeFont | None:
    try:
        if path.suffix.lower() == ".ttc":
            return ImageFont.truetype(str(path), size, index=_CJK_INDEX.get(path.name, 0))
        return ImageFont.truetype(str(path), size)
    except OSError:
        return None


def resolve_font(postscript_name: str, size: int) -> ImageFont.FreeTypeFont | None:
    """PS 的字体名 -> PIL 字体对象。找不到返回 None（调用方回退）。"""
    key = (postscript_name, size)
    if key in _font_cache:
        return _font_cache[key]

    fname = _FONT_FILES.get(postscript_name)
    if fname is None and postscript_name.lower().startswith("yugoth"):
        fname = "YuGothM.ttc"
    path = _find_file(fname) if fname else None
    f = _load(path, size) if path else None
    if f is None:                     # 兜底：随便找个能用的
        p = _first_existing(_CJK_CANDIDATES + ["segoeui.ttf", "arial.ttf"])
        f = _load(p, size) if p else None
    _font_cache[key] = f
    return f


def _has_cjk(text: str) -> bool:
    return any(ord(ch) >= 0x2E80 for ch in text)


def font_for(postscript_name: str, size: int, text: str, cjk_font: str | None):
    """带 CJK 回退的字体选择。

    Inter 没有任何 CJK 字形；Photoshop 会**静默替换**成别的字体，PIL 不会 ——
    它会画成豆腐块。所以含 CJK 时必须显式换字体。
    """
    if cjk_font and _has_cjk(text):
        f = resolve_font(cjk_font, size)
        if f is not None:
            return f
    return resolve_font(postscript_name, size)


# ─────────────────────────── 工具 ───────────────────────────


def hex_rgb(value: str) -> tuple[int, int, int]:
    v = str(value).lstrip("#")
    return (int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16))


def _screen(base: Image.Image, top: Image.Image) -> Image.Image:
    """Photoshop 的 Screen 混合：结果 = 1-(1-a)(1-b)，按 top 的 alpha 加权。"""
    from PIL import ImageChops

    b = base.convert("RGBA")
    t = top.convert("RGBA")
    sc = ImageChops.screen(b.convert("RGB"), t.convert("RGB"))
    return Image.composite(sc, b.convert("RGB"), t.split()[3]).convert("RGBA")


def _rounded_mask(size, box, radius, ss=4):
    l, t, r, b = box
    w, h = r - l, b - t
    m = Image.new("L", (w * ss, h * ss), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, w * ss - 1, h * ss - 1], radius=radius * ss, fill=255)
    return m.resize((w, h), Image.LANCZOS)


# ─────────────────────────── 渲染器 ───────────────────────────

SIGNBOARD_FALLBACK = {
    # 用户定的规则：**不管有没有开 mod，S 系一律用 S 的立绘，SS 系一律用 SS 的**。
    # 所以 X 前缀（Hidden/开 mod 出的评级）不再走单独立绘：
    #   XH (= SS+HD) -> signboard_ss
    #   SH (= S+HD)  -> signboard_s
    # 缺的那几档先退回 B，等出图后再填。
    "XH": ["signboard_ss", "signboard_b"],
    "SS": ["signboard_ss", "signboard_b"],
    "SH": ["signboard_s",  "signboard_b"],
    "S":  ["signboard_s",  "signboard_b"],
    "A":  ["signboard_a",  "signboard_b"],
    "B":  ["signboard_b",  "signboard_a"],
    "C":  ["signboard_c",  "signboard_b"],
    "D":  ["signboard_d",  "signboard_b"],
    "F":  ["signboard_f",  "signboard_b"],
}


class PilScoreCardRenderer:
    """一张卡。无状态，可复用。"""

    def __init__(self, spec: Path, assets_dir: Path | None = None,
                 work_dir: Path | None = None):
        self.spec_path = Path(spec)
        self.assets_dir = Path(assets_dir) if assets_dir else Path(spec).parent / "assets"
        self.work_dir = Path(work_dir) if work_dir else Path(spec).parent / "renders"
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.spec = json.loads(self.spec_path.read_text(encoding="utf-8"))
        self.canvas = self.spec.get("canvas", {"width": 1920, "height": 1080})
        self.render_cfg = self.spec.get("render", {})
        self._layers = {L["name"]: L for L in self.spec.get("textLayers", [])}
        self._static_warned = False

    # -- 和 psd.ScoreCardRenderer 同名的接口，便于互换 -------------------
    def signboard_chain(self, grade: str) -> list[str]:
        return list(SIGNBOARD_FALLBACK.get(str(grade).upper(), ["signboard_b"]))

    # -- 内部 ----------------------------------------------------------
    def _darken_bg(self, img: Image.Image) -> Image.Image:
        """复现 PSD 里 _deco_bg_overlay 的压暗。

        那层是 #0B0D11 实色、透明度 74.9%。用两张已知导出色板反解出来是
        (10.7, 13.2, 17.2)，和 #0B0D11 = (11,13,17) 一致。
        """
        pct = float(self.render_cfg.get("bgDimPct", 74.9)) / 100.0
        overlay = hex_rgb(self.render_cfg.get("bgOverlayColor", "#0B0D11"))
        base = img.convert("RGB")
        ov = Image.new("RGB", base.size, overlay)
        return Image.blend(base, ov, pct)

    def _draw_panel(self, card: Image.Image, bg: Image.Image) -> None:
        """毛玻璃底板。参数照抄 template/build/build_panels75.py 的 panel_frost()。"""
        p = self.render_cfg.get("panel", {})
        box = tuple(p.get("box", [40, 40, 1256, 1020]))
        radius = int(p.get("radius", 36))
        blur = float(p.get("blur", 44))
        keep = float(p.get("keep", 0.50))
        desat = float(p.get("desat", 0.25))
        tint = tuple(p.get("tint", [10, 14, 22]))

        l, t, r, b = box
        w, h = r - l, b - t

        # 模糊的是**已经压暗过的**背景（PSD 里底板在 bg 组之上）。
        # 降饱和和压暗都用 PIL 的整图运算做 —— 逐像素 Python 循环在
        # 1216x980 上要 1 秒左右，是这套渲染里最大的瓶颈。
        #
        # 半径 44 的高斯模糊在 1920x1080 上要 0.2s。先缩到 1/4、用 1/4 半径模糊、
        # 再放大：对这么重的模糊肉眼看不出差别，但快一个数量级。
        W, H = bg.size
        small = bg.resize((max(1, W // 4), max(1, H // 4)), Image.BILINEAR)
        blurred = small.filter(ImageFilter.GaussianBlur(blur / 4.0))
        blurred = blurred.resize((W, H), Image.BILINEAR).crop(box)
        grey = ImageOps.grayscale(blurred).convert("RGB")
        mixed = Image.blend(blurred, grey, desat)
        glass = Image.blend(mixed, Image.new("RGB", (w, h), tint), 1.0 - keep)

        mask = _rounded_mask((w, h), box, radius)
        card.paste(glass, (l, t), mask)

        # 1px 白色描边
        rgba = tuple(p.get("borderRGBA", [255, 255, 255, 41]))
        bm = _rounded_mask((w, h), box, radius)
        inner = Image.new("L", (w, h), 0)
        ImageDraw.Draw(inner).rounded_rectangle([2, 2, w - 3, h - 3],
                                                radius=max(0, radius - 1), fill=255)
        import numpy as np
        ring = Image.fromarray(
            (np.clip(np.asarray(bm, "int16") - np.asarray(inner, "int16"), 0, 255)).astype("uint8"))
        ring_rgba = Image.new("RGBA", (w, h), rgba)
        card.paste(ring_rgba, (l, t), ring)

    def _draw_texts(self, card: Image.Image, text_layers: list[dict]) -> int:
        draw = ImageDraw.Draw(card)
        drawn = 0
        for item in text_layers:
            name = item.get("name")
            value = item.get("value")
            spec = self._layers.get(name)
            if spec is None or value in (None, ""):
                continue
            size = int(round(spec.get("sizePx", 16)))
            font = font_for(spec.get("font", "Inter18pt-Regular"), size,
                            str(value), spec.get("cjkFont"))
            if font is None:
                continue
            colour = item.get("accent") or spec.get("color", "#EAEEF6")
            rgb = hex_rgb(colour)

            ink = spec.get("ink")
            if not ink:
                continue
            il, it = ink[0], ink[1]
            example = spec.get("example", "")

            # 用「示例文字」的墨迹偏移定出**笔原点** —— PS 的点文字里原点是恒定的，
            # 换一个字符串只会改变墨迹，不会改变原点。
            ref = draw.textbbox((0, 0), example or str(value), font=font)
            ox = il - ref[0]
            oy = it - ref[1]
            if spec.get("justify") == "center":
                # 居中：把示例墨迹的中心对齐到实际墨迹的中心
                cx = (ink[0] + ink[2]) / 2.0
                tw = draw.textbbox((0, 0), str(value), font=font)
                ox = cx - (tw[2] - tw[0]) / 2.0 - tw[0]
            draw.text((ox, oy), str(value), font=font, fill=rgb)
            drawn += 1
        return drawn

    # -- 主入口 --------------------------------------------------------
    def render(self, text_layers: list[dict], rasters: list[dict],
               signboard, out_png: Path) -> dict:
        W = int(self.canvas.get("width", 1920))
        H = int(self.canvas.get("height", 1080))
        by_layer = {}
        for r in (rasters or []):
            by_layer[r.get("layer")] = r

        card = Image.new("RGBA", (W, H), (0, 0, 0, 255))
        used = []

        # 1. 背景 + 压暗
        bg_r = by_layer.get("beatmap_bg")
        if bg_r:
            bg = Image.open(bg_r["path"]).convert("RGB")
            bg = bg.resize((W, H), Image.LANCZOS) if bg.size != (W, H) else bg
            bg = self._darken_bg(bg)
            card.paste(bg, (0, 0))
            used.append("beatmap_bg")
        else:
            bg = Image.new("RGB", (W, H), (11, 13, 17))

        # 2. 评级染色
        if "beatmap_bg" in by_layer:
            g = by_layer.get("_deco_bg_gradient")
            if g:
                ov = Image.open(g["path"]).convert("RGBA")
                card = _screen(card, ov)
                used.append("_deco_bg_gradient")

        # 3. 毛玻璃底板
        self._draw_panel(card, bg)
        used.append("panel")

        # 4. 评级辉光（screen）
        glow = by_layer.get("rank_glow")
        if glow:
            card = _screen(card, Image.open(glow["path"]).convert("RGBA"))
            used.append("rank_glow")

        # 5. 立绘
        chain = [signboard] if isinstance(signboard, str) else list(signboard or [])
        self._signboard_used = None
        for nm in chain:
            p = self.assets_dir / "signboards" / f"{nm}.png"
            if not p.is_file():
                p = self.assets_dir / f"{nm}.png"
            if p.is_file():
                il = Image.open(p).convert("RGBA")
                if il.size != (W, H):
                    il = il.resize((W, H), Image.LANCZOS)
                card.alpha_composite(il)
                used.append(nm)
                self._signboard_used = nm
                break

        # 5b. 模板的静态内容（_deco_* 标签、判定图标、属性图标、分隔线）
        #
        # 这些在走 Photoshop 时是模板自带的，插件从不设置。PIL 只画插件给的东西，
        # 所以必须单独抽出来叠上去 —— 否则卡片上会缺掉 TOTAL PP / JUDGEMENT /
        # ACCURACY 等一整批小标签和所有图标。
        # 由 template/build 的 export_static.jsx 导出，改动模板后要重新导出。
        static_p = self.assets_dir / "static_overlay.png"
        if static_p.is_file():
            so = Image.open(static_p).convert("RGBA")
            if so.size != (W, H):
                so = so.resize((W, H), Image.LANCZOS)
            card.alpha_composite(so)
            used.append("static_overlay")
        elif not self._static_warned:
            self._static_warned = True

        # 6. 位图（头像 / 星级条 / 属性条 / mod）
        for nm in ("player_avatar", "star_strip", "od_bar", "hp_bar", "mod_1"):
            r = by_layer.get(nm)
            if r:
                im = Image.open(r["path"]).convert("RGBA")
                if im.size != (W, H):
                    im = im.resize((W, H), Image.LANCZOS)
                card.alpha_composite(im)
                used.append(nm)

        # 7. 文字
        n_text = self._draw_texts(card, text_layers)

        out_png = Path(out_png)
        out_png.parent.mkdir(parents=True, exist_ok=True)
        card.convert("RGB").save(out_png, "PNG", optimize=False)

        return {"ok": True, "out": str(out_png), "engine": "pil",
                "text": n_text, "rasters": len(used), "used": used,
                "signboard": chain[0] if chain else None}


def fonts_report() -> list[dict]:
    """自检用：每个模板字体解析到了哪个文件。"""
    out = []
    for ps in sorted(_FONT_FILES):
        p = _find_file(_FONT_FILES[ps])
        out.append({"font": ps, "path": str(p) if p else None, "found": bool(p)})
    for ps in ("YuGothic-Medium",):
        p = _first_existing(_CJK_CANDIDATES)
        out.append({"font": ps, "path": str(p) if p else None, "found": bool(p)})
    return out
