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


def count_hit_objects(osu_text: str) -> tuple[int, int] | None:
    """(普通键数, 长条数) of a mania .osu, or None when there is nothing to count.

    The one place that parses [HitObjects]. count_map_max_combo() and the cache
    both go through it — a second parser written for the cache is how the two
    would quietly disagree later.
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
    return notes, holds


def count_map_max_combo(osu_text: str) -> int | None:
    """Max combo of a mania beatmap counted from the .osu itself — the STABLE rule.

    osu!'s `beatmap.max_combo` is a **lazer** number for mania: it counts hold
    ticks as well as the head and the tail. This function counts the way the
    stable client does (a note is 1 combo, a hold is 2), which is the number
    that belongs beside a stable play's own combo.

    Measured against the live API and both maps' leaderboards (2026-10):

        bid      notes  holds  here  API   stable plays          lazer "CL" plays
        5493536   2034    444   2922  3243  2922 (is_perfect_combo)  3243
        5327306   1184    624   2432  2763  2432 (is_perfect_combo)  2757+

    For 5327306 the leaderboard settles it outright: plays with no mods and
    `is_perfect_combo` = true report exactly 2432, while lazer "CL" plays report
    2757 and the API says 2763. Two counting rules, two correct numbers — the
    card is showing a stable play's combo, so it wants the stable maximum.

    Returns None when there is nothing to count (no [HitObjects], an osu!std
    file, a truncated download).
    """
    counts = count_hit_objects(osu_text)
    if counts is None:
        return None
    notes, holds = counts
    return notes + holds * 2


def as_positive_int(value) -> int | None:
    """Anything a payload or a fixture might hand us -> a positive int, else None.

    `0` is deliberately NOT a value. On this card zero means "nothing was
    measured", and printing it renders as `0x` — a number that looks like data
    but is not. That is the bug this whole file's combo handling exists to
    avoid, so the guard lives here rather than at each call site.
    """
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _fmt_combo(value) -> str:
    """Combo slot: `2,922x`, or `--` when there is no measurement."""
    number = as_positive_int(value)
    return f"{number:,}x" if number else "--"


def _fmt_length(seconds) -> str:
    try:
        n = max(0, int(seconds))
        return f"{n // 60}:{n % 60:02d}"
    except (TypeError, ValueError, OverflowError):
        return "--:--"


def _fmt_bpm(beatmap: dict, bpm_range: tuple[float, float] | None) -> str:
    if bpm_range:
        low, high = bpm_range
        if round(low) != round(high):
            return f"{round(low)}–{round(high)}"
    return str(_pick(beatmap, "bpm", default=""))


def _score_parts(value) -> tuple[str, str]:
    try:
        n = max(0, int(value))
    except (TypeError, ValueError, OverflowError):
        return "--", ""
    return (f"{n // 1000}K", f".{n % 1000:03d}") if n >= 1000 else (str(n), "")


def resolve_map_max_combo(score: dict, beatmap: dict,
                          counted: int | None = None) -> tuple[int | None, str]:
    """The MAP COMBO slot, in the order we trust the sources.

    Returns (value, source); value None means "no measurement" and the caller
    prints `--`. `source` is kept for tests and for the log line — it is how we
    tell "the .osu was counted" from "we fell back to the API".

    The order, and why:

      1. `perfect_combo` — on a full combo the player's own `max_combo` IS the
         map's maximum, exactly, and it costs nothing. This is also the only
         case where the number is beyond argument.
      2. `osu_file` — `counted`, the value a caller obtained by downloading the
         .osu and running count_map_max_combo() on it. Accurate, but it needs
         the file, so the caller (not this pure function) does the fetching.
      3. `api` — `beatmap.max_combo`. For mania this is the **lazer** maximum
         (see count_map_max_combo): right for a lazer play, systematically too
         high for a stable one. It is a last resort, not a source of truth.
      4. `none` — nothing usable, so the card shows `--`.

    Two of those three sources can be *contradicted by the score itself*: a map's
    maximum can never be smaller than a combo someone already reached on it. A
    candidate below the score's own `max_combo` is therefore not merely
    imprecise, it is impossible, and it is discarded — which is what keeps a
    lazer play (combo 2757 on bid 5327306) from being handed the stable maximum
    of 2432, and lets the API's 2763 through instead. Rejecting a value we can
    prove wrong is not the same as trusting the API; it is the cheapest honest
    check available without a second download.
    """
    player = as_positive_int((score or {}).get("max_combo"))
    if player and (score or {}).get("is_perfect_combo"):
        return player, "perfect_combo"

    for value, source in ((as_positive_int(counted), "osu_file"),
                          (as_positive_int((beatmap or {}).get("max_combo")), "api")):
        if value and (player is None or value >= player):
            return value, source
    return None, "none"


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
SPEED_MOD_MULT = {"DT": 1.5, "NC": 1.5, "HT": 0.75, "DC": 0.75}


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


def mod_speed_multipliers(mods) -> list[float | None]:
    """Use each speed mod's actual setting; unconfigured mods use game defaults."""
    result = []
    for mod in mods or []:
        code = (mod if isinstance(mod, str) else mod.get("acronym", "")).upper()
        default = SPEED_MOD_MULT.get(code)
        value = (mod.get("settings") or {}).get("speed_change") if isinstance(mod, dict) else None
        try:
            speed = float(value) if value is not None else default
            result.append(speed if speed is not None and 0 < speed <= 10 else default)
        except (TypeError, ValueError):
            result.append(default)
    return result


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
    This is the stable-comparable accuracy shown on a lazer play's right side.
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


def grade_of(counts: dict[str, int], mods: list[str], accuracy=None) -> str:
    """Mania fallback grade, using weighted accuracy rather than non-miss ratio.

    Use the API accuracy when available (lazer); otherwise use stable judgement
    weights, including for SB payloads. Thresholds follow osu!'s ScoreProcessor:
    https://github.com/ppy/osu/blob/master/osu.Game/Rulesets/Scoring/ScoreProcessor.cs
    A missing/empty score must not be mistaken for a perfect play.
    """
    try:
        accuracy = float(accuracy) if accuracy is not None else None
    except (TypeError, ValueError):
        accuracy = None
    if accuracy is None or not 0 <= accuracy <= 1:
        accuracy = stable_accuracy(counts)
    if accuracy is None:
        return "D"
    hidden = any(mod in mods for mod in ("HD", "FL", "FI"))
    if accuracy == 1:
        return "XH" if hidden else "SS"
    if accuracy >= 0.95:
        return "SH" if hidden else "S"
    if accuracy >= 0.90:
        return "A"
    if accuracy >= 0.80:
        return "B"
    if accuracy >= 0.70:
        return "C"
    return "D"


# The API spells the top grades with an X; the card (and osu!'s own UI) uses SS.
_API_GRADE_ALIAS = {"X": "SS", "XH": "XH", "SS": "SS", "S": "S", "SH": "SH"}


def grade_from_api(raw, mods: list[str], counts: dict[str, int], *,
                   passed: bool | None = None, accuracy=None) -> str:
    """Failure wins; preserve valid API grades before using mania fallback."""
    if passed is False:
        return "F"
    if isinstance(raw, str) and raw.strip():
        g = raw.strip().upper()
        if g in _API_GRADE_ALIAS:
            return _API_GRADE_ALIAS[g]
        if len(g) == 1 and g in "ABCDF":
            return g
    return grade_of(counts, mods, accuracy)


@dataclass
class CardData:
    """Every value the card renders, already formatted."""

    title: str = ""
    artist: str = ""
    difficulty: str = ""
    mapper: str = ""
    beatmap_id: str = ""
    bpm: str = ""
    length: str = ""
    keys: str = ""
    status_icon: str = ""
    od: str = ""
    hp: str = ""
    star_rating: str = ""

    player_name: str = ""
    total_pp: str = ""
    rank_change: str = ""
    play_date: str = ""

    score: str = ""
    score_suffix: str = ""
    full_combo: bool = False
    pp: str = ""
    pp_max: str = ""
    accuracy: str = ""
    accuracy_lazer: str = ""
    other_accuracy_label: str = "LAZER ACC"
    max_combo: str = ""
    map_max_combo: str = ""

    # 不是文本层：`map_max_combo` 这个数是从哪条路来的
    # （perfect_combo / osu_file / api / none）。给自检和日志看，卡片不画它。
    map_max_combo_source: str = "none"

    counts: dict[str, int] = field(default_factory=dict)
    mods: list[str] = field(default_factory=list)
    mod_speeds: list[float | None] = field(default_factory=list)
    # Drawn in the open space below MODS by raster.render_density_panel().
    density_counts: list[int] = field(default_factory=list)
    fail_progress: float | None = None
    ratio_text: str = "--"

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
            "length": self.length,
            "keys": self.keys,
            "od": self.od,
            "hp": self.hp,
            "star_rating": self.star_rating,
            "player_name": self.player_name,
            "total_pp": self.total_pp,
            "_deco_total_pp_label": "TOTAL PP",
            "rank_change": self.rank_change,
            "play_date": self.play_date,
            "score": self.score,
            "score_suffix": self.score_suffix,
            "pp": self.pp,
            "pp_max": self.pp_max,
            "accuracy": self.accuracy,
            "accuracy_lazer": self.accuracy_lazer,
            "_deco_accuracy_lazer_label": self.other_accuracy_label,
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
            mult = (self.mod_speeds[i] if i < len(self.mod_speeds)
                    else SPEED_MOD_MULT.get(code.upper()))
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
               pp_max_mode: str = "computed",
               real_max_combo: int | None = None,
               bpm_range: tuple[float, float] | None = None,
               density_counts: list[int] | None = None,
               fail_progress: float | None = None,
               modded_star_rating: float | None = None) -> CardData:
    """Assemble a CardData from a /scores/<id> payload plus optional user profile.

    `beatmap`/`beatmapset` are the objects the score already embeds, so a score
    fetch needs no follow-up requests. `player` is a full /users/... profile and is
    the only source of TOTAL PP; without it that slot falls back to a dash.

    `real_max_combo` is the map's maximum combo as counted from the .osu itself
    (card.count_map_max_combo), supplied by the caller because this module does
    no I/O. None means "not counted" and the slot falls back as described in
    resolve_map_max_combo().

    `pp_max_mode`: 'computed' 算理论最大 PP（全 320 + 满连）,'dash' 退回 "--"。
    """
    mods = mod_acronyms(score.get("mods"))
    counts = judgements(score)
    ratio_text = (f"{counts['count_max'] / counts['count_300']:.1f}"
                  if counts['count_300'] > 0 else "--")
    # 成绩来自官服还是 SB 私服。取数那一步会在 score 里打 `server` 标记；
    # 官服路径不打，所以默认 "osu"（保持既有行为不变）。
    _server = str(score.get("server") or "osu").strip().lower()
    is_stable = (_server == "sb" or score.get("legacy_score_id") is not None
                 or bool(score.get("legacy_total_score")))
    # The score's embedded beatmap carries the *unmodded* rating. The caller
    # resolves score-specific attributes from osu! when mods are present.
    stars = modded_star_rating if modded_star_rating is not None else beatmap.get("difficulty_rating")
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

    # MAP COMBO. The old code was `beatmap.get("max_combo", 0)` on every
    # non-full-combo play, and the official API does not always put that key on
    # the score's embedded beatmap at all — so the card printed `0x`. The order
    # of sources, and the impossibility check, are in resolve_map_max_combo().
    _map_max_combo, _map_max_combo_src = resolve_map_max_combo(
        score, beatmap, counted=real_max_combo)
    raw_score = _pick(score, "total_score", "legacy_total_score", "score", default=0)
    score_main, score_suffix = _score_parts(raw_score)
    combo = as_positive_int(score.get("max_combo"))
    full_combo = bool(score.get("is_perfect_combo") or score.get("legacy_perfect"))
    if not full_combo and combo and _map_max_combo:
        full_combo = combo == _map_max_combo
    status = str(_pick(beatmap, "status", default="")).lower()
    if not status:
        status = {2:"ranked",1:"ranked",3:"qualified",4:"loved",
                  0:"pending",-2:"graveyard"}.get((beatmap or {}).get("ranked"), "")
    status_icon = ("ranked" if status in ("ranked", "approved") else
                   status if status in ("loved", "qualified", "pending", "graveyard") else "")

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
        # 官服也显式写 Lazer / Stable 而不是留空 —— 「什么都不显示」这个约定太隐晦，
        # 用户看图时没法确定一张旧卡到底是哪边来的。
        server_tag=("SB 私服" if _server == "sb" else "Stable" if is_stable else "Lazer"),
        # 私服用青色：它和九套评级强调色（金/银/绿/蓝/紫/红/暗红）都不撞，
        # 一眼能看出「这不是普通的一张官服卡」。官服用三级灰，安静地待着。
        server_tag_color="#4FC3F7" if _server == "sb" else "#8C96A9",
        bpm=_fmt_bpm(beatmap, bpm_range),
        length=_fmt_length(beatmap.get("total_length") or beatmap.get("hit_length")),
        keys=(f"{float(beatmap['cs']):g}K" if beatmap.get("cs") is not None else "--"),
        status_icon=status_icon,
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
        # 玩家名字下面那一格。图层名是 `rank_change`，但它显示的**不是 PP 变化**
        # —— osu! API 根本没有「PP 变化」这个字段（没有历史 PP 就没有 delta）。
        # 这一格填的是 `rank_global`：**这局成绩在谱面排行榜上的名次**（#165 =
        # 该谱面第 165 名）。API 没给这个字段时显示 `--`，那是正确行为，不是 bug。
        # 图层名保留不改：改它要连带动模板和 layer_mapping.json，不值得。
        rank_change=(f"#{score['rank_global']}" if score.get("rank_global") else "--"),
        play_date=_fmt_date(_pick(score, "ended_at", "created_at")),

        # v2 calls the raw score `total_score`; `score` is present but null.
        score=score_main,
        score_suffix=score_suffix,
        full_combo=full_combo,
        pp=_fmt_pp(score.get("pp")),
        # 理论最大 PP = 全 320 判定 + 满连。公式见上面的 mania_pp()/max_pp()。
        # pp_max_mode 为 'dash' 时退回 "--"（公式随 osu! 版本会失准，留个逃生口）。
        pp_max=_pp_max_text,
        accuracy=_fmt_acc(stable_accuracy(counts) if is_stable else lazer),
        accuracy_lazer=_fmt_acc(lazer if is_stable else stable_accuracy(counts)),
        other_accuracy_label="LAZER ACC" if is_stable else "STABLE ACC",
        max_combo=_fmt_combo(score.get("max_combo")),
        # MAP COMBO = 谱面满连。取数顺序（满连 -> 数 .osu -> API -> "--"）和
        # 「候选值不能小于玩家自己的连击」这条否决规则，都写在
        # resolve_map_max_combo() 上面。**任何情况下都不出现 `0x`** ——
        # 0 是「没测到」的伪装，看起来像真数据。
        map_max_combo=_fmt_combo(_map_max_combo),
        map_max_combo_source=_map_max_combo_src,

        counts=counts,
        mods=mods,
        mod_speeds=mod_speed_multipliers(score.get("mods")),
        density_counts=list(density_counts or []),
        fail_progress=fail_progress if score.get("passed") is False else None,
        ratio_text=ratio_text,

        grade=grade_from_api(score.get("rank"), mods, counts,
                             passed=score.get("passed"), accuracy=score.get("accuracy")),
        star_value=float(stars or 0.0),
        od_value=float(od or 0.0),
        hp_value=float(hp or 0.0),
        od_range=stat_range_for("od", float(od or 0.0), da),
        hp_range=stat_range_for("hp", float(hp or 0.0), da),
        background_url=str(_pick(beatmapset.get("covers") or {}, "cover@2x", "cover")),
        avatar_url=str(_pick(score.get("user") or {}, "avatar_url",
                             default=_pick(player or {}, "avatar_url", default=""))),
    )
