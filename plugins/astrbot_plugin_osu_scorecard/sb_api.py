"""osu! 私服（SB / ppy.sb）的 API 客户端与数据归一化。

为什么单独一个模块
------------------
官服 `osu.ppy.sh` 的 `/users/{user}/scores/recent` 对应用凭据一律 404，必须走用户授权；
而 **SB 私服不需要授权** —— 只要用户名或 id 就能查最近成绩。所以私服这条路能立刻用，
官服那条要等 OAuth 授权码流程。

接口来源
--------
`https://api.ppy.sb/` 是个 FastAPI 服务，自带 OpenAPI 文档（`/openapi.json`，59 个端点）。
本模块用到的：

    GET /v1/search_players?q=<名字>                    名字 -> id
    GET /v1/get_player_info?scope=all&id=|name=        玩家资料（stats 按模式索引）
    GET /v1/get_player_scores?scope=recent|best&...    最近 / 最佳成绩  ← 官服做不到的那个
    GET /v1/get_score_info?id=                         单条成绩
    GET /v1/get_map_info?id=|md5=                      谱面（真实 max_combo 只在这里）

两个必须知道的坑
----------------
1. **`score.beatmap.max_combo` 是脏数据。** 它永远等于 `score.max_combo`（实测 5 条成绩
   全部相等），不是谱面的满连。谱面真实满连必须另外调 `/v1/get_map_info?md5=`。
   实测：score 5030104 的 `max_combo` = 945，而 `get_map_info` 给的 `max_combo` = 3228。
   `score.max_combo` 本身是**玩家**的连击（945 ≤ 3228，说得通），可以直接用。

2. **响应都包了一层 `{"status": "success", ...}`**，失败时 status 是错误文本而不是 success。
   本模块统一在这一层脱壳，调用方拿到的就是干净的 list / dict。

`mods` 是 **stable 位掩码整数**（不是官服的 acronym 列表），所以要自己解码。
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

SB_BASE = "https://api.ppy.sb"
SB_AVATAR = "https://a.ppy.sb"          # 头像：{SB_AVATAR}/{player_id}
OSU_COVER = "https://assets.ppy.sh"     # 谱面封面走官服 CDN（SB 没有自己的封面源）

# stable 的 mod 位掩码。顺序按位取值，键是 acronym。
_MOD_BITS = [
    (1, "NF"), (2, "EZ"), (4, "TD"), (8, "HD"), (16, "HR"), (32, "SD"),
    (64, "DT"), (128, "RX"), (256, "HT"), (512, "NC"), (1024, "FL"),
    (2048, "AT"), (4096, "SO"), (8192, "AP"), (16384, "PF"),
    (1048576, "FI"), (2097152, "RD"), (4194304, "CN"), (8388608, "TG"),
]
# 键数 mod（4K/5K/7K…）对 mania 卡片是噪音，解码后丢掉。
_KEY_MOD_BITS = {32768, 65536, 131072, 262144, 524288,
                 16777216, 33554432, 67108864, 134217728, 268435456}

# SB 的模式编号和官服一致：0=osu 1=taiko 2=fruits 3=mania
RULESET_TO_SB = {"osu": 0, "taiko": 1, "fruits": 2, "mania": 3}


def decode_mods(bitmask) -> list[str]:
    """stable 位掩码 -> acronym 列表。

    NC（512）在位掩码里等同于 DT|NC，两个位会同时亮；显示时只留 NC，否则卡上会
    出现「DT NC」两个徽章表示同一件事。
    """
    try:
        bits = int(bitmask or 0)
    except (TypeError, ValueError):
        return []
    out: list[str] = []
    for bit, name in _MOD_BITS:
        if bits & bit:
            out.append(name)
    if "NC" in out and "DT" in out:
        out.remove("DT")
    return out

def effective_proxies(override: str = "") -> dict:
    """拿到真正该用的代理。

    坑：`urllib.request.getproxies()` 的实现是

        getproxies_environment() or getproxies_registry()

    只要环境里存在**任何**代理相关变量，它就返回非空 dict，`or` 短路，
    **Windows 注册表里的代理根本不会被查**。

    实测证据（AstrBot 进程内）：
        getproxies() -> {'no': 'localhost,127.0.0.1,::1'}
        env          -> {'NO_PROXY': 'localhost,127.0.0.1,::1'}
    注册表里明明是 ProxyEnable=1 / 127.0.0.1:7890，却被完全忽略 ——
    请求于是直连，而直连 api.ppy.sb 要 21 秒才超时。

    所以：没有 http/https 条目时，显式补一次注册表。
    `override` 非空则直接用它（用户在配置里手填的，最可靠）。
    """
    if override:
        return {"http": override, "https": override}

    proxies = dict(urllib.request.getproxies() or {})
    if not any(k in proxies for k in ("http", "https")):
        reg = getattr(urllib.request, "getproxies_registry", None)
        if callable(reg):
            try:
                for key, value in (reg() or {}).items():
                    proxies.setdefault(key, value)
            except Exception:
                pass
    return proxies



class SbApiError(RuntimeError):
    """消息可以安全展示给用户：不含凭据，不含响应正文。"""


class SbApi:
    """`https://api.ppy.sb` 的同步客户端。

    和官服那个 `OsuApi` 一样是 urllib 同步实现 —— 调用方要用
    `asyncio.to_thread(...)` 包起来，不要直接 await。
    私服不需要任何凭据，所以这里没有 token、也没有任何密钥可泄漏。
    """

    def __init__(self, base_url: str = SB_BASE, timeout: int = 30,
                 proxy: str = ""):
        self.base = str(base_url or SB_BASE).rstrip("/")
        self.timeout = int(timeout)
        # 自建 opener，**显式**带上系统代理。
        #
        # 不能用 urllib.request.urlopen()：它走的是全局 opener，任何库调一次
        # install_opener() 就会把它换掉；被换成一个不带 ProxyHandler 的 opener 时，
        # 请求会直连。而这台机器上 api.ppy.sb 直连要 22 秒才超时
        # （实测：直连 22.10s URLError TimeoutError 10060，走代理 0.12~0.23s）。
        # 自建 opener 不受全局状态影响。
        self.proxies = effective_proxies(proxy)
        self._opener = urllib.request.build_opener(
            urllib.request.ProxyHandler(self.proxies or {}))

    # ─────────────────── 临时诊断（排查完删除） ───────────────────

    @staticmethod
    def _diag_dir():
        from pathlib import Path as _P
        try:
            from astrbot.core.utils.astrbot_path import get_astrbot_data_path
            d = _P(get_astrbot_data_path()) / "plugin_data" / "astrbot_plugin_osu_scorecard"
        except Exception:
            d = _P(__file__).resolve().parent / "_diag"
        try:
            d.mkdir(parents=True, exist_ok=True)
            return d
        except Exception:
            return None

    def _record(self, exc, url, elapsed):
        """把连接失败的真实原因写下来。本身绝不抛异常。"""
        try:
            import os
            import socket
            import sys
            import traceback

            reason = getattr(exc, "reason", None)
            lines = [
                "=" * 72,
                "time      : " + __import__("time").strftime("%Y-%m-%d %H:%M:%S"),
                "exc       : " + type(exc).__module__ + "." + type(exc).__name__,
                "reason    : " + repr(reason),
                "str(exc)  : " + str(exc),
                "url       : " + url,
                "elapsed   : %.2fs" % elapsed,
                "self.timeout: %s" % self.timeout,
                "socket默认超时: " + repr(socket.getdefaulttimeout()),
                "getproxies: " + repr(urllib.request.getproxies()),
                "self.proxies: " + repr(getattr(self, "proxies", None)),
                "proxies_final(补注册表后): " + repr(getattr(self, "proxies", None)),
                "全局opener: " + repr(urllib.request._opener),
                "全局opener是否带ProxyHandler: " + repr(
                    any(type(h).__name__ == "ProxyHandler"
                        for h in (getattr(urllib.request._opener, "handlers", []) or []))),
                "env proxy : " + repr({k: v for k, v in os.environ.items() if "proxy" in k.lower()}),
                "python    : " + sys.executable,
                "argv0     : " + (sys.argv[0] if sys.argv else ""),
                "cwd       : " + repr(os.getcwd()),
                "traceback :",
                traceback.format_exc(),
            ]
            block = "\n".join(lines) + "\n"

            # 两处都写：解析出来的路径可能因为 cwd 不对而跑偏，
            # 绝对路径这份一定能读到。
            targets = []
            d = self._diag_dir()
            if d is not None:
                targets.append(d / "sb_error.log")
            import os as _os
            targets.append(__import__("pathlib").Path(
                r"D:\LLBot\bin\astrbot\data\plugin_data\astrbot_plugin_osu_scorecard\sb_error.log"))
            seen = set()
            for t in targets:
                key = str(t).lower()
                if key in seen:
                    continue
                seen.add(key)
                try:
                    t.parent.mkdir(parents=True, exist_ok=True)
                    with t.open("a", encoding="utf-8") as fh:
                        fh.write(block)
                except Exception:
                    pass

            try:
                from astrbot.api import logger as _log
                _log.error("[scorecard][SB诊断] " + block)
            except Exception:
                print("[scorecard][SB诊断] " + block, flush=True)
        except Exception:
            pass

    @staticmethod
    def _friendly(exc):
        """reason -> 用户能看懂的一句话。"""
        import socket
        reason = getattr(exc, "reason", None)
        text = (str(reason) if reason is not None else str(exc)).lower()
        if isinstance(reason, socket.timeout) or "timed out" in text:
            return "连接超时"
        if "getaddrinfo" in text or "name or service not known" in text or "11001" in text:
            return "DNS 解析失败"
        if "refused" in text or "10061" in text:
            return "连接被拒绝"
        if "ssl" in text or "certificate" in text:
            return "TLS/证书错误"
        if "proxy" in text or "407" in text:
            return "代理出错"
        if "unreachable" in text or "10051" in text:
            return "网络不可达"
        return ""

    # ─────────────────────────── transport ───────────────────────────

    def _get(self, path: str, **params):
        url = self.base + path
        if params:
            url += "?" + urllib.parse.urlencode(
                {k: v for k, v in params.items() if v is not None})
        req = urllib.request.Request(
            url, headers={"Accept": "application/json",
                          "User-Agent": "astrbot-osu-scorecard/1.1"})
        import time as _time
        _t0 = _time.monotonic()
        # 正常响应 0.1~0.3 秒，所以超时不用给 30 秒 —— 给短一点 + 重试，
        # 偶发抖动时能自己恢复，真挂了也能快点告诉用户。
        timeout = min(self.timeout, 10)
        last = None
        for attempt in range(3):
            try:
                with self._opener.open(req, timeout=timeout) as resp:
                    payload = json.loads(resp.read() or b"{}")
                break
            except urllib.error.HTTPError as exc:
                # 不回声响应正文：里面可能带服务端内部信息。
                raise SbApiError(f"SB 私服 HTTP {exc.code} at {path}") from None
            except Exception as exc:  # noqa: BLE001
                last = exc
                if attempt < 2:
                    _time.sleep(0.6 * (attempt + 1))
                    continue
                # 临时诊断：把真实 reason 落盘，排查完删掉这段调用。
                self._record(exc, url, _time.monotonic() - _t0)
                hint = self._friendly(exc)
                detail = (hint + "：" if hint else "") + type(exc).__name__
                raise SbApiError(f"连不上 SB 私服（{detail}）") from None
        _ = last

        # 统一脱壳：{"status": "success", ...} / {"status": "<错误文本>"}
        if isinstance(payload, dict) and "status" in payload:
            status = payload.get("status")
            if status != "success":
                raise SbApiError(f"SB 私服返回：{status}")
        return payload

    # ─────────────────────────── endpoints ───────────────────────────

    def search_players(self, query: str) -> list[dict]:
        data = self._get("/v1/search_players", q=query)
        rows = data.get("result") if isinstance(data, dict) else None
        return rows if isinstance(rows, list) else []

    def player_id(self, name: str) -> int | None:
        rows = self.search_players(name)
        if not rows:
            return None
        # 优先精确匹配（忽略大小写），否则退回第一条 —— 私服的搜索是模糊的。
        want = str(name).strip().lower()
        for row in rows:
            if str(row.get("name", "")).lower() == want:
                return row.get("id")
        return rows[0].get("id")

    def player_info(self, player_id=None, name=None, scope: str = "all") -> dict:
        data = self._get("/v1/get_player_info", scope=scope, id=player_id, name=name)
        return data.get("player") or {} if isinstance(data, dict) else {}

    def player_scores(self, player_id=None, name=None, mode: int | str = 3,
                      scope: str = "recent", limit: int = 50,
                      include_failed: bool = False) -> list[dict]:
        """scope='recent' 是最近成绩（官服做不到的那个），'best' 是最佳成绩。"""
        if isinstance(mode, str):
            mode = RULESET_TO_SB.get(mode.lower(), 3)
        data = self._get("/v1/get_player_scores", scope=scope, id=player_id,
                         name=name, mode=int(mode), limit=int(limit),
                         include_failed=str(bool(include_failed)).lower())
        rows = data.get("scores") if isinstance(data, dict) else None
        return rows if isinstance(rows, list) else []

    def score_info(self, score_id) -> dict:
        data = self._get("/v1/get_score_info", id=int(score_id))
        return data.get("score") or {} if isinstance(data, dict) else {}

    def map_info(self, map_id=None, md5=None) -> dict:
        data = self._get("/v1/get_map_info", id=map_id, md5=md5)
        return data.get("map") or {} if isinstance(data, dict) else {}


# ─────────────────────────── 资料归一化 ───────────────────────────

def profile_to_osu(info: dict, ruleset: str = "mania") -> dict:
    """SB 的 player 对象 -> 官服 `/users/...` 那种扁平资料。

    `info` 是 `SbApi.player_info()` 的返回值，形状是：
        {"info": {id, name, country, ...}, "clan": ..., "stats": {"3": {...}}}
    所以 id/name 在 **`info["info"]` 里**，不在顶层 —— 第一版就是漏了这一层，
    结果 user_id/username/avatar_url 全是 None。这里两种形状都兼容。
    """
    info = info or {}
    ident = info.get("info") if isinstance(info.get("info"), dict) else info
    stats = info.get("stats") or {}
    # stats 的键是**字符串**模式号（"0".."8"），不是 int。
    mode = RULESET_TO_SB.get(str(ruleset).lower(), 3)
    per = stats.get(str(mode)) or stats.get(mode) or {}
    pid = ident.get("id")

    return {
        "user_id": pid,
        "username": ident.get("name"),
        # 私服头像：{SB_AVATAR}/{player_id}。实测按 id 变化，
        # 不存在的 id 会退回一张默认图（不会 404）。
        "avatar_url": f"{SB_AVATAR}/{pid}" if pid else None,
        "total_pp": per.get("pp"),
        # 私服的 stats 没有全球排名字段（玩家池是独立的），留空更诚实。
        "global_rank": None,
        # 私服自带的总分 / 场次 / 最大连击，卡片暂时不用，留着方便以后加。
        "server": "sb",
        "sb_tscore": per.get("tscore"),
        "sb_plays": per.get("plays"),
        "sb_acc": per.get("acc"),
        "sb_max_combo": per.get("max_combo"),
    }


def score_to_osu(raw: dict, map_info: dict | None = None,
                 username: str | None = None) -> tuple[dict, dict, dict]:
    """SB 成绩 -> (score, beatmap, beatmapset)，形状对齐官服 v2。

    对齐形状（而不是另写一套卡片的取值逻辑）是刻意的：`card.build_card` 已经
    用真实成绩标定过，只要喂给它官服形状，整条渲染链路一行都不用改。

    `map_info`：**强烈建议传**。SB 成绩里内嵌的 `beatmap.max_combo` 是脏数据
    （等于玩家连击而不是谱面满连），只有 `/v1/get_map_info` 给的是真值。
    没传时退回内嵌值，并让人一眼能看出这是退化的结果。
    """
    raw = raw or {}
    embedded = raw.get("beatmap") or {}
    info = map_info or {}

    # 谱面：优先用 get_map_info 的，缺字段再退回成绩内嵌的
    bm_id = info.get("id") or embedded.get("id")
    set_id = info.get("set_id") or embedded.get("set_id")
    # 真实满连只在 get_map_info 里；内嵌那个不能用
    true_max_combo = info.get("max_combo")
    if true_max_combo is None:
        true_max_combo = embedded.get("max_combo")

    def pick(key, default=None):
        v = info.get(key)
        return v if v is not None else embedded.get(key, default)

    beatmap = {
        "id": bm_id,
        "beatmapset_id": set_id,
        "difficulty_rating": pick("diff"),
        # 官服把 OD 放在 accuracy、HP 放在 drain
        "accuracy": pick("od"),
        "drain": pick("hp"),
        "ar": pick("ar"),
        "bpm": pick("bpm"),
        "cs": pick("cs"),
        "status": pick("status"),
        "max_combo": true_max_combo,
        "version": pick("version"),
        "mode": pick("mode", 3),
        # 私服没有星级以外的难度属性接口，留 None 让卡片那格退回默认
        "total_length": pick("total_length"),
    }

    beatmapset = {
        "title": pick("title"),
        "artist": pick("artist"),
        "creator": pick("creator"),
        # SB 没有封面接口，走官服 CDN。这张图不在官服上就会 404，
        # 渲染器会退回纯色背景 —— 比给个错图好。
        "covers": {"card": f"{OSU_COVER}/beatmaps/{set_id}/covers/card.jpg",
                   "cover": f"{OSU_COVER}/beatmaps/{set_id}/covers/cover.jpg"}
        if set_id else {},
    }

    counts = _counts_from_sb(raw)
    score = {
        "id": raw.get("id"),
        # SB 直接给总分
        "total_score": raw.get("score"),
        "pp": raw.get("pp"),
        # 刻意**不设** `accuracy`。
        #
        # SB 的 `acc` 是 **stable 口径**（实测 99.419，而我们用判定算出的 stable
        # 准确率是 99.4185 —— 同一回事）。官服 `score.accuracy` 是 lazer 口径，
        # 卡片拿它填 LAZER ACC 那一格。若把 SB 的 stable 值塞进 lazer 槽，
        # 两个槽会显示同一个数，等于把 lazer 那个数标错。
        #
        # 留空后 card.build_card 会用 `lazer_accuracy(counts)` 自己按 305 权重算，
        # 得到真正意义不同的第二个数（实测 99.10%）。大字那格仍然是
        # `stable_accuracy(counts)`，和 SB 的官方值一致。
        "max_combo": raw.get("max_combo"),
        "mods": decode_mods(raw.get("mods")),
        "statistics": counts,
        "rank": raw.get("grade"),
        # SB has no `passed` boolean; an F grade denotes an ended failed play.
        # The density marker uses this flag and the judgement count.
        "passed": str(raw.get("grade") or "").upper() != "F",
        "ruleset_id": raw.get("mode", 3),
        "ended_at": raw.get("play_time"),
        "user": {"id": raw.get("userid"), "username": username},
        "server": "sb",
        # 原始 acc 留着，方便排查/以后想改口径
        "sb_acc": raw.get("acc"),
    }
    return score, beatmap, beatmapset


# ─────────────────── 两个成绩接口的形状差异（重要）───────────────────
#
# 私服的两个成绩接口返回的**不是同一个形状**，实测（抓真响应比对过）：
#
#   /v1/get_player_scores   'beatmap'(内嵌), acc, grade, max_combo, mods, n*,
#                           perfect, play_time, pp, score, status, time_elapsed, id
#                           —— **没有 `userid`**
#   /v1/get_score_info      client_flags, map_md5, online_checksum, **userid**,
#                           + 上面那些标量
#                           —— **没有 `beatmap`**
#
# 于是「谱面的指纹」和「玩家的 id」各只有一半接口给。两个都给不出来时，
# `s <id> -sb` 会渲染出一张没有曲名/难度/满连的空卡，`r -sb` 会永远没有 TOTAL PP
# —— 这两个 bug 都真实发生过，是自检喂真响应才暴露的。
#
# 把这段判断抽成纯函数（而不是散在 main.py 的 async 方法里），是为了让自检
# 能直接对着**生产用的同一个函数**跑两种形状，不会再出现「测试喂的形状和生产
# 收到的形状不一致」那种假通过。

def score_map_md5(raw: dict) -> str | None:
    """成绩对象里能拿到的谱面指纹，两种接口各给一半。"""
    raw = raw or {}
    return (raw.get("beatmap") or {}).get("md5") or raw.get("map_md5")


def score_user_id(raw: dict) -> int | None:
    """成绩对象里的玩家 id。只有 `/v1/get_score_info` 会给。"""
    raw = raw or {}
    try:
        return int(raw.get("userid"))
    except (TypeError, ValueError):
        return None


def _counts_from_sb(raw: dict) -> dict:
    """SB 的 ngeki/n300/nkatu/n100/n50/nmiss -> 官服 lazer 判定名。

    mania 的对应关系（stable 口径）：
        ngeki(320/MARVELOUS) -> perfect
        n300                 -> great
        nkatu(200)           -> good
        n100                 -> ok
        n50                  -> meh
        nmiss                -> miss

    这里用 lazer 名（perfect/great/...）是因为 `card.MANIA_KEYS` 两套名字都认，
    而这套更通用；同时**显式补 0**，因为 SB 在计数为 0 时会省略该键，
    卡片那边靠 `.get(k, 0)` 兜底但显式给更清楚。
    """
    return {
        "perfect": int(raw.get("ngeki") or 0),
        "great": int(raw.get("n300") or 0),
        "good": int(raw.get("nkatu") or 0),
        "ok": int(raw.get("n100") or 0),
        "meh": int(raw.get("n50") or 0),
        "miss": int(raw.get("nmiss") or 0),
    }
