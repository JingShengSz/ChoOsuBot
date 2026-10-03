#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
谱面ID → osu-malody 知识库 谱面/*.md 生成器

架构参考 yumu-bot (https://github.com/yumu-bot/yumu-bot):
  - HitObjectType 位标志: CIRCLE=1 / SLIDER=2 / SPINNER=8 / LONGNOTE=128
  - Timing 红线: bpm = 60000 / beatLength（未继承）
  - Beatmap.totalNotes = circles + sliders (+ spinners)
  - .osu 来源: https://osu.ppy.sh/osu/{bid}（yumu-bot getBeatmapFileFromOfficialWebsite）
  - 元数据: sayobot get_beatmaps（字段对齐官方 API v2 Beatmap/Beatmapset）

用法：
  python beatmap_md.py 1945566              # 曲包ID → 整包 mania 难度
  python beatmap_md.py --bid 4025150        # 谱面ID → 该难度（仍按整包结构输出）
  python beatmap_md.py 1430396 -o ./out
  python beatmap_md.py 1222586 --dry-run
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# 常量（对齐 yumu-bot）
# ---------------------------------------------------------------------------

# HitObjectType.kt
HIT_CIRCLE = 1
HIT_SLIDER = 2
HIT_SPINNER = 8
HIT_LONGNOTE = 128

OSU_FILE_URL = "https://osu.ppy.sh/osu/{bid}"  # BeatmapApiImpl.getBeatmapFileFromOfficialWebsite
SAYO_API = "https://api.sayobot.cn/ppy/get_beatmaps"

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) beatmap-md/1.1 (yumu-bot-ref)"

# Beatmap.status → 知识库中文
STATUS_CN = {
    "ranked": "Ranked已上架",
    "approved": "Approved已上架",
    "qualified": "Qualified待上架",
    "loved": "Loved社区喜爱",
    "pending": "Pending",
    "wip": "WIP",
    "graveyard": "Graveyard坟场",
    # sayobot approved 数字
    "1": "Ranked已上架",
    "2": "Approved已上架",
    "3": "Qualified待上架",
    "4": "Loved社区喜爱",
    "0": "Pending",
    "-1": "WIP",
    "-2": "Graveyard坟场",
}

TAG_STOPWORDS = {
    "the", "and", "or", "of", "to", "in", "on", "for", "a", "an",
    "song", "songs", "map", "maps", "beatmap", "set", "ver", "ver.",
    "feat", "feat.", "ft", "ft.", "vs", "vs.",
}

WIN_BAD = re.compile(r'[\\/:*?"<>|\r\n]+')


# ---------------------------------------------------------------------------
# HTTP（本机 Python 直连部分站点 TLS 不稳，优先 urllib，失败走 curl.exe）
# ---------------------------------------------------------------------------


def _curl(args: list[str], timeout: int = 60) -> bytes:
    cmd = ["curl.exe", "-sS", "--fail-with-body", "--max-time", str(timeout),
           "-A", USER_AGENT, *args]
    proc = subprocess.run(cmd, capture_output=True, timeout=timeout + 5)
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", "replace").strip()
        raise RuntimeError(f"curl 失败 ({proc.returncode}): {err or 'unknown'}")
    return proc.stdout


def http_get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.read().decode("utf-8", "replace")
    except Exception:
        return _curl(["-L", url]).decode("utf-8", "replace")


def http_json(url: str):
    return json.loads(http_get(url))


# ---------------------------------------------------------------------------
# yumu-bot 风格数据模型
# ---------------------------------------------------------------------------


@dataclass
class Timing:
    """对齐 model/beatmapParse/Timing.kt — 只保留红线 BPM 计算。"""
    start_time: int
    beat_length: float
    is_red_line: bool

    @property
    def bpm(self) -> float:
        if self.beat_length <= 0:
            return 0.0
        return 60000.0 / self.beat_length


@dataclass
class HitObject:
    """对齐 model/beatmapParse/HitObject.kt + HitObjectType。"""
    type_flags: int
    start_time: int
    end_time: int
    x: int = 0

    @property
    def is_longnote(self) -> bool:
        return (self.type_flags & HIT_LONGNOTE) != 0

    @property
    def is_circle(self) -> bool:
        # mania 里 CIRCLE=单点；注意 LONGNOTE 位优先（yumu-bot getType 顺序）
        return (self.type_flags & HIT_CIRCLE) != 0 and not self.is_longnote


@dataclass
class OsuBeatmapAttributes:
    """对齐 model/beatmapParse/parse/OsuBeatmapAttributes.kt 的必要字段。"""
    cs: float = 0.0
    od: float = 0.0
    ar: float = 0.0
    hp: float = 0.0
    mode: int = 0
    title: str = ""
    artist: str = ""
    creator: str = ""
    version: str = ""
    tags: str = ""
    beatmap_id: str = ""
    beatmapset_id: str = ""
    timings: list[Timing] = field(default_factory=list)
    hit_objects: list[HitObject] = field(default_factory=list)

    @property
    def circle_count(self) -> int:  # 单点
        return sum(1 for h in self.hit_objects if h.is_circle)

    @property
    def longnote_count(self) -> int:  # 长条
        return sum(1 for h in self.hit_objects if h.is_longnote)

    @property
    def total_notes(self) -> int:
        # Beatmap.kt totalNotes：manía = circles + sliders(+spinners)
        return len(self.hit_objects)

    @property
    def red_line_bpms(self) -> list[float]:
        return [t.bpm for t in self.timings if t.is_red_line and t.beat_length > 0]

    @property
    def length_ms(self) -> int:
        if not self.hit_objects:
            return 0
        return max(h.end_time for h in self.hit_objects) - min(h.start_time for h in self.hit_objects)

    @property
    def keys(self) -> int:
        return max(1, int(round(self.cs)))


@dataclass
class BeatmapLite:
    """对齐 entity/BeatmapLite.kt：API 元数据 + 解析补充。"""
    beatmap_id: str = ""
    beatmapset_id: str = ""
    difficulty_name: str = ""
    creator: str = ""
    status: str = ""
    star_rating: float = 0.0
    bpm: float = 0.0
    cs: float = 0.0
    od: float = 0.0
    circles: int = 0          # 单点
    sliders: int = 0          # 长条 (mania LN = count_slider)
    total_length: int = 0     # 秒
    tags: str = ""
    mode: str = "mania"
    # 解析补充
    bpm_min: float | None = None
    bpm_max: float | None = None
    rice: int = 0
    ln: int = 0


@dataclass
class BeatmapsetLite:
    title: str = ""
    artist: str = ""
    creator: str = ""
    tags: str = ""
    beatmapset_id: str = ""
    beatmaps: list[BeatmapLite] = field(default_factory=list)


# ---------------------------------------------------------------------------
# .osu 解析（对齐 OsuBeatmapAttributes.parseHitObject / parseTiming）
# ---------------------------------------------------------------------------


def parse_osu(text: str) -> OsuBeatmapAttributes:
    attr = OsuBeatmapAttributes()
    section = ""
    meta: dict[str, str] = {}
    diff: dict[str, str] = {}

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("//"):
            continue
        m = re.match(r"^\[([A-Za-z0-9]+)\]$", line)
        if m:
            section = m.group(1)
            continue

        if section in ("General", "Metadata", "Difficulty") and ":" in line:
            k, _, v = line.partition(":")
            k, v = k.strip(), v.strip()
            if section == "Metadata":
                meta[k] = v
            elif section == "Difficulty":
                diff[k] = v
            elif section == "General":
                meta[k] = v
            continue

        if section == "TimingPoints":
            # entity.size >= 8，对齐 parseTiming
            parts = line.split(",")
            if len(parts) < 7:
                continue
            try:
                start = int(float(parts[0]))
                beat_len = float(parts[1])
                # yumu-bot: entity[6].toBoolean() → "1"/"true"
                red = parts[6].strip() in ("1", "true", "True")
            except ValueError:
                continue
            attr.timings.append(Timing(start, beat_len, red))
            continue

        if section == "HitObjects":
            # x,y,time,type,hitSound,objectParams...
            parts = line.split(",")
            if len(parts) < 4:
                continue
            try:
                x = int(parts[0])
                start = int(parts[2])
                flags = int(parts[3])
            except ValueError:
                continue
            end = start
            if flags & HIT_LONGNOTE and len(parts) >= 6:
                # LONGNOTE endTime = entity[5].split(":")[0]
                try:
                    end = int(parts[5].split(":")[0])
                except ValueError:
                    end = start
            elif flags & HIT_SPINNER and len(parts) >= 6:
                try:
                    end = int(parts[5].split(":")[0])
                except ValueError:
                    end = start
            attr.hit_objects.append(HitObject(flags, start, end, x))
            continue

    attr.mode = int(meta.get("Mode", "0") or 0)
    attr.title = meta.get("Title", "")
    attr.artist = meta.get("Artist", "")
    attr.creator = meta.get("Creator", "")
    attr.version = meta.get("Version", "")
    attr.tags = meta.get("Tags", "")
    attr.beatmap_id = meta.get("BeatmapID", "")
    attr.beatmapset_id = meta.get("BeatmapSetID", "")
    try:
        attr.cs = float(diff.get("CircleSize", 0) or 0)
    except ValueError:
        attr.cs = 0.0
    try:
        attr.od = float(diff.get("OverallDifficulty", 0) or 0)
    except ValueError:
        attr.od = 0.0
    try:
        attr.ar = float(diff.get("ApproachRate", 0) or 0)
    except ValueError:
        attr.ar = 0.0
    try:
        attr.hp = float(diff.get("HPDrainRate", 0) or 0)
    except ValueError:
        attr.hp = 0.0
    return attr


def fetch_osu_file(bid: str) -> str | None:
    """对齐 getBeatmapFileFromOfficialWebsite：https://osu.ppy.sh/osu/{bid}"""
    try:
        text = http_get(OSU_FILE_URL.format(bid=bid))
    except Exception as exc:
        print(f"[warn] 下载 .osu 失败 bid={bid}: {exc}", file=sys.stderr)
        return None
    # 校验：yumu-bot 检查是否以 osu file format 开头
    idx = text.find("osu file format")
    if idx < 0:
        print(f"[warn] bid={bid} 返回内容不是 .osu", file=sys.stderr)
        return None
    return text[idx:] if idx else text


# ---------------------------------------------------------------------------
# 元数据（sayobot 字段对齐官方 API v2 Beatmap）
# ---------------------------------------------------------------------------


def fetch_meta_sayobot(*, sid: str | None = None, bid: str | None = None) -> list[dict]:
    url = f"{SAYO_API}?s={sid}" if sid else f"{SAYO_API}?b={bid}"
    data = http_json(url)
    if not isinstance(data, list) or not data:
        raise RuntimeError(f"sayobot 无结果: {url}")
    return data


def meta_to_beatmaplite(row: dict) -> BeatmapLite:
    def fnum(key, default=0.0):
        try:
            return float(row.get(key) or default)
        except (TypeError, ValueError):
            return default

    def inum(key, default=0):
        try:
            return int(float(row.get(key) or default))
        except (TypeError, ValueError):
            return default

    status = str(row.get("approved") or row.get("status") or "")
    return BeatmapLite(
        beatmap_id=str(row.get("beatmap_id") or ""),
        beatmapset_id=str(row.get("beatmapset_id") or ""),
        difficulty_name=str(row.get("version") or ""),
        creator=str(row.get("creator") or ""),
        status=status,
        star_rating=fnum("difficultyrating"),
        bpm=fnum("bpm"),
        cs=fnum("diff_size", 4),
        od=fnum("diff_overall"),
        circles=inum("count_normal"),
        sliders=inum("count_slider"),
        total_length=inum("total_length"),
        tags=str(row.get("tags") or ""),
        mode="mania" if str(row.get("mode")) == "3" else str(row.get("mode")),
    )


def pick_mania(rows: list[dict], only_bid: str | None) -> list[dict]:
    mania = [r for r in rows if str(r.get("mode", "")) == "3"]
    if not mania:
        raise RuntimeError("该曲包没有 mania 难度")
    if only_bid:
        hit = [r for r in mania if str(r.get("beatmap_id")) == str(only_bid)]
        return hit or mania
    return mania


# ---------------------------------------------------------------------------
# 显示格式
# ---------------------------------------------------------------------------


def fmt_num(x, decimals: int = 2) -> str:
    if x is None:
        return "?"
    try:
        v = float(x)
    except (TypeError, ValueError):
        return "?"
    s = f"{v:.{decimals}f}".rstrip("0").rstrip(".")
    return s if s else "0"


def fmt_duration(seconds) -> str:
    if seconds is None:
        return "?"
    sec = int(round(float(seconds)))
    return f"{sec // 60}:{sec % 60:02d}"


def fmt_ln_ratio(rice: int, ln: int) -> tuple[str, int]:
    total = rice + ln
    if total <= 0:
        return "0%", 0
    pct = ln * 100.0 / total
    return fmt_num(pct, 1) + "%", int(round(pct))


def clean_tag_token(tok: str) -> str | None:
    t = tok.strip()
    if not t:
        return None
    t = re.sub(r"[・·•‧]", "", t).strip(" ,;|/")
    if not t or re.fullmatch(r"\d+", t):
        return None
    if t.casefold() in TAG_STOPWORDS:
        return None
    if len(t) < 2 and not re.search(r"[぀-ヿ一-鿿]", t):
        return None
    return t


def build_tags(raw_tags: str, keys: int, bpm_main: float | None, ln_tag: int) -> str:
    tokens: list[str] = []
    seen: set[str] = set()

    def push(t: str) -> None:
        key = t.casefold()
        if key in seen:
            return
        seen.add(key)
        tokens.append(t)

    push(f"{keys}k")
    if bpm_main is not None:
        push(f"bpm={int(round(bpm_main))}")
    push(f"ln={ln_tag}")
    for raw in (raw_tags or "").split():
        t = clean_tag_token(raw)
        if t:
            push(t)
    tokens.sort(key=lambda s: (s.casefold(), s))
    return " ".join(f"#{t}" for t in tokens)


def safe_filename(title: str) -> str:
    return (WIN_BAD.sub("_", title).strip().strip(". ") or "unknown")


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


def build_from_id(sid: str | None, bid: str | None) -> tuple[str, str, list[BeatmapLite], BeatmapsetLite]:
    rows = fetch_meta_sayobot(sid=sid, bid=bid)
    rows = pick_mania(rows, only_bid=bid)

    head = rows[0]
    set_info = BeatmapsetLite(
        title=str(head.get("title") or ""),
        artist=str(head.get("artist") or ""),
        creator=str(head.get("creator") or ""),
        tags=str(head.get("tags") or ""),
        beatmapset_id=str(head.get("beatmapset_id") or (sid or "")),
    )
    # 集级标签稍后用 .osu Metadata.Tags 覆盖（保留大小写）

    def star_key(r: dict) -> float:
        try:
            return float(r.get("difficultyrating") or 0)
        except (TypeError, ValueError):
            return 0.0

    resolved: list[BeatmapLite] = []

    for row in sorted(rows, key=star_key):
        b = meta_to_beatmaplite(row)
        rice, ln = b.circles, b.sliders

        # 逐难度拉 .osu（yumu-bot: getBeatmapFileString）
        text = fetch_osu_file(b.beatmap_id) if b.beatmap_id else None
        attr = parse_osu(text) if text else None

        if attr and attr.mode == 3:
            rice, ln = attr.circle_count, attr.longnote_count
            red = attr.red_line_bpms
            if red:
                # 范围来自红线 Timing（yumu-bot Timing.bpm = 60000/beatLength）
                b.bpm_min, b.bpm_max = min(red), max(red)
                # 主 BPM 保留 API 值（知识库同款）；API 缺失时才用红线众数
                if not b.bpm:
                    cnt = Counter(round(x, 1) for x in red)
                    best, _ = cnt.most_common(1)[0]
                    top = [x for x, c in cnt.items() if c == cnt[best]]
                    b.bpm = min(top, key=lambda x: abs(x - (b.bpm or best))) if top else best
            if attr.cs:
                b.cs = attr.cs
            if attr.od:
                b.od = attr.od
            if not b.difficulty_name:
                b.difficulty_name = attr.version
            if not b.creator:
                b.creator = attr.creator
            if not b.total_length and attr.length_ms:
                b.total_length = int(round(attr.length_ms / 1000.0))
            # .osu Tags 保留原始大小写，优先于 sayobot 小写 tags
            if attr.tags.strip():
                b.tags = attr.tags.strip()
                if set_info.tags.strip() in ("", b.tags) or set_info.tags == str(head.get("tags") or ""):
                    set_info.tags = attr.tags.strip()

        b.rice, b.ln = rice, ln
        if not b.tags:
            b.tags = set_info.tags
        resolved.append(b)

    if not resolved:
        raise RuntimeError("没有可写入的 mania 难度")

    add_date = datetime.now().strftime("%Y-%m-%d %H:%M")
    md = render_md(set_info, resolved, add_date)
    return safe_filename(set_info.title), md, resolved, set_info


def render_md(set_info: BeatmapsetLite, diffs: list[BeatmapLite], add_date: str) -> str:
    lines: list[str] = []
    lines.append(f"# {set_info.title or 'Unknown'}")
    lines.append("")
    lines.append(f"> 谱面集 | 曲师：{set_info.artist or 'Unknown'} | 模式：mania")
    lines.append(f"> 谱师/打包者：{set_info.creator or 'Unknown'}")
    if set_info.tags.strip():
        lines.append(f"> 谱面标签：{set_info.tags.strip()}")
    lines.append(f"> 添加日期：{add_date} | 曲包ID：{set_info.beatmapset_id or '?'}")
    lines.append("")
    lines.append("**标签：** #谱面 #mania")
    lines.append("")

    for d in diffs:
        rice, ln = d.rice, d.ln
        total = rice + ln
        ln_display, ln_tag = fmt_ln_ratio(rice, ln)

        if d.bpm_min is not None and d.bpm_max is not None:
            bpm_display = (
                f"{fmt_num(d.bpm, 1)}"
                f"（{fmt_num(d.bpm_min, 1)}~{fmt_num(d.bpm_max, 1)}）"
            )
        else:
            v = fmt_num(d.bpm, 1)
            bpm_display = f"{v}（{v}~{v}）" if d.bpm else "?（?~?）"

        status_cn = STATUS_CN.get(str(d.status).lower(), STATUS_CN.get(str(d.status), d.status or "?"))
        mapper = d.creator or set_info.creator
        keys = max(1, int(round(d.cs or 4)))
        tags_src = (d.tags or set_info.tags or "").strip()

        lines.append(f"## {d.difficulty_name or d.beatmap_id}")
        lines.append("")
        lines.append(f"- 时长：{fmt_duration(d.total_length)}")
        lines.append(f"- 物量：{total}（单点 {rice} + 长条 {ln}）")
        lines.append(f"- LN比例：{ln_display}")
        lines.append(f"- BPM：{bpm_display}")
        lines.append(f"- 星级：{fmt_num(d.star_rating, 2)} | CS：{fmt_num(d.cs, 1)} | OD：{fmt_num(d.od, 1)}")
        lines.append(f"- 谱面ID：{d.beatmap_id}")
        lines.append(f"- 谱师：{mapper}")
        lines.append(f"- Rank状态：{status_cn}")
        if tags_src:
            lines.append(f"- 谱面标签：{tags_src}")
        lines.append(f"**标签：** {build_tags(tags_src, keys, d.bpm if d.bpm else None, ln_tag)}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="按谱面/曲包 ID 生成知识库谱面 md（参考 yumu-bot）")
    p.add_argument("id", nargs="?", help="曲包ID（beatmapset id）")
    p.add_argument("--bid", help="谱面ID（beatmap id）")
    p.add_argument("-o", "--out", default="out", help="输出目录（默认 ./out）")
    p.add_argument("--dry-run", action="store_true", help="只打印 markdown，不写文件")
    args = p.parse_args(argv)

    if not args.id and not args.bid:
        p.error("请给出曲包ID，或使用 --bid 谱面ID")

    sid = args.id
    bid = args.bid
    try:
        if bid and not sid:
            stem, md, diffs, set_info = build_from_id(sid=None, bid=bid)
        else:
            stem, md, diffs, set_info = build_from_id(sid=sid, bid=bid)
    except Exception as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1

    print(f"# {set_info.title}  (曲包ID {set_info.beatmapset_id}, {len(diffs)} 个 mania 难度)")
    for d in diffs:
        print(
            f"  - [{fmt_num(d.star_rating, 2)}] {d.difficulty_name}  bid={d.beatmap_id}  "
            f"物量={d.rice + d.ln}（{d.rice}+{d.ln}）  "
            f"BPM={fmt_num(d.bpm, 1)}（{fmt_num(d.bpm_min, 1)}~{fmt_num(d.bpm_max, 1)}）"
        )

    if args.dry_run:
        print()
        print(md)
        return 0

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{stem}.md"
    out_path.write_text(md, encoding="utf-8")
    print(f"\n已写入: {out_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
