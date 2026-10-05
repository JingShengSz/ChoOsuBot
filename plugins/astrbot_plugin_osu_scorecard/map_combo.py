"""谱面真实满连：把 .osu 下下来自己数，并缓存结果。

为什么要下载 .osu，而不是信 API
-------------------------------
`beatmap.max_combo` 对 mania 是**lazer 口径**：长条的头、尾、以及中间的 hold
ticks 都算连击。stable 口径只有「普通键 1 连 + 长条 2 连」。

实测（2026-10，两个谱面、官服 API + 两个谱面的排行榜）：

    bid      notes  holds  这里(数文件)  API    榜单上的 stable 满连   lazer "CL" 成绩
    5493536   2034    444      2922       3243   2922 (is_perfect_combo)   3243
    5327306   1184    624      2432       2763   2432 (is_perfect_combo)   2757+

5327306 这条把话说死了：**不带 mod、`is_perfect_combo = true`** 的成绩恰好是
2432，而 lazer 的 CL 成绩能到 2757，API 给 2763。两边都是「对的数」，只是规则
不同。卡片显示的是 stable 成绩的连击，所以它要的是 stable 那个最大值 ——
也就是数文件数出来的这个。

yumu-bot（Rust / rosu-pp）走的是同一条路：下载谱面本体自己算，而不是信 API 的
数字；它也带一个 BeatmapStarRatingCache，说明「算了就存下来」。本模块就是那个
缓存 + 计数这一步的 Python 版。

缓存
----
`<data_dir>/map_combo_cache.json` —— data_dir 是
`data/plugin_data/astrbot_plugin_osu_scorecard/`，**不在插件目录里**（插件目录
可能被 AstrBot 升级覆盖，而且它在 git 里）。一个 bid 的满连是不会变的，
所以 TTL 给得很长（默认 30 天），失败**不**写缓存（下载失败是暂时的，
缓存住会让一次网络抖动变成永久的 "--"）。
"""
from __future__ import annotations

import json
import time
from pathlib import Path

#: 默认缓存有效期。同一个 bid 的满连不会变，这个值只是给「谱面被改过」留条路。
DEFAULT_TTL_DAYS = 30

CACHE_NAME = "map_combo_cache.json"

#: 上限：避免缓存文件无限长大。满了就丢最旧的。
MAX_ENTRIES = 5000


class MapComboResolver:
    """`beatmap_id -> 真实满连`，带磁盘缓存。

    同步实现（和 osu_api / sb_api 一致）：调用方用 `asyncio.to_thread` 包起来，
    不要直接 await。
    """

    def __init__(self, data_dir, ttl_days: float = DEFAULT_TTL_DAYS,
                 proxy: str = "", enable_cache: bool = True):
        self.dir = Path(data_dir)
        self.ttl = max(0.0, float(ttl_days)) * 86400.0
        self.enable_cache = bool(enable_cache)
        # 代理在构造时定下来：解析器是单例，配置改了要重建（main.py 就是这么做的）。
        self.proxy = str(proxy or "")
        self._path = self.dir / CACHE_NAME
        self._cache: dict[str, dict] = self._load()

    # ─────────────────────────── 缓存读写 ───────────────────────────

    def _load(self) -> dict:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _save(self) -> None:
        """原子写：临时文件 + replace，崩在中间也不会留下半个文件。

        整个写盘失败不算致命 —— 大不了下次重新下载，绝不能因此让出卡失败。
        """
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            tmp.write_text(json.dumps(self._cache, ensure_ascii=False),
                           encoding="utf-8")
            tmp.replace(self._path)
        except OSError:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass

    def cached(self, beatmap_id) -> int | None:
        """缓存里的满连，过期或没有则 None。"""
        if not self.enable_cache or self.ttl <= 0:
            return None
        entry = self._cache.get(str(beatmap_id))
        if not isinstance(entry, dict):
            return None
        age = time.time() - float(entry.get("fetched_at") or 0)
        if age > self.ttl:
            return None
        value = entry.get("max_combo")
        return int(value) if isinstance(value, int) and value > 0 else None

    def put(self, beatmap_id, max_combo: int, notes: int = 0,
            holds: int = 0, bpm_range: tuple[float, float] | None = None,
            times: list[int] | None = None) -> None:
        if not self.enable_cache or self.ttl <= 0:
            return
        entry = {
            "max_combo": int(max_combo),
            "notes": int(notes),
            "holds": int(holds),
            "fetched_at": time.time(),
        }
        if bpm_range:
            entry["bpm_min"], entry["bpm_max"] = bpm_range
        if times:
            import density
            entry["density"] = density.buckets(times)
            entry["hit_times"] = density.encode_times(times)
        self._cache[str(beatmap_id)] = entry
        if len(self._cache) > MAX_ENTRIES:
            ordered = sorted(self._cache.items(),
                             key=lambda kv: kv[1].get("fetched_at") or 0)
            for key, _ in ordered[: len(ordered) - MAX_ENTRIES]:
                self._cache.pop(key, None)
        self._save()

    # ─────────────────────────── 取数 ───────────────────────────

    def resolve(self, beatmap_id) -> int | None:
        """这个 bid 的真实满连，取不到就 None（调用方自己决定降级）。

        缓存命中 -> 0 次网络；未命中 -> 下载 .osu 数一次再写缓存。
        任何异常都吞掉并返回 None：满连只是卡片上的一格，
        **不该因为它让整张卡失败**。调用方用 `last_error` 记原因。
        """
        self.last_error = ""
        text = str(beatmap_id or "").strip()
        if not text.isdigit():
            self.last_error = "beatmap_id 不是数字"
            return None

        hit = self.cached(text)
        if hit:
            return hit

        try:
            import osu_api

            osu_text = osu_api.fetch_beatmap_file(text, proxy=self.proxy)
        except Exception as exc:  # noqa: BLE001
            self.last_error = f"{type(exc).__name__}: {exc}"
            return None

        value = count_objects(osu_text)
        if value is None:
            # 下载成功但没有 [HitObjects]（换页、被截断、或是别的文件）：
            # 这是「数不出来」，不是 0，也不写缓存。
            self.last_error = "下载到的文件里没有可数的 [HitObjects]"
            return None

        combo, notes, holds = value
        import density
        self.put(text, combo, notes, holds, parse_bpm_range(osu_text),
                 density.hit_object_times(osu_text))
        return combo

    def resolve_bpm(self, beatmap_id) -> tuple[float, float] | None:
        """Read uninherited timing points; cache alongside the map combo."""
        text = str(beatmap_id or "").strip()
        if not text.isdigit():
            return None
        entry = self._cache.get(text) if self.enable_cache else None
        if isinstance(entry, dict) and time.time() - float(entry.get("fetched_at") or 0) <= self.ttl:
            low, high = entry.get("bpm_min"), entry.get("bpm_max")
            if isinstance(low, (int, float)) and isinstance(high, (int, float)):
                return float(low), float(high)
        try:
            import osu_api
            osu_text = osu_api.fetch_beatmap_file(text, proxy=self.proxy)
            bpm_range = parse_bpm_range(osu_text)
            if bpm_range and self.enable_cache and self.ttl > 0:
                combo = count_objects(osu_text)
                if combo:
                    import density
                    self.put(text, *combo, bpm_range=bpm_range,
                             times=density.hit_object_times(osu_text))
            return bpm_range
        except Exception:  # noqa: BLE001
            return None

    def resolve_density(self, beatmap_id, judged_objects: int | None = None
                        ) -> tuple[list[int], float | None]:
        """Return yumu-style 26-bin density and an estimated fail position.

        Existing cache entries predate density and are upgraded on first use.
        Download errors leave the chart empty without blocking score rendering.
        """
        import density

        text = str(beatmap_id or "").strip()
        if not text.isdigit():
            return [], None
        entry = self._cache.get(text) if self.enable_cache else None
        if isinstance(entry, dict) and time.time() - float(entry.get("fetched_at") or 0) <= self.ttl:
            values = entry.get("density")
            times = density.decode_times(entry.get("hit_times") or "")
            if (isinstance(values, list) and len(values) == density.BUCKETS
                    and all(isinstance(v, int) and v >= 0 for v in values)
                    and (judged_objects is None or times)):
                progress = density.fail_progress(times, judged_objects) if judged_objects else None
                return values, progress
        try:
            import osu_api
            osu_text = osu_api.fetch_beatmap_file(text, proxy=self.proxy)
            times = density.hit_object_times(osu_text)
            if not times:
                return [], None
            value = count_objects(osu_text)
            if value:
                self.put(text, *value, bpm_range=parse_bpm_range(osu_text), times=times)
            return density.buckets(times), (density.fail_progress(times, judged_objects)
                                            if judged_objects else None)
        except Exception:  # noqa: BLE001
            return [], None


def parse_bpm_range(osu_text: str) -> tuple[float, float] | None:
    """BPM extremes from red timing lines in the .osu [TimingPoints] section."""
    in_timing = False
    values = []
    for raw in osu_text.splitlines():
        line = raw.strip()
        if line.startswith("[") and line.endswith("]"):
            in_timing = line == "[TimingPoints]"
            continue
        if not in_timing or not line or line.startswith("//"):
            continue
        fields = line.split(",")
        try:
            if len(fields) > 6 and fields[6].strip() == "1":
                beat_length = float(fields[1])
                if beat_length > 0:
                    values.append(60000 / beat_length)
        except ValueError:
            continue
    return (min(values), max(values)) if values else None


def count_objects(osu_text: str) -> tuple[int, int, int] | None:
    """(满连, 普通键, 长条)，数不出来则 None。

    计数规则只有一份实现 —— `card.count_hit_objects()`。这里只是把中途数字
    一并返回，好写进缓存方便排查（缓存里存 notes/holds，出问题时能一眼看出
    数的是不是一张 mania 谱）。
    """
    import card

    counts = card.count_hit_objects(osu_text)
    if counts is None:
        return None
    notes, holds = counts
    return notes + holds * 2, notes, holds
