"""Turn osu! API payloads into the exact strings the template's text layers take.

Everything here is pure: no network, no Photoshop, no AstrBot. That is deliberate —
`self_test.py` feeds it the documented score 6645548845 and checks the numbers
against the values we already know that card must show.

Field names on the right of `to_layers()` come from `template/layer_mapping.json`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

# OD/HP bar scales. Difficulty Adjust widens them, which is why the bars are not
# always 0..10: an OD of 11 on a DA chart still has to fit.
STAT_RANGES = {"od": {"normal": (0.0, 10.0), "da": (-15.0, 15.0)},
               "hp": {"normal": (0.0, 10.0), "da": (0.0, 11.0)}}


def stat_range_for(name: str, value: float, da_enabled: bool) -> tuple[float, float]:
    r = STAT_RANGES.get(name)
    if not r:
        return 0.0, 10.0
    lo, hi = r["normal"]
    if da_enabled and (value < lo or value > hi):
        return r["da"]
    return lo, hi

# osu!mania judgement order on the card: MAX / 300 / 200 / 100 / 50 / miss.
# The v2 API names them perfect/great/good/ok/meh/miss (lazer) but older payloads
# and stable-era endpoints still use count_300 and friends, so both are accepted.
MANIA_KEYS = [
    ("count_max", ("perfect", "count_geki", "count_max")),
    ("count_300", ("great", "count_300")),
    ("count_200", ("good", "count_katu", "count_200")),
    ("count_100", ("ok", "count_100")),
    ("count_50",  ("meh", "count_50")),
    ("count_miss", ("miss", "count_miss")),
]

# Rate-changing mods are the only ones with a meaningful "xN.NN" multiplier, and
# that number is exactly what the template's mod_N_mult slot shows under the badge.
RATE_MODS = {
    "DT": 1.50, "NC": 1.50,
    "HT": 0.75, "DC": 0.75,
    "WU": 0.75, "WD": 1.50,
}

# Badge art that actually exists in template/assets/mods/ready/.
KNOWN_BADGES = {"HD", "DT", "HT", "HR", "EZ", "FL", "NF", "SO", "SD", "PF"}


def _fmt_int(value) -> str:
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return "0"


def _fmt_pp(value) -> str:
    if value is None:
        return "--"
    try:
        # Grouped, because the template's own sample reads "12,345pp" and a bare
        # "9486pp" reads as a different number at 30px.
        return f"{round(float(value)):,}pp"
    except (TypeError, ValueError):
        return "--"


def _fmt_acc(value) -> str:
    """Truncate, not round — this is what osu! itself displays.

    The API returns 0.99536 for score 6645548845. Rounding gives 99.54%; the osu!
    website shows 99.53%. Truncating matches the site, which is what a player
    compares the card against.
    """
    if value is None:
        return "--"
    try:
        return f"{int(float(value) * 10000) / 100:.2f}%"
    except (TypeError, ValueError):
        return "--"


def count_map_max_combo(osu_text: str) -> int | None:
    """Real max combo of a mania beatmap, counted from the .osu itself.

    osu!'s `beatmap.max_combo` is unreliable for mania. For bid 5493536 the API
    reports 3243, but the file holds 2478 objects (2034 notes + 444 holds) and a
    hold is worth 2 combo, so the true maximum is 2922 — which is exactly the
    player's max_combo, their perfect-combo flag, and the sum of all six
    judgements. The 321 gap is unexplained and is not any multiple of the hold
    count, so it is not simply a lazer-vs-stable counting difference.

    Returns None when the text has no [HitObjects] section.
    """
    idx = osu_text.find("[HitObjects]")
    if idx < 0:
        return None
    notes = holds = 0
    for line in osu_text[idx:].splitlines()[1:]:
        line = line.strip()
        if not line:
            continue
        parts = line.split(",")
        if len(parts) < 4:
            continue
        try:
            kind = int(parts[3])
        except ValueError:
            continue
        if kind & 128:          # mania hold
            holds += 1
        elif kind & 1:          # mania note
            notes += 1
    if notes == 0 and holds == 0:
        return None
    return notes + holds * 2


def _fmt_date(value) -> str:
    """ISO-8601 from the API -> `YYYY-MM-DD`, in the play's own offset.

    No timezone conversion on purpose: osu! stamps a play in the local time of the
    client that set it, and that is the date the player recognises.
    """
    if not value:
        return ""
    text = str(value).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return str(value)[:10]
    return dt.strftime("%Y-%m-%d")


# Score multiplier shown under a mod badge. Speed-changing mods only — see the
# note in CardData.to_layers() for why the others are deliberately omitted.
SPEED_MOD_MULT = {"DT": 1.5, "NC": 1.5, "HT": 0.5, "DC": 0.5}


# ───────────────────────── osu!mania pp ─────────────────────────
#
# 公式来源（权威，ppy/osu 主分支，取用时 2026-10）：
#   osu.Game.Rulesets.Mania/Difficulty/ManiaPerformanceCalculator.cs
#
#     totalHits      = perfect + great + good + ok + meh + miss
#     customAccuracy = (perfect*320 + great*300 + good*200 + ok*100 + meh*50)
#                      / (totalHits * 320)
#     difficultyValue= 8.0 * max(SR - 0.15, 0.05)^2.2
#                      * max(0, 5*customAccuracy - 4)
#                      * (1 + 0.1 * min(1, totalHits/1500))
#     total          = difficultyValue * multiplier        # NF x0.75, EZ x0.5（可叠乘）
#
# 实测标定（成绩 6645548845）：公式 147.9015 pp vs API 147.902 pp，差 -0.0005。
#
# ⚠️ 这个公式**会随 osu! 版本变化**。上面是「当前」的 lazer 公式；osu! 改版后
#    这个数会失准，需要人工维护。配置项 `pp_max_mode` 可以一键退回 `--`。


def _judge_values(counts: dict) -> tuple[int, int, int, int, int, int]:
    """(perfect, great, good, ok, meh, miss) from either key vocabulary.

    `judgements()` returns the TEMPLATE's names (`count_max`, `count_300`, ...) because
    those are the layer names in the PSD. The osu! API's own names are
    perfect/great/good/ok/meh. Accept both, so a caller holding either shape works.
    """
    alias = {
        "perfect": ("perfect", "count_max", "max"),
        "great":   ("great", "count_300", "300"),
        "good":    ("good", "count_200", "200"),
        "ok":      ("ok", "count_100", "100"),
        "meh":     ("meh", "count_50", "50"),
        "miss":    ("miss", "count_miss"),
    }
    out = []
    for _name, keys in alias.items():
        v = 0
        for k in keys:
            if counts and counts.get(k) is not None:
                v = int(counts[k] or 0)
                break
        out.append(v)
    return tuple(out)  # type: ignore[return-value]


def mania_pp(counts: dict, star_rating: float, mods=()) -> float | None:
    """按上面那条公式算 pp。counts 用哪套判定键名都行（见 _judge_values）。"""
    if not star_rating or star_rating <= 0:
        return None
    perfect, great, good, ok, meh, miss = _judge_values(counts)
    total_hits = perfect + great + good + ok + meh + miss
    if total_hits <= 0:
        return None

    custom_acc = (perfect * 320 + great * 300 + good * 200 + ok * 100 + meh * 50) / (total_hits * 320)
    mult = 1.0
    upper = {str(m).upper() for m in (mods or [])}
    if "NF" in upper:
        mult *= 0.75
    if "EZ" in upper:
        mult *= 0.5

    return (8.0
            * max(star_rating - 0.15, 0.05) ** 2.2
            * max(0.0, 5.0 * custom_acc - 4.0)
            * (1.0 + 0.1 * min(1.0, total_hits / 1500.0))
            * mult)


def max_pp(counts: dict, star_rating: float, mods=()) -> float | None:
    """理论最大 PP：全部判定都是 320（perfect）、满连。

    全 320 时 customAccuracy 恒等于 1.0，所以 `max(0, 5*acc-4)` 这一项恒等于 1，
    公式退化成只跟 星级 / totalHits / NF·EZ 有关：

        8.0 * max(SR - 0.15, 0.05)^2.2 * 1.0 * (1 + 0.1*min(1, totalHits/1500)) * mult

    已用 SR 2~9、notes 500~4000 的网格验证这个退化和完整公式逐位一致（差 < 1e-9）。
    注意它**仍然依赖 totalHits** —— 光有星级算不出来。
    """
    # 只数六个判定。counts 里还可能有 ignore_hit 之类的非判定键（lazer 会给），
    # 那些不能算进 totalHits，否则长度奖励项会算错。
    vals = _judge_values(counts) if isinstance(counts, dict) else ()
    total_hits = sum(vals)
    if not total_hits:
        return None
    return mania_pp({"perfect": total_hits}, star_rating, mods)


def mod_acronyms(mods) -> list[str]:
    """`score.mods` is a list of acronyms in v1-shaped payloads and a list of
    {acronym, settings} objects in lazer-shaped ones. Both are normalised here."""
    out: list[str] = []
    for m in mods or []:
        if isinstance(m, str):
            out.append(m.upper())
        elif isinstance(m, dict) and m.get("acronym"):
            out.append(str(m["acronym"]).upper())
    return out


def judgements(score: dict) -> dict[str, int]:
    """Six judgement counts, tolerating either naming scheme."""
    stats = score.get("statistics") or {}
    out: dict[str, int] = {}
    for layer, keys in MANIA_KEYS:
        value = 0
        for k in keys:
            if stats.get(k) is not None:
                value = int(stats[k] or 0)
                break
        out[layer] = value
    return out


def stable_accuracy(counts: dict[str, int]) -> float | None:
    """osu!stable mania accuracy.

    On the stable scale MAX and 300 are both worth 300, 200->200, 100->100, 50->50.
    This is the number the template's big ACCURACY readout shows, and it is NOT the
    same as the lazer figure the API reports for the same play.
    """
    total = sum(counts.values())
    if total <= 0:
        return None
    gain = (300 * (counts["count_max"] + counts["count_300"])
            + 200 * counts["count_200"]
            + 100 * counts["count_100"]
            + 50 * counts["count_50"])
    return gain / (300 * total)


def lazer_accuracy(counts: dict[str, int]) -> float | None:
    """Lazer mania accuracy (305 scale). Only used when the API gives no value."""
    total = sum(counts.values())
    if total <= 0:
        return None
    gain = (305 * counts["count_max"]
            + 300 * counts["count_300"]
            + 200 * counts["count_200"]
            + 100 * counts["count_100"]
            + 50 * counts["count_50"])
    return gain / (305 * total)


def grade_of(counts: dict[str, int], mods: list[str]) -> str:
    """osu! grade letter, including the silver (Hidden) variants.

    Only used when the API did not hand us a grade. The server's own `rank` field
    is preferred — see grade_from_api.
    """
    hidden = "HD" in mods or "FL" in mods
    if counts["count_miss"] == 0 and counts["count_50"] == 0 and counts["count_100"] == 0 \
            and counts["count_200"] == 0 and counts["count_300"] == 0:
        return "XH" if hidden else "SS"
    if counts["count_miss"] == 0 and counts["count_50"] == 0 and counts["count_100"] == 0:
        return "SH" if hidden else "S"
    total = sum(counts.values()) or 1
    hit = sum(c for k, c in counts.items() if k != "count_miss")
    ratio = hit / total
    if ratio > 0.90:
        return "A"
    if ratio > 0.80:
        return "B"
    if ratio > 0.70:
        return "C"
    return "D"


# The API spells the top grades with an X; the card (and osu!'s own UI) uses SS.
_API_GRADE_ALIAS = {"X": "SS", "XH": "XH", "SS": "SS", "S": "S", "SH": "SH"}


def grade_from_api(raw, mods: list[str], counts: dict[str, int]) -> str:
    """Prefer the server's grade; fall back to counting judgements ourselves."""
    if isinstance(raw, str) and raw.strip():
        g = raw.strip().upper()
        if g in _API_GRADE_ALIAS:
            return _API_GRADE_ALIAS[g]
        if len(g) == 1 and g in "ABCD":
            return g
    return grade_of(counts, mods)


@dataclass
class CardData:
    """Every value the card renders, already formatted."""

    title: str = ""
    artist: str = ""
    difficulty: str = ""
    mapper: str = ""
    beatmap_id: str = ""
    bpm: str = ""
    od: str = ""
    hp: str = ""
    star_rating: str = ""

    player_name: str = ""
    total_pp: str = ""
    rank_change: str = ""
    play_date: str = ""

    score: str = ""
    pp: str = ""
    pp_max: str = ""
    accuracy: str = ""
    accuracy_lazer: str = ""
    max_combo: str = ""
    map_max_combo: str = ""

    counts: dict[str, int] = field(default_factory=dict)
    mods: list[str] = field(default_factory=list)

    # 分服标识。官服和 SB 私服是两套独立数据，同一张卡上必须一眼能看出成绩来自哪边。
    # 文本为空时那一格不画（渲染器只画有内容的层）。
    server_tag: str = ""
    server_tag_color: str = "#8C96A9"

    # not a text layer: drives the signboard, the rank theme and the star strip
    grade: str = "D"
    star_value: float = 0.0
    od_value: float = 0.0
    hp_value: float = 0.0
    od_range: tuple[float, float] = (0.0, 10.0)
    hp_range: tuple[float, float] = (0.0, 10.0)
    background_url: str = ""
    avatar_url: str = ""

    def to_layers(self) -> dict[str, str]:
        """Layer name -> replacement text. Names match layer_mapping.json."""
        out = {
            "beatmap_title": self.title,
            "beatmap_artist": self.artist,
            "beatmap_difficulty": self.difficulty,
            "beatmap_mapper": self.mapper,
            "beatmap_id": self.beatmap_id,
            # 紧挨着谱面 ID 的分服标识（官方 / SB 私服）
            "server_tag": self.server_tag,
            "bpm": self.bpm,
            "od": self.od,
            "hp": self.hp,
            "star_rating": self.star_rating,
            "player_name": self.player_name,
            "total_pp": self.total_pp,
            "rank_change": self.rank_change,
            "play_date": self.play_date,
            "score": self.score,
            "pp": self.pp,
            "pp_max": self.pp_max,
            "accuracy": self.accuracy,
            "accuracy_lazer": self.accuracy_lazer,
            "max_combo": self.max_combo,
            "map_max_combo": self.map_max_combo,
        }
        out.update({k: _fmt_int(v) for k, v in self.counts.items()})

        # Mod multipliers. Only SPEED-changing mods are shown, because those are
        # the only ones whose multiplier is unambiguous across rulesets and osu!
        # versions; the exact figures for HD/HR/EZ etc. differ and printing a
        # wrong number is worse than printing none. DT and HT are also the ones
        # the template itself demonstrates (`mod_2_mult` ships with "x1.5").
        #
        # Anything NOT emitted here must be hidden by the renderer — the template
        # ships `mod_2_mult` visible, so leaving it alone put a stale "x1.5" on
        # every no-mod card.
        for i, code in enumerate(self.mods):
            mult = SPEED_MOD_MULT.get(code.upper())
            if mult is not None and 1 <= i + 1 <= 6:
                out[f"mod_{i + 1}_mult"] = f"x{mult:g}"
        return out


def _pick(d: dict, *keys, default=""):
    for k in keys:
        v = d.get(k)
        if v not in (None, ""):
            return v
    return default


def build_card(score: dict, beatmap: dict, beatmapset: dict,
               player: dict | None = None,
               pp_max_mode: str = "computed") -> CardData:
    """Assemble a CardData from a /scores/<id> payload plus optional user profile.

    `beatmap`/`beatmapset` are the objects the score already embeds, so a score
    fetch needs no follow-up requests. `player` is a full /users/... profile and is
    the only source of TOTAL PP; without it that slot falls back to a dash.

    `pp_max_mode`: 'computed' 算理论最大 PP（全 320 + 满连）,'dash' 退回 "--"。
    """
    mods = mod_acronyms(score.get("mods"))
    counts = judgements(score)
    # 成绩来自官服还是 SB 私服。取数那一步会在 score 里打 `server` 标记；
    # 官服路径不打，所以默认 "osu"（保持既有行为不变）。
    _server = str(score.get("server") or "osu").strip().lower()
    stars = beatmap.get("difficulty_rating")
    od = beatmap.get("accuracy")
    hp = beatmap.get("drain")
    da = "DA" in mods or "DifficultyAdjust" in mods

    lazer = score.get("accuracy")
    if lazer is None:
        lazer = lazer_accuracy(counts)

    # TOTAL PP arrives in two different shapes and both are live callers:
    #   - the raw /users/... response  -> player["statistics"]["pp"]
    #   - main._profile()'s slim dict  -> player["total_pp"]  (flat)
    # Only the first was handled, so the real render path always drew a dash while
    # self_test (which feeds the raw shape) passed. Accept both.
    stats = (player or {}).get("statistics") or {}
    total_pp = stats.get("pp")
    if total_pp is None:
        total_pp = (player or {}).get("total_pp")

    # See count_map_max_combo(): the API's beatmap.max_combo drifts for mania, so on a
    # full combo trust the player's own max_combo instead.
    if score.get("is_perfect_combo") and score.get("max_combo"):
        _map_max_combo = score.get("max_combo")
    else:
        _map_max_combo = beatmap.get("max_combo", 0)

    # 理论最大 PP。老调用方不传 pp_max_mode，默认按 computed 走。
    _pp_max_mode = str(pp_max_mode or "computed").strip().lower()
    if _pp_max_mode in ("dash", "none", "off", "--"):
        _pp_max_text = "--"
    else:
        _v = max_pp(counts, float(stars or 0.0), mods)
        _pp_max_text = _fmt_pp(_v) if _v else "--"

        # 合理性闸门：理论最大 PP 不可能低于这一局实际拿到的 PP。
        #
        # 会低于只有一个原因 —— 递进来的 `stars` 是**没算 mod 的名义星级**，而
        # mania_pp() 只对 NF/EZ 做倍率，**没有做变速（DT/HT）的星级调整**。
        # 开 DT 时实际难度远高于名义星级，本地公式就会低估到离谱。
        #   实测（SB 私服成绩 5030104）：名义 4.993★ + DT，实际 pp = 931.47，
        #   本地公式算出的 pp_max = 283 —— 比实际还小。
        # 与其在卡上印一个明显错的数，不如退回 "--"。
        #
        # 正解要 mod 调整后的星级（需要难度重算）或服务端计算器：
        # SB 的 /v1/calculate_pp 需要鉴权（实测 401），官服 v2 没有这个端点。
        # 所以这里只做闸门，不动 mania_pp/max_pp 本身。
        try:
            _actual_pp = float(score.get("pp") or 0.0)
        except (TypeError, ValueError):
            _actual_pp = 0.0
        if _v and _actual_pp and float(_v) <= _actual_pp:
            _pp_max_text = "--"

    return CardData(
        title=str(_pick(beatmapset, "title_unicode", "title")),
        artist=str(_pick(beatmapset, "artist_unicode", "artist")),
        difficulty=str(_pick(beatmap, "version", default="?")),
        mapper=f"mapped by {_pick(beatmapset, 'creator', default='?')}",
        beatmap_id=f"#{_pick(beatmap, 'id', default='?')}",
        # 分服标识。`score["server"]` 由取数那一步打上（官服路径不打 -> osu）。
        # 官服也显式写「官方」而不是留空 —— 「什么都不显示」这个约定太隐晦，
        # 用户看图时没法确定一张旧卡到底是哪边来的。
        server_tag="SB 私服" if _server == "sb" else "官方",
        # 私服用青色：它和九套评级强调色（金/银/绿/蓝/紫/红/暗红）都不撞，
        # 一眼能看出「这不是普通的一张官服卡」。官服用三级灰，安静地待着。
        server_tag_color="#4FC3F7" if _server == "sb" else "#8C96A9",
        bpm=str(_pick(beatmap, "bpm", default="")),
        od=f"{float(od):g}" if od is not None else "",
        hp=f"{float(hp):g}" if hp is not None else "",
        # Deliberately EMPTY: the star strip raster already carries the "★ 3.88"
        # badge, and this text layer sits right on top of it (107,319 vs the strip's
        # 75,326-644,378). Drawing both prints the number twice.
        #
        # The template PSD ships this layer HIDDEN, which is why the Photoshop path
        # never showed it — PS writes the content and the hidden flag wins. PIL has no
        # visibility concept, so it drew it and the duplicate appeared.
        # The strip is the owner of this number; star_value (below) feeds it.
        star_rating="",

        player_name=str(_pick(score.get("user") or {}, "username",
                              default=_pick(player or {}, "username", default="?"))),
        total_pp=_fmt_pp(total_pp),
        # rank_global is the score's position on the map leaderboard. The layer is
        # named `rank_change`, which reads like a PP delta — the API offers no such
        # number, so this slot shows the leaderboard rank instead.
        rank_change=(f"#{score['rank_global']}" if score.get("rank_global") else "--"),
        play_date=_fmt_date(_pick(score, "ended_at", "created_at")),

        # v2 calls the raw score `total_score`; `score` is present but null.
        score=_fmt_int(_pick(score, "total_score", "legacy_total_score", "score", default=0)),
        pp=_fmt_pp(score.get("pp")),
        # 理论最大 PP = 全 320 判定 + 满连。公式见上面的 mania_pp()/max_pp()。
        # pp_max_mode 为 'dash' 时退回 "--"（公式随 osu! 版本会失准，留个逃生口）。
        pp_max=_pp_max_text,
        accuracy=_fmt_acc(stable_accuracy(counts)),
        accuracy_lazer=_fmt_acc(lazer),
        max_combo=f"{_fmt_int(score.get('max_combo', 0))}x",
        # The API's beatmap.max_combo drifts for mania (3243 vs the true 2922 here —
        # see count_map_max_combo). On a full combo the player's own max_combo IS the
        # map's true maximum, so prefer it; otherwise fall back to the API value.
        # Count the .osu with count_map_max_combo() when an exact non-FC value matters.
        map_max_combo=f"{_fmt_int(_map_max_combo)}x",

        counts=counts,
        mods=mods,

        grade=grade_from_api(score.get("rank"), mods, counts),
        star_value=float(stars or 0.0),
        od_value=float(od or 0.0),
        hp_value=float(hp or 0.0),
        od_range=stat_range_for("od", float(od or 0.0), da),
        hp_range=stat_range_for("hp", float(hp or 0.0), da),
        background_url=str(_pick(beatmapset.get("covers") or {}, "cover@2x", "cover")),
        avatar_url=str(_pick(score.get("user") or {}, "avatar_url",
                             default=_pick(player or {}, "avatar_url", default=""))),
    )
