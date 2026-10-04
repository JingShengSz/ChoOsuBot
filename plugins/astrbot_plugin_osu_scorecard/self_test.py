"""Offline check of the score card pipeline.

Three layers, each runnable on its own:

    python self_test.py             mapping + rasters   (no network, no PS)
    python self_test.py --render    the above, then a real render through Photoshop
    python self_test.py --only map  just the field mapping

The mapping stage is the one that matters most: it runs the frozen real payload of
score 6645548845 through the same code path the plugin uses and compares every
field against the values that card is already known to show. If a field name in the
osu! API ever shifts, this is what catches it.

Exit code 0 = everything that ran passed.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import card as cardmod          # noqa: E402
import raster                   # noqa: E402

FIXTURE = HERE / "tests" / "fixture_score.json"

# The card this fixture must produce. Values are the ones the reference render was
# built from; `map_max_combo` is deliberately the API's number (see the note below).
EXPECTED_TEXT = {
    "player_name":      "F6A8AF",
    "score":            "984K",
    "score_suffix":     ".196",
    "pp":               "148pp",
    "accuracy":         "99.53%",     # lazer play: API value is primary
    "accuracy_lazer":   "99.88%",     # stable-comparable value on the right
    "max_combo":        "2,922x",
    "map_max_combo":    "2,922x",     # FC -> the player max_combo (see card.py)
    "count_max":        "2,295",
    "count_300":        "617",
    "count_200":        "10",
    "count_100":        "0",
    "count_50":         "0",
    "count_miss":       "0",
    "play_date":        "2026-05-05",
    "beatmap_id":       "#5493536",
    "beatmap_mapper":   "mapped by J-99",
    "beatmap_difficulty": "[4K] Rigid-Brained Girl",
    "bpm":              "181",
    "od":               "8.5",
    "hp":               "8.5",
    "star_rating":      "",
    "total_pp":         "9,486pp",
    "rank_change":      "#165",
    # the unicode fields win, which is what osu! itself displays
    "beatmap_title":    "脳味噌リジッドガール",
    "beatmap_artist":   "森羅万象",
}

FAILURES: list[str] = []


def check(label: str, got, want) -> None:
    ok = got == want
    if not ok:
        FAILURES.append(f"{label}: 期望 {want!r}，实际 {got!r}")
    print(f"  {'ok  ' if ok else 'FAIL'}  {label:<20} {got!r}")


# ─────────────────────────────── stage 1: mapping ───────────────────────────────


def stage_mapping() -> dict:
    print("── 1. 字段映射（冻结的真实成绩 6645548845）")
    if not FIXTURE.is_file():
        FAILURES.append(f"缺少 fixture: {FIXTURE}（先在有机器的凭据上跑 tests/make_fixture.py）")
        print(f"  FAIL  找不到 {FIXTURE}")
        return {}
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    score = payload["score"]
    player = payload.get("player") or {}
    beatmap = score.get("beatmap") or {}
    beatmapset = score.get("beatmapset") or {}

    print(f"  fixture 里的 beatmapset 键: {sorted(beatmapset)[:12]}")
    data = cardmod.build_card(score, beatmap, beatmapset, player)
    layers = data.to_layers()

    for name, want in EXPECTED_TEXT.items():
        check(name, layers.get(name), want)

    print(f"  {'ok  ' if data.grade == 'S' else 'FAIL'}  grade                {data.grade!r}")
    if data.grade != "S":
        FAILURES.append(f"grade: 期望 'S'，实际 {data.grade!r}")
    check("mods", data.mods, [])
    check("od_range", data.od_range, (0.0, 10.0))
    check("hp_range", data.hp_range, (0.0, 10.0))
    print(f"  --    star_value           {data.star_value}")
    print(f"  --    background_url 有值  {bool(data.background_url)}")
    print(f"  --    avatar_url 有值      {bool(data.avatar_url)}")
    return {"data": data}


# ─────────────────────────────── stage 2: rasters ───────────────────────────────


def _nonblank(img) -> tuple[float, bool]:
    """Fraction of pixels with any alpha, and whether that is enough to be real."""
    alpha = img.getchannel("A")
    hist = alpha.histogram()
    painted = sum(hist[16:])
    total = img.width * img.height
    frac = painted / total
    return frac, frac > 0.005


def stage_rasters(info: dict) -> None:
    print("\n── 2. 位图生成（星级条 / OD-HP 条 / 头像 / mod 徽章）")
    data = info.get("data")
    if data is None:
        print("  跳过：映射阶段没有产出数据")
        return

    strip = raster.render_star_strip(data.star_value, 600)
    frac, ok = _nonblank(strip)
    print(f"  {'ok  ' if ok else 'FAIL'}  star_strip  {strip.size}  墨迹 {frac:.1%}")
    if not ok:
        FAILURES.append("star_strip 是空白的")
    if strip.width != 600:
        FAILURES.append(f"star_strip 宽度应为 600，实际 {strip.width}")

    # A perfect score and an empty one must not look the same.
    hi = raster.render_star_strip(10.0, 600)
    lo = raster.render_star_strip(0.0, 600)
    differing = sum(1 for a, b in zip(hi.getdata(), lo.getdata()) if a != b)
    print(f"  {'ok  ' if differing else 'FAIL'}  10.0★ 与 0.0★ 有 {differing} 个像素不同")
    if not differing:
        FAILURES.append("星级条对星级没有反应")

    for name, value, rng in (("od_bar", data.od_value, data.od_range),
                             ("hp_bar", data.hp_value, data.hp_range)):
        bar = raster.render_stat_bar(value, rng[0], rng[1], width=600, height=12)
        frac, ok = _nonblank(bar)
        print(f"  {'ok  ' if ok else 'FAIL'}  {name:<10} {bar.size}  覆盖 {frac:.1%}")
        if not ok:
            FAILURES.append(f"{name} 是空白的")

    full = raster.render_stat_bar(10.0, 0, 10, width=600, height=12)
    empty = raster.render_stat_bar(0.0, 0, 10, width=600, height=12)
    differing = sum(1 for a, b in zip(full.getdata(), empty.getdata()) if a != b)
    print(f"  {'ok  ' if differing else 'FAIL'}  OD 满格与空格有 {differing} 个像素不同")
    if not differing:
        FAILURES.append("OD 条对数值没有反应")


# ─────────────────────────────── stage 3: render ───────────────────────────────


def stage_render(info: dict, template: Path, assets: Path) -> None:
    print("\n── 3. 真实渲染（Photoshop COM）")
    import psd

    data = info.get("data")
    if data is None:
        print("  跳过：没有成绩数据")
        return
    if not template.is_file():
        print(f"  跳过：模板不存在 {template}")
        return

    from PIL import Image
    out_dir = HERE / "tests" / "out"
    out_dir.mkdir(parents=True, exist_ok=True)

    def blank():
        return Image.new("RGBA", (1920, 1080), (0, 0, 0, 0))

    rasters = []
    sheet = blank()
    sheet.alpha_composite(raster.render_star_strip(data.star_value, 600), (60, 310))
    p = out_dir / "strip.png"
    sheet.save(p)
    rasters.append({"layer": "star_strip", "group": "beatmap_stats", "path": p.as_posix()})

    for name, value, rng, y in (("od_bar", data.od_value, data.od_range, 520),
                                ("hp_bar", data.hp_value, data.hp_range, 588)):
        bar = raster.render_stat_bar(value, rng[0], rng[1], width=600, height=12)
        sheet = blank()
        sheet.alpha_composite(bar, (60, y))
        p2 = out_dir / f"{name}.png"
        sheet.save(p2)
        rasters.append({"layer": name, "group": "beatmap_stats", "path": p2.as_posix()})

    rank_png = assets / "rank_svg" / f"tint_{data.grade}.png"
    if rank_png.is_file():
        rasters.append({"layer": "_deco_bg_gradient", "group": "bg",
                        "path": rank_png.as_posix()})

    # The accuracy readout takes the grade's colour — read it from the same
    # mapping the plugin uses, never a hard-coded one.
    accent = None
    mapping_path = template.parent / "layer_mapping.json"
    if mapping_path.is_file():
        mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
        for row in mapping.get("rankColors") or []:
            if str(row.get("key", "")).upper() == str(data.grade).upper():
                accent = row.get("color")
    if not accent:
        FAILURES.append(f"layer_mapping.json 里没有 {data.grade} 的评级色")
    print(f"  评级 {data.grade} 的强调色 {accent}")

    jobs = []
    for name, value in data.to_layers().items():
        text = "" if value is None else str(value)
        jobs.append({"name": name, "value": text,
                     "font": "YuGothic-Medium" if any(ord(c) > 0x2E7F for c in text) else None,
                     "accent": accent if name == "accuracy" else None})

    renderer = psd.ScoreCardRenderer(template, out_dir / "work", timeout_seconds=300)
    out_png = out_dir / "self_test_card.png"
    result = renderer.render(jobs, rasters, renderer.signboard_chain(data.grade), out_png)

    print(f"  文字层写入 {result.get('textApplied')}，缺失 {result.get('textMissing')}")
    print(f"  位图替换   {result.get('rasters')}")
    print(f"  立绘       {result.get('shown')}")
    for line in result.get("log") or []:
        print(f"    · {line}")
    if result.get("textMissing"):
        FAILURES.append(f"这些文字层在模板里找不到: {result['textMissing']}")

    img = Image.open(out_png).convert("RGB")
    stat = img.convert("L").histogram()
    spread = max(i for i, n in enumerate(stat) if n)
    darkest = min(i for i, n in enumerate(stat) if n)
    print(f"  {'ok  ' if spread - darkest > 40 else 'FAIL'}  {out_png.name} {img.size} "
          f"亮度范围 {darkest}..{spread}")
    if spread - darkest <= 40:
        FAILURES.append("导出的 PNG 几乎是单色，渲染没有生效")
    else:
        print(f"  看图: {out_png}")


def stage_render_full(info: dict, template: Path, assets: Path) -> None:
    """The whole card: background, avatar, mod badges and glow as well.

    Unlike stage_render this needs network (the cover and avatar are CDN URLs) and
    exercises every raster slot the plugin fills.
    """
    print("\n── 4. 全量渲染（背景 + 头像 + mod 徽章 + 辉光）")
    import urllib.request

    from PIL import Image

    import psd

    data = info.get("data")
    if data is None or not template.is_file():
        print("  跳过：缺少成绩数据或模板")
        return

    out_dir = HERE / "tests" / "out"
    out_dir.mkdir(parents=True, exist_ok=True)

    def blank():
        return Image.new("RGBA", (1920, 1080), (0, 0, 0, 0))

    def fetch(url):
        if not url:
            return None
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "osu-scorecard-self-test/1.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except Exception as exc:  # noqa: BLE001
            print(f"    （下载失败 {type(exc).__name__}，这一步跳过）")
            return None

    rasters = []
    from io import BytesIO

    # background
    bg_bytes = fetch(data.background_url)
    if bg_bytes:
        bg = raster.cover_fit(Image.open(BytesIO(bg_bytes)))
        p = out_dir / "full_bg.png"
        bg.save(p)
        rasters.append({"layer": "beatmap_bg", "group": "bg", "path": p.as_posix()})
        print(f"  ok    背景     {bg.size}")

    # avatar
    av_bytes = fetch(data.avatar_url)
    if av_bytes:
        sheet = blank()
        sheet.alpha_composite(
            raster.render_avatar(Image.open(BytesIO(av_bytes)).convert("RGBA")), (922, 60))
        p = out_dir / "full_avatar.png"
        sheet.save(p)
        rasters.append({"layer": "player_avatar", "group": "player_info", "path": p.as_posix()})
        print(f"  ok    头像     {sheet.size}")

    # star strip + bars
    sheet = blank()
    sheet.alpha_composite(raster.render_star_strip(data.star_value, 600), (60, 310))
    p = out_dir / "full_strip.png"
    sheet.save(p)
    rasters.append({"layer": "star_strip", "group": "beatmap_stats", "path": p.as_posix()})

    for name, value, rng, y in (("od_bar", data.od_value, data.od_range, 520),
                                ("hp_bar", data.hp_value, data.hp_range, 588)):
        bar = raster.render_stat_bar(value, rng[0], rng[1], width=600, height=12)
        sheet = blank()
        sheet.alpha_composite(bar, (60, y))
        p = out_dir / f"full_{name}.png"
        sheet.save(p)
        rasters.append({"layer": name, "group": "beatmap_stats", "path": p.as_posix()})

    # mod badges — deliberately a list with mods, so the badge path is covered
    demo_mods = ["HD", "DT", "HR", "FL", "EZ", "NF"]
    mod_sheet, placed = raster.render_mod_row(demo_mods, assets / "mods" / "ready")
    p = out_dir / "full_mods.png"
    mod_sheet.save(p)
    rasters.append({"layer": "mod_1", "group": "mods_block", "path": p.as_posix()})
    empty = blank()
    empty_p = out_dir / "full_empty.png"
    empty.save(empty_p)
    for i in range(2, raster.MOD_SLOTS + 1):
        rasters.append({"layer": f"mod_{i}", "group": "mods_block", "path": empty_p.as_posix()})
    print(f"  ok    mod 徽章 放置 {[m['code'] for m in placed]}")

    # rank theme
    grade = (data.grade or "D").upper()
    tint = assets / "rank_svg" / f"tint_{grade}.png"
    glow = assets / "rank_svg" / f"glow_{grade}.png"
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

    renderer = psd.ScoreCardRenderer(template, out_dir / "work", timeout_seconds=300)
    out_png = out_dir / "self_test_full.png"
    result = renderer.render(jobs, rasters, renderer.signboard_chain(grade), out_png)
    print(f"  文字层 {result.get('textApplied')}，位图 {len(result.get('rasters') or [])}，"
          f"立绘 {result.get('shown')}")
    for line in result.get("log") or []:
        print(f"    · {line}")

    img = Image.open(out_png).convert("RGB")
    spread = max(i for i, n in enumerate(img.convert("L").histogram()) if n)
    darkest = min(i for i, n in enumerate(img.convert("L").histogram()) if n)
    ok = spread - darkest > 40
    print(f"  {'ok  ' if ok else 'FAIL'}  {out_png.name} {img.size} 亮度范围 {darkest}..{spread}")
    if not ok:
        FAILURES.append("全量渲染的 PNG 几乎是单色")
    else:
        img.resize((1180, 664), Image.LANCZOS).save(out_dir / "full_view.png")
        print(f"  看图: {out_dir / 'full_view.png'}")


def stage_plugin() -> None:
    """Load main.py and exercise the pieces that need no live AstrBot event.

    main.py uses relative imports, exactly like the sibling plugins, so it is
    loaded here inside a throwaway package. Anything that would need a real
    AstrMessageEvent is stubbed with the few attributes the code touches.
    """
    print("\n── 5. 插件逻辑（正则 / 参数解析 / 存储 / 报错脱敏）")
    import importlib.util
    import tempfile
    import types

    pkg_name = "_osucard_selftest"
    pkg = types.ModuleType(pkg_name)
    pkg.__path__ = [str(HERE)]
    sys.modules[pkg_name] = pkg
    spec = importlib.util.spec_from_file_location(f"{pkg_name}.main", HERE / "main.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[f"{pkg_name}.main"] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception as exc:  # noqa: BLE001
        FAILURES.append(f"main.py 无法导入: {type(exc).__name__}: {exc}")
        print(f"  FAIL  main.py 导入失败: {type(exc).__name__}: {exc}")
        return
    print("  ok    main.py 导入成功（相对导入可用）")

    # --- score link recognition ---
    cases = [
        ("https://osu.ppy.sh/scores/6645548845", True),
        ("https://osu.ppy.sh/community/scores/6645548845", True),
        ("看看这个 osu.ppy.sh/scores/123456 好吗", True),
        ("https://osu.ppy.sh/beatmapsets/2498268", False),
        ("https://osu.ppy.sh/users/32749965", False),
    ]
    for text, want in cases:
        got = bool(mod.SCORE_URL_RE.search(text))
        if got != want:
            FAILURES.append(f"链接识别 {text!r}: 期望 {want}，实际 {got}")
        print(f"  {'ok  ' if got == want else 'FAIL'}  链接识别 {want!s:<5} {text}")

    # --- command argument stripping ---
    class FakeEvent:
        def __init__(self, text):
            self.message_str = text

    arg_cases = [
        ("s 6645548845", "6645548845"),
        ("s https://osu.ppy.sh/scores/6645548845", "https://osu.ppy.sh/scores/6645548845"),
        ("bind Cookiezi", "Cookiezi"),
        ("p", ""),
        ("r", ""),
        # a bare link must NOT be eaten by the command stripper
        ("https://osu.ppy.sh/scores/1", "https://osu.ppy.sh/scores/1"),
    ]
    for text, want in arg_cases:
        got = mod.OsuScoreCardPlugin._args(FakeEvent(text))
        if got != want:
            FAILURES.append(f"_args({text!r}): 期望 {want!r}，实际 {got!r}")
        print(f"  {'ok  ' if got == want else 'FAIL'}  参数解析 {text!r} -> {got!r}")

    # --- the command guard must catch every command word ---
    for word in mod.COMMAND_NAMES:
        head = word.lower()
        caught = any(head.startswith(n) for n in mod.COMMAND_NAMES)
        if not caught:
            FAILURES.append(f"自动链接处理器不会跳过 {word}")
    print(f"  ok    自动链接跳过 {'/'.join(mod.COMMAND_NAMES)}")

    # --- errors must never leak a credential VALUE ---
    # Naming the config keys is fine (that is how the user is told what to fill in);
    # what must never appear is a token, an Authorization header or a long secret-like
    # run of characters.
    secret_shaped = re.compile(r"[A-Za-z0-9_\-]{32,}")
    samples = [
        "Fill osu_client_id and osu_client_secret in the local configuration",
        "osu! API HTTP 404 at /api/v2/scores/1",
        "osu! API HTTP 429 at /api/v2/users/1/mania",
        "some other failure",
        "token abcdefghijklmnopqrstuvwxyz0123456789ABCD rejected",
    ]
    for s in samples:
        msg = mod.OsuScoreCardPlugin._explain(RuntimeError(s), "出错了")
        bad = []
        if "Bearer" in msg or "access_token" in msg:
            bad.append("auth header")
        if secret_shaped.search(msg):
            bad.append("secret-shaped string")
        if bad:
            FAILURES.append(f"_explain 泄漏了 {bad}: {msg}")
        print(f"  {'ok  ' if not bad else 'FAIL'}  脱敏 {s[:34]!r} -> {msg[:52]!r}")

    # --- storage round trip ---
    import store as storemod

    with tempfile.TemporaryDirectory() as tmp:
        st = storemod.Store(Path(tmp), cache_minutes=10)
        st.bind("10001", "F6A8AF")
        ok = st.username_for("10001") == "F6A8AF"
        print(f"  {'ok  ' if ok else 'FAIL'}  绑定写入/读取")
        if not ok:
            FAILURES.append("绑定读写失败")

        st.put_player("F6A8AF", "mania", {"total_pp": 9485.6, "user_id": 32749965})
        got = st.cached_player("F6A8AF", "mania")
        ok = bool(got) and abs(got["total_pp"] - 9485.6) < 0.01
        print(f"  {'ok  ' if ok else 'FAIL'}  玩家缓存命中")
        if not ok:
            FAILURES.append("玩家缓存读回不正确")

        # a fresh Store must see what the previous one wrote
        st2 = storemod.Store(Path(tmp), cache_minutes=10)
        ok = st2.username_for("10001") == "F6A8AF" and st2.cached_player("F6A8AF", "mania")
        print(f"  {'ok  ' if ok else 'FAIL'}  落盘后重新加载仍在")
        if not ok:
            FAILURES.append("存储没有真正落盘")

        # TTL 0 means "never serve from cache"
        st3 = storemod.Store(Path(tmp), cache_minutes=0)
        ok = st3.cached_player("F6A8AF", "mania") is None
        print(f"  {'ok  ' if ok else 'FAIL'}  cache_minutes=0 时缓存不命中")
        if not ok:
            FAILURES.append("cache_minutes=0 仍然返回了缓存")

        st.unbind("10001")
        ok = st.username_for("10001") is None
        print(f"  {'ok  ' if ok else 'FAIL'}  解绑")
        if not ok:
            FAILURES.append("解绑失败")


# ─────────────────────────────── main ───────────────────────────────


def stage_new_engines(info: dict) -> None:
    """Pillow 渲染器 / pp_max / mod 倍率 / 绑定记录格式。

    这一节刻意用**真实调用路径产生的数据形状**，不是手写的理想输入 ——
    total_pp 那次就是喂了原始 API 形状，把「main 传的是扁平 dict」这个真 bug
    盖过去了。pp_max 也踩过同一个坑：card.judgements() 返回的键是
    count_max/count_300（模板的图层名），不是 perfect/great，
    pp 函数一开始读错了键，直接算不出来。
    """
    print("\n── 6. 新引擎与 pp_max")
    from PIL import Image

    import card as cardmod
    import render as rendermod

    data = info.get("data")
    if data is None:
        print("  跳过：没有成绩数据")
        return

    # ── (a) 用真实 judgements() 的键形状算 pp ──────────────────────────
    # 用 `data.counts` —— 这是**真实调用路径**的产物（build_card 出来的 CardData），
    # 不是 fixture 的原始 JSON。喂 fixture 根对象就会重演 total_pp 那次教训。
    score = info.get("score") or {}
    real_counts = dict(data.counts or {})
    check("judgements() 的键形状", sorted(real_counts),
          ["count_100", "count_200", "count_300", "count_50", "count_max", "count_miss"])
    print(f"   真实 counts = {real_counts}")
    check("counts 不是全零（真数据路径）", sum(real_counts.values()) > 0, True)

    pp_calc = cardmod.mania_pp(real_counts, 3.88145, [])
    check("用 count_* 键能算出 pp（不是 None）", pp_calc is not None, True)
    if pp_calc is not None:
        # 这条就是公式正确性的硬证据：拿同一局的实际判定反算，对比 API 给的值。
        ok = abs(pp_calc - 147.902) < 1.0
        print(f"   标定：公式 {pp_calc:.4f} vs API 147.902，差 {pp_calc - 147.902:+.4f}")
        check("pp 公式与 API 实测吻合（<1pp）", ok, True)

    mx = cardmod.max_pp(real_counts, 3.88145, [])
    check("max_pp 能算出值", mx is not None, True)
    if mx:
        print(f"   理论最大 PP（全 320 + 满连）= {mx:.2f}")
        # 全 320 等价于 customAccuracy = 1，退化式必须一致
        degenerate = (8.0 * max(3.88145 - 0.15, 0.05) ** 2.2 * 1.0
                      * (1 + 0.1 * min(1.0, sum(real_counts.values()) / 1500.0)))
        check("全 320 时退化成闭式表达", abs(mx - degenerate) < 1e-9, True)
        check("NF 倍率生效（×0.75）",
              abs(cardmod.max_pp(real_counts, 3.88145, ["NF"]) - mx * 0.75) < 1e-9, True)

    # ignore_hit 之类的非判定键不能污染 totalHits
    dirty = dict(real_counts)
    dirty["ignore_hit"] = 888
    check("点 ignore_hit 不影响 max_pp",
          cardmod.max_pp(dirty, 3.88145, []), mx)
    check("counts 为空的边界", cardmod.max_pp({}, 3.88145, []), None)
    check("星级为 0 的边界", cardmod.max_pp(real_counts, 0, []), None)

    # ── (b) build_card 全路径（走真实 fixture 形状）─────────────────────
    d_dash = cardmod.build_card(score, info.get("beatmap") or {},
                                info.get("beatmapset") or {},
                                info.get("profile") or {}, pp_max_mode="dash")
    check("pp_max_mode=dash 显示 --", d_dash.pp_max, "--")

    # ── (c) mod 倍率：只在变速 mod 出现时才给 ──────────────────────────
    plain = data.to_layers()
    check("无 mod 时不产生 mod_N_mult 键",
          [k for k in plain if k.endswith("_mult")], [])

    dt_score = dict(score)
    dt_score["mods"] = [{"acronym": "DT"}]
    dt_data = cardmod.build_card(dt_score, info.get("beatmap") or {},
                                 info.get("beatmapset") or {},
                                 info.get("profile") or {})
    dt_layers = dt_data.to_layers()
    check("DT 时 mod_1_mult 出现且为 x1.5", dt_layers.get("mod_1_mult"), "x1.5")

    hd_score = dict(score)
    hd_score["mods"] = [{"acronym": "HD"}]
    hd_layers = cardmod.build_card(hd_score, info.get("beatmap") or {},
                                   info.get("beatmapset") or {},
                                   info.get("profile") or {}).to_layers()
    check("HD 这种非变速 mod 不产生倍率",
          [k for k in hd_layers if k.endswith("_mult")], [])

    # ── (d) Photoshop 的 stale 图层清理必须写进 JSX ────────────────────
    import psd
    jsx = psd.build_jsx({"psd": "x.psd", "out": "y.png", "text": [], "rasters": [],
                         "signboard": ["signboard_s"]})
    check("JSX 里有 stale 图层清理", "stalePat" in jsx, True)
    check("清理覆盖 mod_N_mult", "mod_[0-9]+_mult" in jsx, True)

    # ── (e) 绑定记录的分服与旧格式迁移 ─────────────────────────────────
    #
    # 这一节踩过的坑：写「磁盘上已经是旧格式」的测试，必须在**构造 Store 之前**
    # 把旧数据落到文件里。先构造、再往内存里塞旧键，迁移逻辑根本不会跑，测试
    # 却会以为自己验过了迁移。
    import json
    import tempfile
    import store as storemod
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)

        # 1) 一代格式：qq -> "用户名"（字符串）
        (tdp / "bindings.json").write_text(
            json.dumps({"111": "Cookiezi"}), encoding="utf-8")
        st = storemod.Store(tdp, cache_minutes=10)
        check("旧格式绑定仍可读", st.username_for("111"), "Cookiezi")
        check("旧格式没有 ruleset", st.ruleset_for("111"), None)
        check("旧格式迁移后算官服", st.binding_for("111")["server"], "osu")

        # 2) 二代格式：qq -> {username, ruleset}（mode 指令那一代）
        st.bind("222", "WhiteCat", "osu", "osu")
        st._bindings.pop("osu:222")
        st._bindings["222"] = {"username": "WhiteCat", "ruleset": "taiko"}
        st._save(st._bindings_path, st._bindings)
        st2 = storemod.Store(tdp, cache_minutes=10)
        check("二代格式用户名没丢", st2.username_for("222"), "WhiteCat")
        check("二代格式 ruleset 没丢", st2.ruleset_for("222"), "taiko")

        # 3) 分服隔离：同一个 QQ 在官服和私服是两个人，必须互不覆盖
        st2.bind("333", "Yama7u7", "mania", "osu")
        st2.bind("333", "SomeSBPlayer", "osu", "sb")
        check("官服绑定独立", st2.username_for("333", "osu"), "Yama7u7")
        check("私服绑定独立", st2.username_for("333", "sb"), "SomeSBPlayer")
        check("私服绑定继承自己的 ruleset", st2.ruleset_for("333", "sb"), "osu")
        check("该 QQ 有两个服", st2.servers_for("333"), ["osu", "sb"])
        check("未绑定的 QQ 查不到", st2.username_for("444", "sb"), None)

        # 4) 落盘再读回，分服信息不能丢
        st3 = storemod.Store(tdp, cache_minutes=10)
        check("落盘后官服仍在", st3.username_for("333", "osu"), "Yama7u7")
        check("落盘后私服仍在", st3.username_for("333", "sb"), "SomeSBPlayer")
        check("落盘后 ruleset 仍在", st3.ruleset_for("222"), "taiko")

        # 5) 玩家缓存按服分开——否则官服查出的总 PP 会被私服查询命中
        st3.put_player("Yama7u7", "mania", {"pp": 21312}, "sb")
        st3.put_player("Yama7u7", "mania", {"pp": 99999}, "osu")
        check("私服缓存不串到官服",
              st3.cached_player("Yama7u7", "mania", "sb")["pp"], 21312)
        check("官服缓存不串到私服",
              st3.cached_player("Yama7u7", "mania", "osu")["pp"], 99999)

    # ── (f) Pillow 渲染器出图 ──────────────────────────────────────────
    spec = HERE.parent.parent.parent / "Cho Osu Bot" / "template" / "layer_mapping.json"
    if not spec.is_file():
        spec = Path(r"D:\Cho Osu Bot\template\layer_mapping.json")
    assets = Path(r"D:\Cho Osu Bot\template\assets")
    if spec.is_file() and assets.is_dir():
        rep = rendermod.fonts_report()
        missing = [r["font"] for r in rep if not r["found"]]
        check("模板字体全部解析到文件", missing, [])
        for r in rep[:3]:
            print(f"   {r['font']:22} -> {r['path']}")
        print(f"   ... 共 {len(rep)} 个字体")

        r = rendermod.PilScoreCardRenderer(spec, assets, HERE / "tests" / "out" / "work_pil")
        out = HERE / "tests" / "out" / "self_test_pil.png"
        jobs = [{"name": n, "value": v, "font": None, "accent": None}
                for n, v in data.to_layers().items()]
        res = r.render(jobs, [], r.signboard_chain(data.grade), out)
        img = Image.open(out).convert("RGB")
        hist = img.convert("L").histogram()
        spread = max(i for i, n in enumerate(hist) if n)
        darkest = min(i for i, n in enumerate(hist) if n)
        check("PIL 出图非空白", spread - darkest > 40, True)
        print(f"   PIL 渲染 {res['text']} 文字层，画布 {img.size}")
    else:
        print(f"  跳过 PIL 渲染：找不到 spec({spec}) 或 assets({assets})")


def stage_sb() -> None:
    """SB 私服：拿**真实抓下来的响应**离线跑一遍归一化 + 出卡。

    为什么要用真 fixture，而不是手写一个理想形状的字典
    ----------------------------------------------------
    这个项目已经被同一个模式坑过两次：
      - `total_pp` 那段，`_profile()` 返回的是**扁平**字典，而测试喂的是
        `{statistics: {pp}}`，于是测试通过、线上永远是 `--`。
      - 计分板导出那段，测试和实现各藏了一份名单，两边都"对"。
    教训是：测试必须走**生产同一个函数**，喂**生产真的会收到的东西**。

    所以这里 `tests/fixture_sb_score.json` 是从 api.ppy.sb 直接抓下来的原始响应
    （成绩 / 谱面 / 玩家资料三层都在里面），本函数只负责把它喂进
    `sb_api.score_to_osu()` 和 `card.build_card()` —— 也就是 main.py 里
    `_sb_score_bundle()` + `_score_card()` 真正走的那两个函数。整个测试不联网。
    """
    import json

    import card as cardmod
    import sb_api

    print("\n── 7. 私服（SB / ppy.sb，用抓下来的原始响应）")

    fx_path = HERE / "tests" / "fixture_sb_score.json"
    if not fx_path.is_file():
        print(f"  跳过 SB：找不到 {fx_path}")
        return
    fx = json.loads(fx_path.read_text(encoding="utf-8"))

    raw = fx["score"]
    map_layer = (fx.get("map_info") or {}).get("map") or {}
    # 注意这一行：fixture 存的是**响应原文**（带 {"status":"success", ...} 外壳），
    # 而 SbApi.player_info() 会替调用方脱掉 "player" 这一层。第一版这里直接用了
    # 外壳，`profile_to_osu` 于是拿不到 id/name，测试报出「资料归一化拿到名字 = None」
    # —— 这正是本节存在的意义：测试喂的形状必须和生产真收到的一致。
    player = (fx.get("player_info") or {}).get("player") or {}

    # ── (1) mod 位掩码解码。SB 给的是 stable 整数，官服给的是缩写列表 ──
    check("SB mods 是整数位掩码", isinstance(raw.get("mods"), int), True)
    check("SB 位掩码 64 -> DT", sb_api.decode_mods(64), ["DT"])
    check("SB 位掩码 0 -> 无 mod", sb_api.decode_mods(0), [])
    check("NC 存在时不重复报 DT", sb_api.decode_mods(512 | 64), ["NC"])
    check("键数 mod 被丢掉（4K=32768）", sb_api.decode_mods(32768), [])

    # ── (2) 脏数据：成绩内嵌的 beatmap.max_combo ≠ 谱面满连 ──
    embedded_combo = (raw.get("beatmap") or {}).get("max_combo")
    true_combo = map_layer.get("max_combo")
    check("内嵌 max_combo 确实是脏数据（等于玩家连击）",
          embedded_combo == raw.get("max_combo"), True)
    check("get_map_info 的满连与内嵌值不同", true_combo != embedded_combo, True)

    # ── (3) 归一化走生产函数 ──
    score, beatmap, beatmapset = sb_api.score_to_osu(raw, map_layer, "Yama7u7")
    check("归一化后打了私服标记", score.get("server"), "sb")
    check("谱面满连取到真值（不是内嵌值）", beatmap.get("max_combo"), true_combo)
    check("玩家连击保留原值", score.get("max_combo"), raw.get("max_combo"))
    check("总分来自 score 字段", score.get("total_score"), raw.get("score"))
    check("判定用 lazer 名", sorted(score["statistics"]),
          ["good", "great", "meh", "miss", "ok", "perfect"])
    check("判定总数 = 谱面物件数", sum(score["statistics"].values()),
          sum(beatmapset and [raw.get(k) or 0 for k in
                              ("ngeki", "n300", "nkatu", "n100", "n50", "nmiss")]))
    check("归一化刻意不设 accuracy（lazer 槽要另算）",
          "accuracy" in score, False)

    # ── (4) 出卡：喂生产同一个 build_card ──
    profile = sb_api.profile_to_osu(player, "mania")
    check("资料归一化拿到 id", profile.get("user_id"), 10859)
    check("资料归一化拿到名字", profile.get("username"), "Yama7u7")

    for mode in ("computed", "dash"):
        data = cardmod.build_card(score, beatmap, beatmapset, profile,
                                  pp_max_mode=mode)
        layers = {k: v for k, v in data.to_layers().items() if str(v).strip()}
        check(f"[{mode}] 卡片有内容", len(layers) > 15, True)
        check(f"[{mode}] 服务器标记是私服", layers.get("server_tag"), "SB 私服")
        check(f"[{mode}] 私服标记是青色", data.server_tag_color, "#4FC3F7")
        if mode == "computed":
            check("满连显示谱面真值",
                  layers.get("map_max_combo") or layers.get("max_combo"),
                  f"{true_combo:,}x")
            check("mod 倍率出现 x1.5", layers.get("mod_1_mult"), "x1.5")
            check("总 PP 不是空的", layers.get("total_pp"), f"{profile['total_pp']:,}pp")
            print(f"   私服卡：{len(layers)} 层有值 / 评级 {data.grade} / "
                  f"PP {layers.get('pp')} / ACC {layers.get('accuracy')}")
        else:
            print(f"   pp_max_mode=dash 时 pp_max = {layers.get('pp_max')!r}")

    # ── (5) 没传 map_info 的退化路径不能崩，也不能假装精确 ──
    s2, b2, _ = sb_api.score_to_osu(raw, None, "Yama7u7")
    check("无谱面详情时退回内嵌值（并等于玩家连击）",
          b2.get("max_combo"), embedded_combo)

    # ── (6) 两条接口的形状差异 —— 这一节就是抓到过真 bug 的那一节 ──
    #
    # 实测：get_player_scores 有内嵌 beatmap 但没 userid；
    #       get_score_info     有 userid 和 map_md5 但没 beatmap。
    # 只按其中一种写代码，另一个指令就会静默出空卡。
    alt = (fx.get("score_info") or {}).get("score") or {}
    check("两种形状确实不同（内嵌 beatmap）",
          "beatmap" in raw and "beatmap" not in alt, True)
    check("两种形状确实不同（userid）",
          "userid" not in raw and "userid" in alt, True)

    # `r -sb` 走 get_player_scores：md5 只能从内嵌 beatmap 里拿
    check("[形状A: r -sb] 谱面指纹取自内嵌 beatmap",
          sb_api.score_map_md5(raw), (raw.get("beatmap") or {}).get("md5"))
    check("[形状A: r -sb] 接口不给 userid，必须由调用方补",
          sb_api.score_user_id(raw), None)

    # `s <id> -sb` 走 get_score_info：md5 只能从 map_md5 拿，但 userid 有
    check("[形状B: s -sb] 谱面指纹取自 map_md5",
          sb_api.score_map_md5(alt), alt.get("map_md5"))
    check("[形状B: s -sb] 接口自带 userid",
          sb_api.score_user_id(alt), 10859)

    # `s <id> -sb` 的完整数据链：没有内嵌 beatmap 时，谱面信息必须全靠 map_info
    s_alt, b_alt, bs_alt = sb_api.score_to_osu(alt, map_layer, "Yama7u7")
    for key in ("id", "beatmapset_id", "difficulty_rating", "accuracy",
                "drain", "ar", "bpm", "max_combo", "version"):
        if b_alt.get(key) is None:
            check(f"[形状B] beatmap.{key} 不能为空", None, "有值")
    check("[形状B] 曲名非空", bool(bs_alt.get("title")), True)
    check("[形状B] 满连是真值", b_alt.get("max_combo"), true_combo)
    d_alt = cardmod.build_card(s_alt, b_alt, bs_alt, profile, pp_max_mode="dash")
    alt_layers = {k: v for k, v in d_alt.to_layers().items() if str(v).strip()}
    check("[形状B] 卡上曲名不是空的",
          str(alt_layers.get("beatmap_title") or "").strip() != "", True)
    check("[形状B] 卡上难度不是空的",
          str(alt_layers.get("beatmap_difficulty") or "").strip() != "", True)
    check("[形状B] 卡上谱师不是空的",
          str(alt_layers.get("beatmap_mapper") or "").strip() != "", True)
    check("[形状B] 卡上满连是谱面真值", alt_layers.get("map_max_combo"),
          f"{true_combo:,}x")
    print(f"   s -sb 形状出卡：曲名 {alt_layers.get('beatmap_title')!r} / "
          f"难度 {alt_layers.get('beatmap_difficulty')!r} / "
          f"满连 {alt_layers.get('map_max_combo')!r}")

    # ── (7) 官服这条路上服务器标记必须是「Lazer」（无 stable 标记时）──
    osu_score = dict(score)
    osu_score.pop("server", None)
    d_osu = cardmod.build_card(osu_score, beatmap, beatmapset, profile,
                               pp_max_mode="dash")
    check("官服标记是「Lazer」", d_osu.to_layers().get("server_tag"), "Lazer")
    check("官服标记是灰色", d_osu.server_tag_color, "#8C96A9")


# ─────────────────────────────── stage: map combo ───────────────────────────────

# MAP COMBO 那一格的期望值。写死在常量里（不放行内注释），自检对着它跑。
MAP_COMBO_EXPECTED = {
    "synthetic_notes": 5,
    "synthetic_holds": 2,
    "synthetic_combo": 9,
    "synthetic_missing_section": None,
    "synthetic_no_objects": None,
    "counted_slot": "2,432x",
    "counted_source": "osu_file",
    "fc_slot": "2,922x",
    "fc_source": "perfect_combo",
    "api_slot": "2,763x",
    "api_source": "api",
    "impossible_slot": "--",
    "impossible_source": "none",
    "empty_slot": "--",
    "empty_source": "none",
    "player_slot_when_absent": "--",
    "forbidden": "0x",
    "cache_combo": 2432,
    "cache_notes": 1184,
    "cache_holds": 624,
    "cache_file": "map_combo_cache.json",
}

# 两个真实谱面（文件是官服 osu.ppy.sh/osu/<bid> 的原样字节，md5 等于 API 的
# checksum）。stable 一栏是「数文件」的结果，也是不带 mod、is_perfect_combo 的
# 成绩在排行榜上实际打出来的连击；api 一栏是 API 给的 beatmap.max_combo，
# 那是 lazer 口径（长条连 ticks 一起算），两者对 mania 本来就不是一个数。
MAP_COMBO_FIXTURES = [
    {
        "bid": 5493536,
        "file": "fixture_beatmap_5493536.osu",
        "md5": "3449b5b02da2f821777d9940c8847dd2",
        "notes": 2034,
        "holds": 444,
        "stable_max_combo": 2922,
        "api_max_combo": 3243,
    },
    {
        "bid": 5327306,
        "file": "fixture_beatmap_5327306.osu",
        "md5": "f5bf50d635a01ebb6047de89ced76216",
        "notes": 1184,
        "holds": 624,
        "stable_max_combo": 2432,
        "api_max_combo": 2763,
    },
]


def stage_map_combo() -> None:
    """MAP COMBO：计数、降级顺序、缓存。全部离线。

    这一节盯的是线上那个真 bug：非满连的成绩，`beatmap.max_combo` 在官服返回里
    可以**整个字段都不存在**，旧代码 `.get("max_combo", 0)` 于是把 `0x` 印在卡上
    —— 一个看起来像数据的假数字。下面每一个分支都在检查「不许出现 0x」。

    真实谱面用冻结在 tests/ 里的 .osu（官服原样字节，md5 对得上 API 的 checksum），
    所以 2922 / 2432 这两个数是**离线可复现**的，不靠「当时网通」。
    """
    import hashlib
    import tempfile

    import card as cardmod
    import map_combo as map_combomod

    print("\n── 7b. 谱面满连（MAP COMBO）")

    # ── (1) 纯计数 ─────────────────────────────────────────────────────
    synthetic = (
        "osu file format v14\n"
        "\n"
        "[HitObjects]\n"
        + "64,192,100,1,0,0:0:0:0:\n" * (MAP_COMBO_EXPECTED["synthetic_notes"] - 1)
        + "64,192,200,5,0,0:0:0:0:\n"          # 5 = 1|4：普通键 + 新连击段，仍是 1 连
        + "64,192,300,128,0,400:0:0:0:0:\n" * (MAP_COMBO_EXPECTED["synthetic_holds"] - 1)
        + "64,192,900,128,0,1000:0:0:0:0:\n"
    )
    check("数出普通键与长条",
          cardmod.count_hit_objects(synthetic),
          (MAP_COMBO_EXPECTED["synthetic_notes"], MAP_COMBO_EXPECTED["synthetic_holds"]))
    check("满连 = 普通键 + 长条*2",
          cardmod.count_map_max_combo(synthetic), MAP_COMBO_EXPECTED["synthetic_combo"])
    check("没有 [HitObjects] -> None",
          cardmod.count_map_max_combo("osu file format v14\n[General]\n"),
          MAP_COMBO_EXPECTED["synthetic_missing_section"])
    check("有段落但没有物件 -> None",
          cardmod.count_map_max_combo("[HitObjects]\n\n\n"),
          MAP_COMBO_EXPECTED["synthetic_no_objects"])

    # ── (2) 真实谱面：文件没被改过、数得对、并且确实和 API 不是一个数 ──
    texts: dict[int, str] = {}
    for row in MAP_COMBO_FIXTURES:
        bid = row["bid"]
        path = HERE / "tests" / row["file"]
        if not path.is_file():
            FAILURES.append(f"缺少谱面 fixture: {path}")
            print(f"  FAIL  找不到 {path.name}")
            continue
        raw = path.read_bytes()
        text = raw.decode("utf-8", "replace")
        texts[bid] = text
        check(f"[bid {bid}] fixture 是官服原样字节（md5 = API checksum）",
              hashlib.md5(raw).hexdigest(), row["md5"])
        check(f"[bid {bid}] 物件数",
              cardmod.count_hit_objects(text), (row["notes"], row["holds"]))
        check(f"[bid {bid}] stable 满连（数文件）",
              cardmod.count_map_max_combo(text), row["stable_max_combo"])
        print(f"   bid {bid}: {row['notes']} 键 + {row['holds']} 长条 -> "
              f"{row['stable_max_combo']}  |  API 说 {row['api_max_combo']}（lazer 口径）")

    # ── (3) 降级顺序：喂生产同一个 build_card ──────────────────────────
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    real_score = payload["score"]
    real_map = real_score.get("beatmap") or {}

    def slot(sc: dict, bm: dict, counted):
        d = cardmod.build_card(sc, bm, payload.get("beatmapset") or {}, {},
                               pp_max_mode="dash", real_max_combo=counted)
        return d.to_layers().get("map_max_combo"), d.map_max_combo_source

    fc_slot, fc_src = slot(real_score, real_map, None)
    check("满连走玩家自己的连击", fc_slot, MAP_COMBO_EXPECTED["fc_slot"])
    check("满连的来源标成 perfect_combo", fc_src, MAP_COMBO_EXPECTED["fc_source"])

    nonfc = dict(real_score)
    nonfc["is_perfect_combo"] = False
    nonfc["max_combo"] = 1479

    # 官服那条路上的真实形状：内嵌 beatmap 里**没有** max_combo 这个键。
    # 旧代码在这里输出 "0x"，就是用户截图上的那个 bug。
    stripped = {k: v for k, v in real_map.items() if k != "max_combo"}
    check("[非满连] 内嵌 beatmap 确实没有 max_combo 键", "max_combo" in stripped, False)

    counted_slot, counted_src = slot(nonfc, stripped, MAP_COMBO_EXPECTED["cache_combo"])
    check("非满连时用数出来的满连", counted_slot, MAP_COMBO_EXPECTED["counted_slot"])
    check("来源标成 osu_file", counted_src, MAP_COMBO_EXPECTED["counted_source"])

    empty_slot, empty_src = slot(nonfc, stripped, None)
    check("数不出来又没有 API 值 -> --（不是 0x）",
          empty_slot, MAP_COMBO_EXPECTED["empty_slot"])
    check("来源标成 none", empty_src, MAP_COMBO_EXPECTED["empty_source"])

    api_slot, api_src = slot(nonfc, dict(stripped, max_combo=2763), None)
    check("数不出来时退回 API 值", api_slot, MAP_COMBO_EXPECTED["api_slot"])
    check("来源标成 api", api_src, MAP_COMBO_EXPECTED["api_source"])

    # 候选值不可能小于玩家已经打出来的连击 —— 那种值是错的，不能印。
    # 实测场景：bid 5327306 的 lazer 成绩连击 2757，stable 满连只有 2432。
    lazer = dict(nonfc, max_combo=2757)
    impossible_slot, impossible_src = slot(lazer, dict(stripped, max_combo=2763),
                                           MAP_COMBO_EXPECTED["cache_combo"])
    check("比玩家连击还小的候选被否决，退回 API 值",
          impossible_slot, f"{2763:,}x")
    check("两个候选都比玩家连击小 -> --（不硬凑一个数）",
          slot(lazer, stripped, MAP_COMBO_EXPECTED["cache_combo"]),
          (MAP_COMBO_EXPECTED["impossible_slot"], MAP_COMBO_EXPECTED["impossible_source"]))

    # 0 不是测量值：它必须被当成「没数」而不是「满连是 0」。
    check("real_max_combo=0 当成没数",
          slot(nonfc, stripped, 0), (MAP_COMBO_EXPECTED["empty_slot"],
                                     MAP_COMBO_EXPECTED["empty_source"]))
    check("beatmap.max_combo=0 也不会印成 0x",
          slot(nonfc, dict(stripped, max_combo=0), None),
          (MAP_COMBO_EXPECTED["empty_slot"], MAP_COMBO_EXPECTED["empty_source"]))

    # 玩家连击缺失时，玩家那一格也不能是 0x（同一个「假装有数据」的毛病）
    no_combo = dict(nonfc)
    no_combo.pop("max_combo", None)
    d_nc = cardmod.build_card(no_combo, dict(stripped, max_combo=2763),
                              payload.get("beatmapset") or {}, {}, pp_max_mode="dash")
    check("玩家连击缺失 -> --",
          d_nc.to_layers().get("max_combo"), MAP_COMBO_EXPECTED["player_slot_when_absent"])

    # ── (4) 任何一条路都不许输出 0x ────────────────────────────────────
    seen = [fc_slot, counted_slot, empty_slot, api_slot, impossible_slot,
            d_nc.to_layers().get("max_combo"),
            d_nc.to_layers().get("map_max_combo")]
    check("全部路径都没有出现 0x",
          MAP_COMBO_EXPECTED["forbidden"] in [str(v) for v in seen], False)

    # ── (5) 缓存：落盘、读回、过期、失败不写 ───────────────────────────
    import shutil
    tmp = Path(tempfile.mkdtemp())
    try:
        resolver = map_combomod.MapComboResolver(tmp)
        resolver.put(MAP_COMBO_FIXTURES[1]["bid"],
                     MAP_COMBO_EXPECTED["cache_combo"],
                     MAP_COMBO_EXPECTED["cache_notes"],
                     MAP_COMBO_EXPECTED["cache_holds"])
        check("缓存读回", resolver.cached(5327306), MAP_COMBO_EXPECTED["cache_combo"])
        check("缓存真的落盘了（重建实例仍在）",
              map_combomod.MapComboResolver(tmp).cached(5327306),
              MAP_COMBO_EXPECTED["cache_combo"])
        check("缓存写在 data 目录里，不在插件目录",
              (tmp / MAP_COMBO_EXPECTED["cache_file"]).is_file(), True)
        check("ttl=0 等于不缓存",
              map_combomod.MapComboResolver(tmp, ttl_days=0).cached(5327306), None)

        if 5327306 in texts:
            check("count_objects 的分解和缓存一致",
                  map_combomod.count_objects(texts[5327306]),
                  (MAP_COMBO_EXPECTED["cache_combo"],
                   MAP_COMBO_EXPECTED["cache_notes"],
                   MAP_COMBO_EXPECTED["cache_holds"]))

        # 下载失败必须返回 None 且**不写**缓存 —— 否则一次网络抖动会变成
        # 三十天的 "--"。
        import osu_api as osu_apimod
        original = osu_apimod.fetch_beatmap_file
        osu_apimod.fetch_beatmap_file = lambda *a, **k: (_ for _ in ()).throw(
            RuntimeError("self_test: 假装下载失败"))
        try:
            failing = map_combomod.MapComboResolver(tmp)
            check("下载失败 -> None", failing.resolve(999999999), None)
            check("下载失败不写缓存", failing.cached(999999999), None)
            check("失败留下了原因（供日志）", bool(failing.last_error), True)
        finally:
            osu_apimod.fetch_beatmap_file = original
        check("非数字 bid 直接拒绝，不发请求",
              map_combomod.MapComboResolver(tmp).resolve("not-a-number"), None)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # ── (6) 生产接线：两条短路必须真的不下载 ───────────────────────────
    #
    # 用真的插件类（按 AstrBot 的包内导入方式加载 main.py），不是替身 ——
    # 「满连不下载」「私服不下载」这两条短路只有跑真方法才算验过。
    # 判定标准是 `downloads` 必须为空：把下载换成会抛异常的替身，真发了就记下来。
    import asyncio
    import importlib.util
    import osu_api as osu_apimod
    import types as _types

    pkg_name = "_osucard_combo_selftest"
    pkg = _types.ModuleType(pkg_name)
    pkg.__path__ = [str(HERE)]
    sys.modules[pkg_name] = pkg
    main_spec = importlib.util.spec_from_file_location(f"{pkg_name}.main", HERE / "main.py")
    main_mod = importlib.util.module_from_spec(main_spec)
    sys.modules[f"{pkg_name}.main"] = main_mod
    try:
        main_spec.loader.exec_module(main_mod)
    except Exception as exc:  # noqa: BLE001
        FAILURES.append(f"[combo] main.py 无法导入: {type(exc).__name__}: {exc}")
        print(f"  FAIL  main.py 导入失败: {type(exc).__name__}: {exc}")
        return

    class _Ctx:
        async def send_message(self, umo, chain):
            return True

    tmp2 = Path(tempfile.mkdtemp())
    downloads: list = []
    original_fetch = osu_apimod.fetch_beatmap_file
    try:
        plugin = main_mod.OsuScoreCardPlugin(
            _Ctx(), {"osu_data_path": str(tmp2 / "x.psd")})
        plugin.data_dir = tmp2

        def _no_download(*args, **kwargs):
            downloads.append(args)
            raise AssertionError("self_test: 这条路径不该下载 .osu")

        osu_apimod.fetch_beatmap_file = _no_download
        check("[生产] 满连短路（不下载）",
              asyncio.run(plugin._counted_map_combo(real_score, real_map, "osu")), None)
        check("[生产] 私服短路（不下载）",
              asyncio.run(plugin._counted_map_combo(nonfc, stripped, "sb")), None)
        check("[生产] 短路时确实没发起下载", downloads, [])
    finally:
        osu_apimod.fetch_beatmap_file = original_fetch
        shutil.rmtree(tmp2, ignore_errors=True)


# ─────────────────────────────── stage: oauth ───────────────────────────────


def stage_oauth() -> None:
    """官服 OAuth 授权码流程。

    除了「用户在浏览器里真的点一次授权」这一步之外，全都真跑：真起 HTTP 服务、
    真发 HTTP 请求、真走回调处理、真落盘。两个必须联网的调用（exchange_code 和
    /me）换成替身 —— 它们需要真实的 code，而 code 只能从 osu! 的授权页拿到。

    所以这个 stage 能证明的是**接线是对的**，不能证明 osu! 那边的往返。
    """
    import asyncio
    import importlib.util
    import socket
    import tempfile
    import shutil
    import types
    import urllib.request
    import uuid

    import oauth as oauthmod
    import store as storemod

    print("\n── 8. 官服 OAuth（真实 HTTP 服务 + 真实回调）")

    # main.py speaks relative imports, so it has to be loaded inside a package —
    # same trick stage_plugin uses, under its own name so the two cannot collide.
    pkg_name = "_osucard_oauth_selftest"
    pkg = types.ModuleType(pkg_name)
    pkg.__path__ = [str(HERE)]
    sys.modules[pkg_name] = pkg
    spec = importlib.util.spec_from_file_location(f"{pkg_name}.main", HERE / "main.py")
    main_mod = importlib.util.module_from_spec(spec)
    sys.modules[f"{pkg_name}.main"] = main_mod
    try:
        spec.loader.exec_module(main_mod)
    except Exception as exc:  # noqa: BLE001
        FAILURES.append(f"[oauth] main.py 无法导入: {type(exc).__name__}: {exc}")
        print(f"  FAIL  main.py 导入失败: {type(exc).__name__}: {exc}")
        return

    def free_port() -> int:
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        return port

    class _FakeCtx:
        def __init__(self):
            self.sent = []

        async def send_message(self, umo, chain):
            self.sent.append((umo, chain))
            return True

    def _fake_client():
        calls: dict = {}

        class C:
            def authorize_url(self, redirect_uri, state, scope="public"):
                calls["redirect_uri"] = redirect_uri
                calls["state"] = state
                return ("https://osu.ppy.sh/oauth/authorize?client_id=999"
                        f"&redirect_uri={redirect_uri}&response_type=code"
                        f"&scope={scope}&state={state}")

            def exchange_code(self, code, redirect_uri):
                calls["code"] = code
                calls["exchange_redirect"] = redirect_uri
                return {"access_token": "AT-" + uuid.uuid4().hex[:8],
                        "refresh_token": "RT-1", "expires_at": 9999999999.0,
                        "expires_in": 86400}

            def get(self, endpoint, params=None, token=None):
                calls["me_token"] = token
                return {"id": 32749965, "username": "F6A8AF"}

            def refresh_user_token(self, refresh_token):
                calls["refreshed"] = refresh_token
                return {"access_token": "AT-new", "refresh_token": "RT-2",
                        "expires_at": 9999999999.0, "expires_in": 86400}

        return C(), calls

    async def run() -> None:
        tmp = Path(tempfile.mkdtemp())
        port = free_port()
        try:
            # state 表
            pend = oauthmod.PendingAuth(tmp / "p.json", ttl=600)
            st = oauthmod.new_state()
            check("state 不是 QQ 号本身", st != "12345" and len(st) > 20, True)
            pend.put(st, "12345", "umo", "mania")
            check("pending 记下了谁在等", (pend.peek(st) or {}).get("qq"), "12345")
            pend.take(st)
            check("take 之后不可重放", pend.peek(st), None)
            pend.put("s2", "999", "umo2", "osu")
            check("pending 落盘重载",
                  (oauthmod.PendingAuth(tmp / "p.json", ttl=600).peek("s2") or {}).get("qq"),
                  "999")

            # redirect_uri
            check("redirect_uri 拼接",
                  oauthmod.redirect_uri("http://a.b"), "http://a.b/oauth/callback")
            check("尾斜杠不产生双斜杠",
                  oauthmod.redirect_uri("http://a.b/"), "http://a.b/oauth/callback")

            # 端到端
            ctx = _FakeCtx()
            plugin = main_mod.OsuScoreCardPlugin(ctx, {
                "osu_data_path": str(tmp / "x.psd"),
                "oauth_callback_host": "127.0.0.1",
                "oauth_callback_port": port,
            })
            plugin.data_dir = tmp
            plugin.store = storemod.Store(tmp, cache_minutes=10)
            plugin._pending = oauthmod.PendingAuth(tmp / "p2.json", ttl=600)
            client, calls = _fake_client()
            plugin._api = client  # 跳过真凭据，也就不用联网

            ok, reason = await plugin._ensure_oauth_server()
            check("回调服务启动", ok, True)
            check("监听地址", plugin.oauth_redirect_uri ==
                  f"http://127.0.0.1:{port}/oauth/callback", True)

            plugin.store.bind("12345", "F6A8AF", "mania", "osu")
            link = plugin._oauth_link("12345", "webchat:FriendMessage:abc", "mania")
            check("链接是 osu! 授权页", link.startswith("https://osu.ppy.sh/oauth/authorize?"), True)
            check("链接带 state", "state=" in link, True)
            check("redirect_uri 与配置一致", calls.get("redirect_uri"),
                  f"http://127.0.0.1:{port}/oauth/callback")
            state = calls.get("state")

            url = f"http://127.0.0.1:{port}/oauth/callback?code=THECODE&state={state}"
            body = await asyncio.to_thread(
                lambda: urllib.request.urlopen(url, timeout=10).read().decode("utf-8"))
            check("回调返回页面", "<html" in body.lower(), True)
            check("页面说授权完成", "授权完成" in body, True)
            check("页面不含令牌", ("AT-" not in body) and ("RT-" not in body), True)
            check("页面不含 code", "THECODE" not in body, True)
            check("code 传给了 exchange", calls.get("code"), "THECODE")
            check("exchange 用同一个 redirect_uri",
                  calls.get("exchange_redirect"),
                  f"http://127.0.0.1:{port}/oauth/callback")

            rec = plugin.store.oauth_for("12345", "osu") or {}
            check("令牌已落盘", rec.get("refresh_token"), "RT-1")
            check("user_id 已记录", rec.get("user_id"), 32749965)
            check("用户名来自 /me", plugin.store.username_for("12345", "osu"), "F6A8AF")
            check("确认消息已发出", len(ctx.sent), 1)

            # 拒绝路径
            b2 = await asyncio.to_thread(lambda: urllib.request.urlopen(
                f"http://127.0.0.1:{port}/oauth/callback?code=X&state=WRONG",
                timeout=10).read().decode("utf-8"))
            check("错误 state 被拒", ("失效" in b2) or ("无效" in b2), True)
            b3 = await asyncio.to_thread(lambda: urllib.request.urlopen(
                f"http://127.0.0.1:{port}/oauth/callback?code=X&state={state}",
                timeout=10).read().decode("utf-8"))
            check("同一 state 不能复用", ("失效" in b3) or ("无效" in b3), True)
            b4 = await asyncio.to_thread(lambda: urllib.request.urlopen(
                f"http://127.0.0.1:{port}/oauth/callback", timeout=10).read().decode("utf-8"))
            check("缺参数被拒", "参数" in b4, True)
            st2 = oauthmod.new_state()
            plugin._pending.put(st2, "12345", "umo", "mania")
            b5 = await asyncio.to_thread(lambda: urllib.request.urlopen(
                f"http://127.0.0.1:{port}/oauth/callback?error=access_denied&state={st2}",
                timeout=10).read().decode("utf-8"))
            check("识别用户取消", "取消" in b5, True)

            # 令牌刷新（osu! 每次刷新都会换新的 refresh_token，旧的作废）
            plugin.store.set_oauth("12345", {"access_token": "OLD", "refresh_token": "RT-old",
                                             "expires_at": 1.0, "user_id": 32749965}, "osu")
            tok = await plugin._user_token("12345", "mania")
            check("过期自动刷新", tok, "AT-new")
            check("刷新用了旧 refresh_token", calls.get("refreshed"), "RT-old")
            check("写回了新的 refresh_token（否则下次永久失效）",
                  (plugin.store.oauth_for("12345", "osu") or {}).get("refresh_token"), "RT-2")
            plugin.store.set_oauth("12345", {"access_token": "FRESH", "refresh_token": "RT-x",
                                             "expires_at": 9999999999.0}, "osu")
            check("未过期直接用缓存", await plugin._user_token("12345", "mania"), "FRESH")
            check("没绑定的人返回 None", await plugin._user_token("99999", "mania"), None)

            # 文案。链接现在由 _send_oauth_link 单独发一条（这样那条才能定时
            # 撤回），所以说明文字里**不该**再出现链接。
            reply = plugin._needs_auth_reply("F6A8AF", True, "")
            check("说明里不再内嵌链接", "osu.ppy.sh/oauth/authorize" not in reply, True)
            check("说明里点明下面会单独发链接", "授权链接" in reply, True)
            check("提示说明替代方案", "s <成绩ID>" in reply, True)
            check("提示不含令牌", ("AT-" not in reply) and ("RT-" not in reply), True)
            reply2 = plugin._needs_auth_reply("F6A8AF", False, "端口被占用")
            check("服务不可用时说明原因", "端口被占用" in reply2, True)
            check("服务不可用时不给链接", "oauth/authorize" not in reply2, True)

            # 文案里的撤回秒数必须和配置一致，不能再说「15 分钟内有效」
            plugin.config["oauth_recall_seconds"] = 30
            link_reply = plugin._oauth_link_reply("12345", "umo", "mania", True, "")
            check("链接文案说 30 秒后撤回", "30 秒后自动撤回" in link_reply, True)
            check("链接文案不再提 15 分钟", "15 分钟" not in link_reply, True)
            check("链接文案里确实有链接",
                  "osu.ppy.sh/oauth/authorize" in link_reply, True)
            plugin.config["oauth_recall_seconds"] = 0
            check("撤回关掉时改回说有效期",
                  "15 分钟" in plugin._oauth_link_reply("12345", "umo", "mania", True, ""),
                  True)
            plugin.config["oauth_recall_seconds"] = 30

            # 停止 + 端口占用
            await plugin._oauth_server.stop()
            check("停止后不再监听", plugin._oauth_server.started, False)
            sock = socket.socket()
            sock.bind(("127.0.0.1", port))
            sock.listen(1)
            try:
                plugin._oauth_server = None
                ok2, reason2 = await plugin._ensure_oauth_server()
                check("端口被占用时给可读原因", (not ok2) and ("端口" in reason2), True)
            finally:
                sock.close()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    asyncio.run(run())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--render", action="store_true", help="额外跑一次真实 Photoshop 渲染")
    ap.add_argument("--full", action="store_true",
                    help="全量渲染：含背景、头像、mod 徽章、辉光（需要联网）")
    ap.add_argument("--only",
                    choices=["map", "raster", "render", "full", "plugin", "sb",
                             "combo", "oauth", "grade", "history"],
                    default=None)
    ap.add_argument("--template", default=r"D:\Cho Osu Bot\template\osu_score_template_v2.psd")
    ap.add_argument("--assets", default=r"D:\Cho Osu Bot\template\assets")
    args = ap.parse_args()

    print(f"self_test  python={sys.version.split()[0]}\n")
    if args.only in (None, "history"):
        import unittest
        suite = unittest.defaultTestLoader.discover(str(HERE / "tests"), pattern="test_history_commands.py")
        if not unittest.TextTestRunner(verbosity=1).run(suite).wasSuccessful():
            FAILURES.append("记录库与指令回归测试失败")
    if args.only in (None, "map", "grade"):
        import unittest
        suite = unittest.defaultTestLoader.discover(str(HERE / "tests"), pattern="test_grades.py")
        if not unittest.TextTestRunner(verbosity=1).run(suite).wasSuccessful():
            FAILURES.append("评级回归测试失败")
    # The raster and render stages both need the mapped card, so the mapping stage
    # always runs first — it is pure and takes milliseconds.
    info = stage_mapping() if args.only in (None, "map", "raster", "full") else {}
    if args.only in (None, "raster"):
        stage_rasters(info)
    if args.only == "render" or (args.render and args.only is None):
        if not info:
            info = stage_mapping()
        stage_render(info, Path(args.template), Path(args.assets))
    if args.only == "full" or (args.full and args.only is None):
        if not info:
            info = stage_mapping()
        stage_render_full(info, Path(args.template), Path(args.assets))
    if args.only in (None, "plugin"):
        stage_plugin()
    if args.only in (None, "new"):
        stage_new_engines(info)
    if args.only in (None, "sb"):
        stage_sb()
    if args.only in (None, "combo"):
        stage_map_combo()
    if args.only in (None, "oauth"):
        stage_oauth()

    print()
    if FAILURES:
        print(f"✗ {len(FAILURES)} 项失败：")
        for f in FAILURES:
            print("   -", f)
        return 1
    print("✓ 全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
