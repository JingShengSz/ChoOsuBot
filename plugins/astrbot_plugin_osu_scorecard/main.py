"""osu!mania score card — render a play into the PSD template and post the PNG.

Commands (no spaces in any of them):

    p                 the most recent PASSED play
    r                 the most recent play, cleared or not
    s <id|link>       one specific score, by id or by osu.ppy.sh/scores/<id> link
    bind <username>   remember which osu! account belongs to this QQ

Plus: any message containing an osu! score link renders it automatically.

The card is the PSD at `template/osu_score_template_v1.psd`; Photoshop is driven
over COM to fill it. See psd.py for the two ExtendScript rules this relies on,
and README.md for the whole picture.
"""
from __future__ import annotations

import asyncio
import re
import sys
import time
from io import BytesIO
from pathlib import Path

# 插件自己的目录上 sys.path —— 万一 AstrBot 把本文件当顶层模块加载
# （而不是包），下面的绝对兜底导入才找得到同目录的兄弟模块。
PLUGIN_DIR = Path(__file__).resolve().parent
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

import aiohttp
from PIL import Image

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.star import Context, Star
import astrbot.api.message_components as Comp

try:  # 正常情况：AstrBot 按包导入，相对导入成立
    from . import card as cardmod
    from . import map_combo as map_combomod
    from . import oauth as oauthmod
    from . import osu_api
    from . import raster
    from . import render as rendermod
    from . import sb_api
    from .psd import PhotoshopError, ScoreCardRenderer
    from .store import DEFAULT_SERVER, SERVER_LABEL, Store, norm_server
except ImportError:  # 兜底：被当顶层模块加载时，走绝对导入
    import card as cardmod
    import map_combo as map_combomod
    import oauth as oauthmod
    import osu_api
    import raster
    import render as rendermod
    import sb_api
    from psd import PhotoshopError, ScoreCardRenderer
    from store import DEFAULT_SERVER, SERVER_LABEL, Store, norm_server

PLUGIN_NAME = "astrbot_plugin_osu_scorecard"

#: 授权链接那条消息发出后多少秒自动撤回。0 = 不撤回。
#: 链接本身是给别人点的，留在群里碍眼，所以默认 30 秒收掉。
AUTO_RECALL_SECONDS = 30

# osu! 的四个规则集。`mode` 指令接受这些值。
RULESETS = ("osu", "taiko", "fruits", "mania")
RULESET_LABEL = {
    "osu": "osu!standard",
    "taiko": "osu!taiko",
    "fruits": "osu!catch",
    "mania": "osu!mania",
}

#: 私服后缀。用户在任一指令末尾加 `-sb` 就表示这条查的是 SB 私服。
#: 允许 `-sb` / `--sb`（大小写随意），也接受中文写法 `-私服`。
#:
#: 必须是**整串开头**或**前面有空白**才算后缀 —— 私服的用户名允许连字符
#: （SB 的校验是 `^[\w \[\]-]{2,15}$`），所以叫 `Foo-sb` 的玩家不能被误判成
#: 「查 Foo 的私服成绩」。
SB_FLAG_RE = re.compile(r"(?:^|\s)--?sb\s*$|(?:^|\s)-私服\s*$", re.I)

HELP_TEXT = (
    "osu! 成绩卡 —— 可用指令：\n"
    "  p              最近【通过】的成绩（出成绩卡）\n"
    "  r              最近【游玩】的成绩（没通过也算）\n"
    "  s <成绩ID>     指定成绩，ID 或成绩链接都行\n"
    "  bind <名字>    把 osu! 用户名绑定到你的 QQ\n"
    "  mode <模式>    切换模式：osu / taiko / fruits / mania\n"
    "  authorize      重新拿一次官服授权链接（绑定后没授权时用）\n"
    "  help           这条帮助\n"
    "\n"
    "每条指令末尾加 -sb 就是查【SB 私服】的成绩，不加是官服。\n"
    "  例：p -sb           私服的最近通过\n"
    "  例：bind 名字 -sb   把名字绑定到你的 SB 私服账号\n"
    "官服和私服是两套独立绑定，互不影响。\n"
    "\n"
    "直接把成绩链接贴到群里也会自动出图，不用打指令。\n"
    "\n"
    "【官服 p / r 需要授权一次】\n"
    "绑定时会给你一个 osu! 授权链接，点开点「Authorize」就行。\n"
    "授权完成后 p / r 才能查最近成绩；s <成绩ID> 和贴链接不需要授权。\n"
    "没收到链接、或者链接过期了，发 authorize 重新要一个。\n"
    "私服（-sb）不需要任何授权，绑定后直接可用。\n"
    "\n"
    "发图较慢时先等一下 —— 渲染要花点时间。"
)

# Any of these shapes, anywhere in a message. Mirrors the matcher the sibling
# replay plugin already uses so the two agree on what a "score link" is.
SCORE_URL_RE = re.compile(r"osu\.ppy\.sh/(?:#/)?(?:community/)?scores/(\d{3,})", re.I)

# Used to keep the automatic link handler from double-handling an explicit command.
COMMAND_NAMES = ("p", "r", "s", "bind", "mode", "authorize")

OUTPUT_PREFIX = "scorecard_"

# Anything token-shaped, and any Authorization header, is stripped before an
# exception message is ever shown to a user. The API client already keeps
# credentials out of its own messages; this is the second line of defence.
_SCRUB_RE = re.compile(r"[A-Za-z0-9_\-]{32,}")


def _plugin_data_dir(name: str) -> Path:
    """Persistent storage. Never write inside the plugin directory itself."""
    try:
        from astrbot.core.utils.astrbot_path import get_astrbot_plugin_data_path

        base = Path(get_astrbot_plugin_data_path())
    except Exception:  # older AstrBot without that helper
        base = Path.cwd() / "data" / "plugin_data"
    d = base / name
    d.mkdir(parents=True, exist_ok=True)
    return d


class OsuScoreCardPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig | None = None):
        super().__init__(context)
        self.config = config or {}
        self.data_dir = _plugin_data_dir(getattr(self, "name", PLUGIN_NAME))
        self.store = Store(self.data_dir, cache_minutes=self.cache_minutes)

        # Photoshop renders one document at a time; two people asking at once
        # would otherwise fight over the same application instance.
        self._render_lock = asyncio.Lock()
        self._api = None
        self._api_error: str | None = None
        self._sb_client = None

        # 谱面满连的解析器（下载 .osu 自己数 + 磁盘缓存）。懒建：建它要读配置文件，
        # 而绝大多数消息根本不出卡。
        self._map_combo: map_combomod.MapComboResolver | None = None

        # OAuth (official server only — the private one needs no authorization).
        self._pending = oauthmod.PendingAuth(self.data_dir / "oauth_pending.json")
        self._oauth_server: oauthmod.OAuthCallbackServer | None = None

        # 待执行的「若干秒后撤回」任务。必须留着强引用，否则事件循环只持弱引用，
        # 任务可能在 sleep 中途被 GC —— 表现为「有时候撤了有时候没撤」。
        self._recall_tasks: set = set()

    # ─────────────────────────── configuration ───────────────────────────

    def _cfg(self, key: str, default):
        value = self.config.get(key, default) if hasattr(self.config, "get") else default
        return default if value in (None, "") else value

    @property
    def ruleset(self) -> str:
        r = str(self._cfg("default_ruleset", "mania")).lower()
        return r if r in RULESETS else "mania"

    def _ruleset_for(self, qq: str, server: str = DEFAULT_SERVER) -> str:
        """该 QQ 在**这个服**绑定的模式，没绑或没设就用默认。

        总 PP / 排名是分模式的，所以模式要跟着绑定走而不是全局一个值；
        官服和私服的绑定也是分开的，所以服务器同样要传进来。
        """
        return self.store.ruleset_for(qq, server) or self.ruleset

    @property
    def cache_minutes(self) -> int:
        try:
            return max(0, int(self._cfg("cache_minutes", 10)))
        except (TypeError, ValueError):
            return 10

    @property
    def output_keep(self) -> int:
        try:
            return max(1, int(self._cfg("output_keep", 20)))
        except (TypeError, ValueError):
            return 20

    @property
    def auto_link(self) -> bool:
        return bool(self._cfg("auto_link", True))

    @property
    def http_proxy(self) -> str:
        """手动指定的代理。留空 = 自动探测。

        自动探测在 AstrBot 进程里靠不住：`urllib.request.getproxies()` 的实现是
        `getproxies_environment() or getproxies_registry()`，只要环境里有 NO_PROXY
        这类变量就返回非空 dict，`or` 短路 —— 注册表里的代理被静默忽略，请求变直连。
        这一项是用户自己能救自己的路。
        """
        return str(self._cfg("http_proxy", "") or "").strip()

    @property
    def pp_max_mode(self) -> str:
        """`computed` = 自己算全 320 的理论最大 PP；`dash` = 退回显示的 "--"。

        公式随 osu! 版本会失准，这个开关是逃生口。
        （原先这里写成 self._pp_max_mode()，但那个方法从来没定义过 ——
        跑到这行就抛 AttributeError，渲染直接失败。）
        """
        return str(self._cfg("pp_max_mode", "computed")).strip().lower()

    @property
    def map_combo_cache_days(self) -> float:
        """谱面满连缓存的有效期（天）。0 = 不缓存，每次都重新下载 .osu。

        一个 bid 的满连不会变，所以默认给 30 天；这个开关只是给「谱面被改过」
        和排查留一条路。
        """
        try:
            return max(0.0, float(self._cfg("map_combo_cache_days", 30)))
        except (TypeError, ValueError):
            return 30.0

    @property
    def map_combo_fetch(self) -> bool:
        """关掉之后不再下载 .osu，满连直接走 API 的值（旧行为）。

        留着是因为它是唯一一处「出卡会多发一个网络请求」的地方 ——
        用户要是嫌慢或者网络环境差，得能一键退回去。
        """
        value = self._cfg("map_combo_fetch", True)
        if isinstance(value, str):
            return value.strip().lower() not in ("0", "false", "no", "off", "")
        return bool(value)

    @property
    def template_path(self) -> Path:
        return Path(str(self._cfg(
            "osu_data_path", r"D:\Cho Osu Bot\template\osu_score_template_v1.psd")))

    @property
    def assets_dir(self) -> Path:
        configured = self._cfg("assets_path", "")
        if configured:
            return Path(str(configured))
        # Default: the assets folder that sits beside the template.
        return self.template_path.parent / "assets"

    @property
    def spec_path(self) -> Path:
        """layer_mapping.json — Pillow 渲染器的版式来源。

        默认就在模板旁边。模板改了要重新导出（build/dump_ink.jsx 补 ink 框，
        build/export_static.jsx 重导静态层），否则 PIL 出图会和设计稿脱节。
        """
        configured = self._cfg("spec_path", "")
        if configured:
            return Path(str(configured))
        return self.template_path.parent / "layer_mapping.json"

    @property
    def credential_file(self) -> Path:
        """The local osu! OAuth file, when one exists.

        Defaults to the file the renderer already keeps, so a machine that has
        already set osu! up needs no WebUI entry at all. `OsuApi.from_file` reads
        `osu_client_id` / `osu_client_secret` from it; if the file is missing the
        plugin falls back to the two config fields instead.
        """
        return Path(str(self._cfg(
            "osu_credential_file", r"D:\Cho Osu Bot\renderer\data\osu_oauth.local.json")))

    @property
    def output_dir(self) -> Path:
        d = self.data_dir / "output"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def sb_api_url(self) -> str:
        """SB 私服的 API 根地址。

        私服不需要任何凭据，所以这里只有地址、没有密钥可泄漏。
        想换服（另一个 bancho 实现）改这一项即可。
        """
        return str(self._cfg("sb_api_url", "https://api.ppy.sb")).rstrip("/")

    # ─────────────────────────── oauth config ───────────────────────────

    @property
    def oauth_enabled(self) -> bool:
        """官服授权流程的总开关。私服不受影响。"""
        value = self._cfg("oauth_enabled", True)
        if isinstance(value, str):
            return value.strip().lower() not in ("0", "false", "no", "off", "")
        return bool(value)

    @property
    def oauth_callback_host(self) -> str:
        """回调服务绑定的地址。

        默认 `127.0.0.1` —— 只对本机浏览器有效（本地自测够用）。
        要让**别的机器上的用户**点链接回到这里，必须改成一个它们能访问到的
        地址，并且同时在 osu! 的 OAuth 应用里登记对应的 Callback URL。
        """
        return str(self._cfg("oauth_callback_host", "127.0.0.1")).strip() or "127.0.0.1"

    @property
    def oauth_callback_port(self) -> int:
        try:
            return max(1, min(65535, int(self._cfg("oauth_callback_port", 6199))))
        except (TypeError, ValueError):
            return 6199

    @property
    def oauth_redirect_base(self) -> str:
        """外部可达的基地址。留空 = 用 host:port 拼一个本机地址。

        部署到公网时填成 `https://你的域名`，否则用户浏览器回不来。
        """
        return str(self._cfg("oauth_redirect_base", "")).strip().rstrip("/")

    @property
    def oauth_redirect_uri(self) -> str:
        """osu! 授权页里要带的 `redirect_uri`。

        **必须和 osu! 后台登记的 Callback URL 一字不差**，osu! 是字面比较。
        """
        base = self.oauth_redirect_base
        if not base:
            base = f"http://{self.oauth_callback_host}:{self.oauth_callback_port}"
        return oauthmod.redirect_uri(base)

    @property
    def oauth_ready(self) -> bool:
        """能不能给用户发授权链接：开关开着 + 凭据可用。

        凭据拿不到时不要给用户一个点开就报错的链接 —— 那种误导比直接说
        「还没配好」更糟。
        """
        if not self.oauth_enabled:
            return False
        try:
            self._client()
        except Exception:  # noqa: BLE001
            return False
        return True

    # ─────────────────────────── osu! API ───────────────────────────

    def _sb(self):
        """The SB private-server client. No credentials involved at all."""
        if self._sb_client is None:
            self._sb_client = sb_api.SbApi(self.sb_api_url, proxy=self.http_proxy)
        return self._sb_client

    def _any_client(self, server: str):
        """按服取客户端。官服是 OsuApi，私服是 SbApi。"""
        return self._sb() if norm_server(server) == "sb" else self._client()

    def _map_combo_resolver(self):
        """谱面满连解析器（下载 .osu 自己数 + 磁盘缓存）。

        缓存落在 `data/plugin_data/<插件名>/map_combo_cache.json` —— 和
        bindings.json / players.json 同一个地方，**不在插件目录里**：
        插件目录会被 AstrBot 升级覆盖，而且它在 git 里。

        代理在构造时定下来，和 `_sb()` / `_client()` 一样。配置改了要重启插件
        （这两个客户端本来也是这个行为，保持一致）。
        """
        if self._map_combo is None:
            self._map_combo = map_combomod.MapComboResolver(
                self.data_dir,
                ttl_days=self.map_combo_cache_days,
                proxy=self.http_proxy,
                enable_cache=self.map_combo_cache_days > 0)
        return self._map_combo

    async def _counted_map_combo(self, score: dict, beatmap: dict,
                                 server: str) -> int | None:
        """这一局的谱面满连，用 .osu 数出来的那个值（数不出来就是 None）。

        规则与降级顺序见 `card.resolve_map_max_combo()`；这里只负责「值从哪来」：

        · 满连（`is_perfect_combo`）时**不下载** —— 玩家自己的连击就是满连，
          精确且零成本，这是最常见的路径。
        · 官服：`https://osu.ppy.sh/osu/<bid>`，公开端点，不需要任何授权。
        · 私服：**不**走这里。SB 的谱面真值在 `/v1/get_map_info` 里
          （成绩内嵌的 `beatmap.max_combo` 是脏数据），那一次调用已经在
          `_sb_score_bundle()` 做过，`beatmap["max_combo"]` 拿到的就是它。
        · 失败一律返回 None，由卡片退回 API 的值或 "--"。**绝不让满连这一格
          把整张卡弄挂**：为了一个数字丢掉整张成绩卡是不划算的。
        """
        if not self.map_combo_fetch:
            return None
        if score.get("is_perfect_combo") and cardmod.as_positive_int(score.get("max_combo")):
            return None
        if norm_server(server) == "sb":
            return None
        # 官服成绩对象的谱面 id 有两个位置：内嵌 beatmap.id（`/scores/<id>` 有），
        # 顶层 beatmap_id（部分形状只有这个）。取不到就没得数。
        bid = beatmap.get("id") or score.get("beatmap_id") or (
            (score.get("beatmap") or {}).get("id"))
        if not bid:
            return None
        try:
            resolver = self._map_combo_resolver()
            value = await self._call(resolver.resolve, bid)
        except Exception as exc:  # noqa: BLE001
            logger.info(f"[scorecard] 谱面满连数不出来（{type(exc).__name__}），"
                        f"退回 API 值")
            return None
        if value:
            logger.info(f"[scorecard] 谱面满连 bid={bid} 数 .osu 得到 {value}")
        elif getattr(resolver, "last_error", ""):
            logger.info(f"[scorecard] 谱面满连 bid={bid} 数不出来：{resolver.last_error}")
        return value

    def _client(self):
        """官服 API 客户端。

        用的是插件自带的 `osu_api.py`（从渲染器 vendored 进来，纯标准库、无外部依赖），
        所以插件是自包含的：不再需要 renderer_path，服务器上也不用额外装渲染器。

        之前这里是从 `mania_render.osu_api` 导入的，服务器上没那个包，
        结果官服查询直接抛 ModuleNotFoundError —— 那就是 bind 报错的根因。
        """
        if self._api is not None:
            return self._api
        if self._api_error:
            raise RuntimeError(self._api_error)
        OsuApi = osu_api.OsuApi
        cred = self.credential_file
        if cred.is_file():
            try:
                self._api = OsuApi.from_file(cred, proxy=self.http_proxy)
            except Exception as exc:  # noqa: BLE001
                self._api_error = f"凭据文件读不了：{cred.name}（{type(exc).__name__}）"
                raise RuntimeError(self._api_error) from None
        else:
            cid = str(self._cfg("osu_client_id", "")).strip()
            secret = str(self._cfg("osu_client_secret", "")).strip()
            if not cid or not secret:
                self._api_error = (
                    "官服还没配凭据。请在插件配置里填 osu_client_id / osu_client_secret，"
                    "或把 osu_credential_file 指向本机的 osu_oauth.local.json。"
                    "查成绩卡和绑定只要客户端凭据；p / r 查最近成绩才需要额外做 OAuth 授权。")
                raise RuntimeError(self._api_error)
            self._api = OsuApi(cid, secret, proxy=self.http_proxy)
        return self._api

    async def _call(self, fn, *args, **kwargs):
        """Run one synchronous osu! API call off the event loop.

        The client is urllib-based, so it must never be awaited directly.
        """
        return await asyncio.to_thread(fn, *args, **kwargs)

    async def _profile(self, username_or_id, use_cache: bool = True,
                       ruleset: str | None = None,
                       server: str = DEFAULT_SERVER) -> dict:
        """A player profile, served from the local cache when it is fresh.

        The compact `user` object embedded in a score lacks statistics, so TOTAL PP
        only exists on a full /users/... response — this is where it comes from.

        `server="sb"` 走 SB 私服：那边没有凭据也不分模式端点，用户名或 id 都能查，
        返回值由 `sb_api.profile_to_osu()` 归一化成和官服一样的扁平形状。
        """
        server = norm_server(server)
        key = str(username_or_id)
        rs = ruleset or self.ruleset
        if use_cache:
            hit = self.store.cached_player(key, rs, server)
            if hit:
                return hit

        if server == "sb":
            client = self._sb()
            # 私服更认数字 id；给的是名字就先搜一次拿 id，搜不到再退回按名字查。
            pid = None
            if key.isdigit():
                pid = int(key)
            else:
                pid = await self._call(client.player_id, key)
            raw = await self._call(client.player_info,
                                   player_id=pid, name=None if pid else key,
                                   scope="all")
            profile = sb_api.profile_to_osu(raw, rs)
            # 搜不到就明确报错，别把空资料当成功返回（否则卡上全是问号）
            if not profile.get("username"):
                raise RuntimeError(f"SB 私服上没有找到玩家 {username_or_id}")
        else:
            client = self._client()
            raw = await self._call(client.user_by_name, key, rs)
            profile = {
                "user_id": raw.get("id"),
                "username": raw.get("username"),
                "avatar_url": raw.get("avatar_url"),
                "total_pp": ((raw.get("statistics") or {}).get("pp")),
                "global_rank": ((raw.get("statistics") or {}).get("global_rank")),
                "server": "osu",
            }

        profile["fetched_at"] = time.time()
        self.store.put_player(key, rs, profile, server)
        self.store.prune_players()
        return profile

    async def _download(self, session: aiohttp.ClientSession, url: str) -> bytes | None:
        if not url:
            return None
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status >= 400:
                    return None
                return await resp.read()
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[scorecard] 下载素材失败 {type(exc).__name__}")
            return None

    # ─────────────────────────── card assembly ───────────────────────────

    @staticmethod
    def _blank() -> Image.Image:
        """A full 1920x1080 transparent canvas.

        Every bitmap handed to Photoshop is composited onto one of these at its
        final coordinates, which is what lets the ExtendScript side place layers
        with `duplicate` alone and never call `translate`.
        """
        return Image.new("RGBA", (1920, 1080), (0, 0, 0, 0))

    def _text_jobs(self, data: cardmod.CardData) -> list[dict]:
        """Layer name -> new string, with a CJK font swap where the text needs one.

        Inter has no CJK glyphs at all, and Photoshop silently substitutes some
        other font when it meets one — which looks fine on this machine and wrong
        on the next. Anything non-ASCII is therefore pinned to Yu Gothic.
        """
        jobs = []
        for name, value in data.to_layers().items():
            text = "" if value is None else str(value)
            job = {"name": name, "value": text, "font": None, "accent": None}
            if any(ord(ch) > 0x2E7F for ch in text):
                job["font"] = "YuGothic-Medium"
            # 服务器标记（官方 / SB 私服）自带颜色，不参与按评级上色。
            if name == "server_tag":
                job["accent"] = getattr(data, "server_tag_color", None)
            jobs.append(job)
        return jobs

    async def _build_rasters(self, session: aiohttp.ClientSession,
                             data: cardmod.CardData) -> tuple[list[dict], dict]:
        """Every bitmap the card needs, each pre-composited onto a 1920x1080 canvas.

        Doing the compositing here (rather than positioning layers inside
        Photoshop) is what keeps the ExtendScript side free of any translate call.
        """
        stamp = f"{int(time.time() * 1000)}"
        work = self.output_dir / f"ras_{stamp}"
        work.mkdir(parents=True, exist_ok=True)
        rasters: list[dict] = []
        meta = {"mods": []}

        def save(img, name):
            p = work / name
            img.save(p)
            return p.as_posix()

        # --- background: the whole canvas, so no positioning is needed ---
        bg_bytes = await self._download(session, data.background_url)
        if bg_bytes:
            try:
                bg = raster.cover_fit(Image.open(BytesIO(bg_bytes)))
                rasters.append({"layer": "beatmap_bg", "group": "bg",
                                "path": save(bg, "bg.png")})
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"[scorecard] 背景解码失败 {type(exc).__name__}")

        # --- avatar: clipped to the template's ellipse at (922,60) ---
        av_bytes = await self._download(session, data.avatar_url)
        if av_bytes:
            try:
                sheet = self._blank()
                sheet.alpha_composite(
                    raster.render_avatar(Image.open(BytesIO(av_bytes)).convert("RGBA")),
                    (922, 60))
                rasters.append({"layer": "player_avatar", "group": "player_info",
                                "path": save(sheet, "avatar.png")})
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"[scorecard] 头像解码失败 {type(exc).__name__}")

        # --- star strip: placed at the template's box origin (60,310) ---
        sheet = self._blank()
        sheet.alpha_composite(raster.render_star_strip(data.star_value, 600), (60, 310))
        rasters.append({"layer": "star_strip", "group": "beatmap_stats",
                        "path": save(sheet, "strip.png")})

        # --- OD / HP bars ---
        for name, value, rng, y in (("od_bar", data.od_value, data.od_range, 520),
                                    ("hp_bar", data.hp_value, data.hp_range, 588)):
            bar = raster.render_stat_bar(value, rng[0], rng[1], width=600, height=12)
            sheet = self._blank()
            sheet.alpha_composite(bar, (60, y))
            rasters.append({"layer": name, "group": "beatmap_stats",
                            "path": save(sheet, f"{name}.png")})

        # --- mod badges: all of them go on mod_1 as one sheet, the rest go blank ---
        mod_sheet, placed = raster.render_mod_row(
            data.mods, self.assets_dir / "mods" / "ready")
        rasters.append({"layer": "mod_1", "group": "mods_block",
                        "path": save(mod_sheet, "mods.png")})
        meta["mods"] = placed
        empty_path = save(self._blank(), "empty.png")
        for i in range(2, raster.MOD_SLOTS + 1):
            rasters.append({"layer": f"mod_{i}", "group": "mods_block", "path": empty_path})

        # --- rank theme: pre-rendered tint + glow per grade ---
        rank_svg = self.assets_dir / "rank_svg"
        grade = (data.grade or "D").upper()
        tint = rank_svg / f"tint_{grade}.png"
        glow = rank_svg / f"glow_{grade}.png"
        if tint.is_file():
            rasters.append({"layer": "_deco_bg_gradient", "group": "bg",
                            "path": tint.as_posix()})
        if glow.is_file():
            rasters.append({"layer": "rank_glow", "group": "signboard", "blend": True,
                            "path": glow.as_posix()})

        return rasters, meta

    def _recolor_accent(self, text_jobs: list[dict], grade: str) -> list[dict]:
        """The accuracy readout takes the grade's colour.

        This is the one text layer whose COLOUR changes, and the only way that
        works on this Photoshop build is SolidColor (see psd.py).
        """
        colors = {r["key"]: r["color"] for r in self._rank_colors()}
        hexv = colors.get(str(grade).upper())
        if hexv:
            for job in text_jobs:
                if job["name"] == "accuracy":
                    job["accent"] = hexv
        return text_jobs

    def _rank_colors(self) -> list[dict]:
        import json
        mapping = self.template_path.parent / "layer_mapping.json"
        try:
            data = json.loads(mapping.read_text(encoding="utf-8"))
            return data.get("rankColors") or []
        except (OSError, ValueError):
            return []

    async def _render(self, event: AstrMessageEvent, data: cardmod.CardData,
                      session: aiohttp.ClientSession) -> Path:
        async with self._render_lock:
            rasters, _meta = await self._build_rasters(session, data)
            jobs = self._recolor_accent(self._text_jobs(data), data.grade)
            out = self.output_dir / f"{OUTPUT_PREFIX}{int(time.time() * 1000)}.png"

            # 引擎选择。默认 auto = 先试 Pillow，失败才退回 Photoshop。
            #
            # Pillow 这条路完全不碰 Photoshop：不用打开 16MB 的 PSD、不用写图层、
            # 不用导出，实测 ~0.4s；走 Photoshop 要 ~34s（实测，同一张卡）。差别几乎
            # 全在「打开 + 导出 PSD」本身，不是可以调优的东西。
            mode = str(self._cfg("renderer", "auto")).strip().lower()
            order = []
            if mode in ("auto", "pil", "pillow"):
                order.append("pil")
            if mode in ("auto", "photoshop", "ps"):
                order.append("photoshop")
            if not order:
                order = ["pil"]

            last_exc: Exception | None = None
            for engine in order:
                started = time.monotonic()
                try:
                    result = await asyncio.to_thread(
                        self._render_once, engine, jobs, rasters, data.grade, out)
                except Exception as exc:  # noqa: BLE001
                    last_exc = exc
                    logger.warning(
                        f"[scorecard] {engine} 渲染失败（{type(exc).__name__}: {exc}），"
                        f"{'换下一个引擎' if engine != order[-1] else '没有后备了'}")
                    continue

                took = time.monotonic() - started
                logger.info(
                    f"[scorecard] 渲染完成 {out.name} engine={engine} {took:.2f}s"
                    + (f" text={result.get('textApplied')}"
                       f" missing={len(result.get('textMissing') or [])}"
                       f" rasters={len(result.get('rasters') or [])}"
                       if engine == "photoshop"
                       else f" text={result.get('text')}"
                            f" rasters={result.get('rasters')}"
                            f" signboard={result.get('signboard')}"))
                event.track_temporary_local_file(str(out))
                self._prune_outputs()
                return out

            raise last_exc if last_exc else RuntimeError("没有可用的渲染引擎")

    def _render_once(self, engine: str, jobs: list[dict], rasters: list[dict],
                     grade: str, out: Path) -> dict:
        """同步跑一个引擎。由 _render 用 to_thread 调，别在这里 await。"""
        if engine == "pil":
            spec = self.spec_path
            r = rendermod.PilScoreCardRenderer(
                spec=spec,
                assets_dir=self.assets_dir,
                work_dir=self.data_dir / "work_pil",
            )
            return r.render(jobs, rasters, r.signboard_chain(grade), out)

        renderer = ScoreCardRenderer(
            template=self.template_path,
            work_dir=self.data_dir / "work",
            timeout_seconds=int(self._cfg("render_timeout_seconds", 180)),
        )
        return renderer.render(jobs, rasters, renderer.signboard_chain(grade), out)

    def _prune_outputs(self) -> None:
        files = sorted(self.output_dir.glob(f"{OUTPUT_PREFIX}*.png"),
                       key=lambda p: p.stat().st_mtime, reverse=True)
        for old in files[self.output_keep:]:
            try:
                old.unlink()
            except OSError:
                pass

    # ─────────────────────────── query paths ───────────────────────────

    async def _render_score(self, event: AstrMessageEvent, score: dict,
                            session: aiohttp.ClientSession,
                            ruleset: str | None = None) -> Path:
        beatmap = score.get("beatmap") or {}
        beatmapset = score.get("beatmapset") or {}
        if not beatmapset and beatmap.get("beatmapset_id"):
            raise RuntimeError("成绩里没有内嵌谱面信息")

        # 服务器跟着成绩走：SB 的 user id 是私服自己的编号，拿去查官服 API 会查到
        # 另一个人（或查不到）。归一化时 `score["server"]` 已经打好标记。
        srv = norm_server(score.get("server") or "osu")
        user = score.get("user") or {}
        profile = None
        if user.get("id"):
            try:
                # 总 PP / 排名是分模式的：成绩自己有 ruleset_id，优先按它查，
                # 查不到再退回调用方给的那个。
                rs = ruleset
                rid = score.get("ruleset_id")
                if rid in (0, 1, 2, 3):
                    rs = ("osu", "taiko", "fruits", "mania")[rid]
                profile = await self._profile(user["id"], ruleset=rs, server=srv)
            except Exception as exc:  # noqa: BLE001
                logger.info(f"[scorecard] 取玩家资料失败，TOTAL PP 留空：{type(exc).__name__}")

        # 谱面满连：非满连时去数 .osu（见 _counted_map_combo）。放在 build_card
        # 之前，因为它决定了卡片上 MAP COMBO 那一格填什么。
        counted_combo = await self._counted_map_combo(score, beatmap, srv)
        data = cardmod.build_card(score, beatmap, beatmapset, profile,
                                  pp_max_mode=self.pp_max_mode,
                                  real_max_combo=counted_combo)
        return await self._render(event, data, session)

    async def _recent_scores(self, username: str, include_fails: bool,
                             ruleset: str | None = None,
                             server: str = DEFAULT_SERVER,
                             user_token: str | None = None
                             ) -> tuple[str, object, str]:
        """Recent plays for one player.

        Returns (status, payload, detail) where status is one of
        "ok" / "empty" / "needs_user_token".

        ── 官服（server="osu"，默认）──────────────────────────────────────────

        `/users/{id}/{ruleset}/scores/recent` 对**应用令牌（client_credentials）**
        一律返回 HTTP 404 —— 带不带 `include_fails`、`/best`、`/firsts`、用用户名
        代替 id、老式路径，全部试过，全 404。osu! 把这个端点放在**用户令牌**
        （authorization_code 流程）后面。

        `user_token` 就是那个令牌，由 `_user_token(qq)` 取（过期会自动刷新）。

        `/users/{id}/recent_activity` 虽然 200，但事件里 `beatmap` 是 `null`、
        也没有成绩 id，填不了卡片的任何一格 —— 所以没有拿它当退路。

        ── 私服（server="sb"）────────────────────────────────────────────────

        私服**不需要任何授权**：`/v1/get_player_scores?scope=recent` 用用户名或 id
        就能查。这正是官服缺的那块能力，所以 `p -sb` / `r -sb` 一直是能用的。

        `include_fails` 和私服的 `include_failed` 语义一致（都是"是否包含失败"），
        直接透传，不需要取反。
        """
        server = norm_server(server)
        rs = ruleset or self.ruleset

        if server == "sb":
            return await self._sb_recent(username, include_fails, rs)

        if not user_token:
            return "needs_user_token", None, ""

        client = self._client()
        try:
            rows = await self._call(client.recent_scores, username, rs,
                                    include_fails=include_fails, limit=50,
                                    user_token=user_token)
        except Exception as exc:  # noqa: BLE001
            text = str(exc)
            # 401/403 说明令牌被撤销或失效，404 仍是"没授权"的老面孔；
            # 两种都当成「需要（重新）授权」，由指令层决定怎么提示。
            if "HTTP 404" in text or "HTTP 401" in text or "HTTP 403" in text:
                return "needs_user_token", None, text
            raise
        if not rows:
            return "empty", None, ""
        return "ok", rows[0], ""

    # ─────────────────────────── SB 私服查询 ───────────────────────────

    async def _sb_player_id(self, username: str):
        """名字 -> 私服 player_id。给的已经是数字就直接用。

        私服的搜索是模糊匹配，所以先找完全同名（忽略大小写）的那条，
        找不到才退回第一条 —— 否则 `Chino` 可能被解析成 `Chino2`。
        """
        key = str(username).strip()
        if key.isdigit():
            return int(key)
        return await self._call(self._sb().player_id, key)

    async def _sb_score_bundle(self, raw: dict, username: str | None = None,
                               uid: int | None = None) -> dict:
        """一条私服成绩 -> 官服形状的成绩对象（内嵌 beatmap / beatmapset）。

        ⚠️ 私服的两个成绩接口返回的**不是同一个形状**，实测：
            /v1/get_player_scores  -> 有内嵌 `beatmap`，**没有 `userid`**
            /v1/get_score_info     -> 有 `userid` 和 `map_md5`，**没有 `beatmap`**
        所以两边都要兼容，否则：
          · 只按 `beatmap.md5` 找谱面 => `s <id> -sb` 整张卡没有曲名/难度/满连
          · 只按 `userid` 找玩家   => `r -sb` 永远没有 TOTAL PP
        这两个 bug 都真实存在过，是自检里喂真响应才暴露出来的。

        另外必须单独调一次 `/v1/get_map_info`：SB 成绩里内嵌的 `beatmap.max_combo`
        是脏数据（实测等于玩家连击而不是谱面满连），谱面真值只在这个接口里。
        那一次调用失败也不致命 —— 退回内嵌值，让卡片少一个精确数字，而不是整张卡挂掉。
        """
        sb = self._sb()
        # 谱面指纹：get_player_scores 给内嵌 beatmap.md5，get_score_info 给 map_md5
        md5 = sb_api.score_map_md5(raw)
        map_info: dict = {}
        if md5:
            try:
                map_info = await self._call(sb.map_info, md5=md5)
            except Exception as exc:  # noqa: BLE001
                logger.info(
                    f"[scorecard] SB 谱面详情取不到，满连退回内嵌值：{type(exc).__name__}")

        # 玩家：uid 优先，取不到就按名字反查。两条接口一半给 id、一半给名字。
        if uid is None:
            uid = sb_api.score_user_id(raw)
        if username is None:
            # get_score_info 有 userid；拿不到就用 uid 字符串兜底
            username = str(uid) if uid else "?"
            if uid:
                try:
                    info = await self._call(sb.player_info, player_id=uid, scope="info")
                    username = ((info.get("info") or {}).get("name")) or username
                except Exception:  # noqa: BLE001
                    pass

        score, beatmap, beatmapset = sb_api.score_to_osu(raw, map_info, username)
        # TOTAL PP 那一格要靠 `score["user"]["id"]` 去查资料；get_player_scores 不给
        # userid，只能由调用方把已经查到的 pid 传进来补上。
        if uid:
            score.setdefault("user", {})["id"] = uid
        score["beatmap"] = beatmap
        score["beatmapset"] = beatmapset
        return score

    async def _sb_recent(self, username: str, include_fails: bool,
                         ruleset: str) -> tuple[str, object, str]:
        sb = self._sb()
        pid = await self._sb_player_id(username)
        rows = await self._call(
            sb.player_scores,
            player_id=pid, name=None if pid else username,
            mode=ruleset, scope="recent", limit=50,
            include_failed=bool(include_fails))
        if not rows:
            return "empty", None, ""
        # pid 显式传进去：get_player_scores 的成绩里没有 userid，不补的话
        # 卡片上的 TOTAL PP 永远是空的。
        return "ok", await self._sb_score_bundle(rows[0], username, uid=pid), ""

    async def _sb_score_card(self, event: AstrMessageEvent, reference: str):
        """`s <id> -sb`：按私服成绩 ID 渲染。

        私服的成绩 ID 和官服是两套独立编号，所以这里**只认数字** ——
        贴一个 osu.ppy.sh 的链接再带 -sb 是没意义的，会明确报出来。
        """
        digits = re.sub(r"\D", "", str(reference or ""))
        if not digits:
            yield event.plain_result(
                "SB 私服用的是私服自己的成绩 ID（纯数字）。\n"
                "用法：s <成绩ID> -sb\n例：s 5030104 -sb")
            return
        try:
            raw = await self._call(self._sb().score_info, digits)
        except Exception as exc:  # noqa: BLE001
            yield event.plain_result(self._explain(exc, "取 SB 私服成绩失败"))
            return
        if not raw:
            yield event.plain_result(f"SB 私服上没有找到成绩 {digits}。")
            return
        try:
            score = await self._sb_score_bundle(raw)
            async with aiohttp.ClientSession() as session:
                png = await self._render_score(event, score, session)
        except PhotoshopError as exc:
            yield event.plain_result(f"渲染失败：{exc}")
            return
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[scorecard] SB 渲染出错 {type(exc).__name__}: {exc}")
            yield event.plain_result(f"渲染失败：{type(exc).__name__}")
            return
        yield self._image_reply(event, png)

    def _needs_auth_reply(self, username: str, server_ok: bool, reason: str) -> str:
        """官服最近成绩查不了时的回复。

        这里**只给说明，不带链接** —— 链接由 `_send_oauth_link` 单独发一条，
        这样那条消息才能在 N 秒后自动撤回。以前链接是拼在这段文字里的，走的是
        普通回复路径，于是 `p` / `r` 触发的链接永远不会被撤回（只有 `bind` /
        `authorize` 那条路径会撤），用户看到的就是「链接一直挂在群里」。
        """
        head = f"{username} 绑好了，但官服的最近成绩还差一次授权。\n"
        if server_ok:
            return (
                head
                + "下面单独发一条授权链接给你，点开、点「Authorize」就行。\n"
                "\n"
                "授权只给「读取公开数据」的权限，插件拿不到你的密码，"
                "也改不了你的账号。\n"
                "\n"
                "不想授权也能用：直接贴成绩链接，或者 s <成绩ID>。")
        return (
            head
            + f"（现在发不出授权链接：{reason}）\n"
            "\n"
            "可以先这样用：\n"
            "· 把成绩链接直接发到群里：https://osu.ppy.sh/scores/<数字>\n"
            "· 或者用指令：s <成绩ID>\n"
            "\n"
            "想看自己的最近成绩：去 osu.ppy.sh 个人主页 → 最近表现 → "
            "点进那一条 → 复制地址栏链接发过来。\n"
            "（私服不受影响：加 -sb 就能直接查）")

    # ─────────────────────────── 官服 OAuth ───────────────────────────
    #
    # 官服的 `/users/{id}/{mode}/scores/recent` 对应用令牌一律 404，只有**用户
    # 令牌**能查。拿到用户令牌的唯一办法是让用户走一次授权码流程。
    #
    # 回调**不能**用 `context.register_web_api()`：AstrBot 给插件挂的每条路由
    # 都带 `Depends(require_plugin_scope)`，而它只认 dashboard 的 JWT cookie 或
    # API key（`dashboard/api/auth.py` 里没有公共路径白名单）。osu! 把用户浏览器
    # 302 过来时不带任何凭据，只会拿到 401，code 就永远到不了我们手里。
    #
    # 所以插件自己起一个小 HTTP 服务（见 oauth.py）。yumu-bot 也是这么做的。

    async def _ensure_oauth_server(self) -> tuple[bool, str]:
        """保证回调服务在跑。返回 (可用?, 不可用时的原因)。"""
        if not self.oauth_enabled:
            return False, "官服授权流程已在配置里关闭（oauth_enabled）"
        if self._oauth_server is not None and self._oauth_server.started:
            return True, ""
        if self._oauth_server is None:
            self._oauth_server = oauthmod.OAuthCallbackServer(
                self.oauth_callback_host, self.oauth_callback_port,
                self._on_oauth_callback)
        started = await self._oauth_server.start()
        if started:
            return True, ""
        return False, (self._oauth_server.error or "回调服务启动失败")

    async def _on_oauth_callback(self, code: str, state: str):
        """授权回调。返回给浏览器看的 (标题, 正文, 语气)。

        这里拿到的是 `code` 和 `state`，都不是凭据；换来的 token 只进 store，
        不进日志、不进页面、不进聊天。
        """
        item = self._pending.take(state)
        if not item:
            return ("链接已失效", "这个授权链接已经用过或者过期了。回到聊天里重新发一次 "
                                   "bind <你的名字>（或 authorize）拿一个新链接。", "warn")

        qq = str(item.get("qq") or "")
        umo = str(item.get("umo") or "")
        ruleset = str(item.get("ruleset") or self.ruleset)
        if not qq:
            return ("链接无效", "这条授权记录缺少账号信息，请重新发起。", "err")

        # 1. code -> token
        try:
            client = self._client()
            tokens = await self._call(client.exchange_code, code, self.oauth_redirect_uri)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[scorecard] OAuth 换取令牌失败 {type(exc).__name__}")
            return ("授权失败", "换取访问令牌时出错了。请回到聊天里重试；"
                                "如果一直失败，检查凭据文件和回调地址是否和 osu! 后台一致。", "err")

        # 2. 用刚拿到的用户令牌问 osu! 是谁 —— 这是权威答案，
        #    不依赖用户之前 bind 的名字（他可能还没绑定就先授权了）。
        user_id = tokens.get("user_id")
        username = ""
        try:
            me = await self._call(client.get, "/me", None, tokens.get("access_token"))
            if isinstance(me, dict):
                user_id = me.get("id") or user_id
                username = str(me.get("username") or "")
        except Exception as exc:  # noqa: BLE001
            # /me 失败不算致命：绑定记录里已经有名字了，令牌本身是好的。
            logger.info(f"[scorecard] OAuth /me 取不到（{type(exc).__name__}），退回已有绑定名")

        existing = self.store.username_for(qq, "osu")
        username = username or existing or f"id:{user_id}"
        tokens["user_id"] = user_id

        # 3. 落盘 + 报告
        if not self.store.binding_for(qq, "osu"):
            self.store.bind(qq, username, ruleset, "osu")
        if not self.store.set_oauth(qq, tokens, "osu"):
            return ("保存失败", "授权成功了，但插件没能把令牌写进绑定记录。请重新 bind 一次。", "err")

        logger.info(f"[scorecard] 官服授权完成 qq={qq} user={username}")

        if umo:
            try:
                await self.context.send_message(
                    umo, MessageChain().message(
                        f"官服授权完成！已绑定 {username}\n"
                        f"现在可以用 p / r 查最近成绩了。"))
            except Exception as exc:  # noqa: BLE001
                # 页面已经告诉用户成功了，主送失败只是少一条通知，不该报错给用户。
                logger.info(f"[scorecard] OAuth 完成通知发送失败 {type(exc).__name__}")

        return ("授权完成", f"已绑定 {username}。回到聊天里发 p 或 r 就能出成绩卡了。", "ok")

    def _oauth_link(self, qq: str, umo: str, ruleset: str) -> str:
        """生成授权链接，并把 state -> 谁在等 记下来。"""
        state = oauthmod.new_state()
        self._pending.put(state, qq, umo, ruleset)
        self._pending.prune()
        return self._client().authorize_url(self.oauth_redirect_uri, state)

    def _recall_delay(self) -> int:
        """授权链接那条消息发出后多少秒撤回；0 = 不撤回。

        文案必须和这个数保持一致。之前写死「链接 15 分钟内有效」而实际 30 秒
        就撤回，用户回头去点发现消息没了，会以为链接本身也失效了。
        """
        try:
            return max(0, int(self._cfg("oauth_recall_seconds", AUTO_RECALL_SECONDS) or 0))
        except (TypeError, ValueError):
            return AUTO_RECALL_SECONDS

    def _oauth_link_reply(self, qq: str, umo: str, ruleset: str,
                          server_ok: bool, reason: str) -> str:
        """发链接时要说清楚「点完才算绑定好」，否则用户会以为没生效。"""
        if not server_ok:
            return (f"官服授权链接暂时发不出来：{reason}\n"
                    f"可以先用 s <成绩ID> 或直接贴成绩链接（这两种不需要授权）。")
        try:
            url = self._oauth_link(qq, umo, ruleset)
        except Exception as exc:  # noqa: BLE001
            return f"生成授权链接失败：{self._explain(exc, '请检查 osu! 凭据配置')}"
        delay = self._recall_delay()
        tail = (f"（这条消息 {delay} 秒后自动撤回，请尽快点开）"
                if delay > 0 else
                f"（链接 {oauthmod.PENDING_TTL // 60} 分钟内有效）")
        return (
            "还差一步 —— 官服的最近成绩需要你授权一次：\n"
            f"{url}\n"
            "\n"
            "点开 → 点「Authorize」→ 看到「授权完成」就好了。\n"
            f"{tail}")

    async def _user_token(self, qq: str, ruleset: str) -> str | None:
        """这个 QQ 的官服用户令牌；过期就自动刷新。没授权过返回 None。

        osu! 每次刷新都会**换一个新的 refresh_token 并作废旧的**，所以刷新后
        必须立刻覆盖写回 —— 否则这次能用，下次就永久失效了。
        """
        rec = self.store.oauth_for(qq, "osu")
        if not rec:
            return None
        token = str(rec.get("access_token") or "")
        expires_at = float(rec.get("expires_at") or 0)
        if token and time.time() < expires_at:
            return token

        refresh = str(rec.get("refresh_token") or "")
        if not refresh:
            self.store.clear_oauth(qq, "osu")
            return None
        try:
            fresh = await self._call(self._client().refresh_user_token, refresh)
        except Exception as exc:  # noqa: BLE001
            # 刷新失败多半是 refresh_token 过期/被撤销了，清掉让用户重新授权，
            # 免得每次 p 都卡在这里。
            logger.info(f"[scorecard] 刷新官服令牌失败 {type(exc).__name__}，清除该用户授权")
            self.store.clear_oauth(qq, "osu")
            return None
        fresh["user_id"] = rec.get("user_id")
        self.store.set_oauth(qq, fresh, "osu")
        return str(fresh.get("access_token") or "") or None

    async def _send_oauth_link(self, event: AstrMessageEvent, qq: str,
                               ruleset: str) -> None:
        ok, reason = await self._ensure_oauth_server()
        text = self._oauth_link_reply(qq, event.unified_msg_origin, ruleset, ok, reason)
        if not await self._send_then_recall(event, text):
            yield event.plain_result(text)

    async def _send_then_recall(self, event: AstrMessageEvent, text: str,
                                delay: int | None = None) -> bool:
        """单独发一条授权链接，N 秒后自动撤回。

        为什么不用 `event.send()`：AstrBot 那个方法不返回 message_id，拿不到 id
        就没法撤回。所以这里直接调 OneBot 的 send_group_msg / send_private_msg，
        从回包里取 message_id，再起一个后台任务定时 delete_msg。

        单独发一条而不是拼在别的回复后面，是为了撤回时不会把
        「绑定成功」那条一起撤掉。发失败就返回 False，调用方回退成普通回复
        （那种情况下撤不了，会在日志里留一条记录）。

        返回 True 表示消息已经发出去了，调用方不要再 yield 一遍，否则会重复。
        """
        delay = self._recall_delay() if delay is None else delay
        bot = getattr(event, "bot", None)
        if bot is None or not hasattr(bot, "call_action"):
            logger.info("[scorecard] 平台没有 call_action，授权链接无法自动撤回（改走普通回复）")
            return False
        gid = event.get_group_id()
        try:
            if gid:
                res = await bot.call_action("send_group_msg",
                                            group_id=int(gid), message=text)
            else:
                res = await bot.call_action("send_private_msg",
                                            user_id=int(event.get_sender_id()),
                                            message=text)
        except Exception as exc:  # noqa: BLE001
            logger.info(f"[scorecard] 直接发授权链接失败（{type(exc).__name__}），"
                        f"改用普通回复（这条撤不了）")
            return False
        mid = res.get("message_id") if isinstance(res, dict) else None
        if mid is None:
            logger.info("[scorecard] 授权链接已发出，但回包里没有 message_id，撤不了")
            return True
        logger.info(f"[scorecard] 授权链接已发出 message_id={mid}，将在 {delay}s 后撤回")
        if delay > 0:
            # 必须留一份强引用：只写 asyncio.create_task(...) 的话，事件循环只持
            # 弱引用，任务可能在 sleep 到一半时被 GC 掉 —— 表现就是「有时候撤了、
            # 有时候没撤」。这就是之前 19:04 成功、19:11 没撤的原因之一。
            task = asyncio.create_task(self._recall_after(event, int(mid), gid, delay))
            self._recall_tasks.add(task)
            task.add_done_callback(self._recall_tasks.discard)
        return True

    async def _recall_after(self, event: AstrMessageEvent, message_id: int,
                            group_id, delay: int) -> None:
        """delay 秒后撤回那条消息。

        撤回失败（机器人没权限、消息太旧、平台不支持……）只写一条日志，
        绝不让它冒出来影响别的流程。
        """
        if delay <= 0:
            return
        try:
            await asyncio.sleep(delay)
            bot = getattr(event, "bot", None)
            if bot is None or not hasattr(bot, "call_action"):
                logger.info(f"[scorecard] 撤回 {message_id} 跳过：平台没有 call_action")
                return
            if group_id:
                await bot.call_action("delete_msg",
                                      message_id=message_id, group_id=int(group_id))
            else:
                await bot.call_action("delete_msg", message_id=message_id)
            logger.info(f"[scorecard] 授权链接消息 {message_id} 已按 {delay}s 自动撤回")
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.info(f"[scorecard] 撤回消息 {message_id} 失败（{type(exc).__name__}）：{exc}")

    # ─────────────────────────── sending ───────────────────────────

    def _image_reply(self, event: AstrMessageEvent, png: Path):
        if event.get_group_id():
            return event.chain_result([
                Comp.At(qq=event.get_sender_id()),
                Comp.Image.fromFileSystem(str(png)),
            ])
        return event.image_result(str(png))

    # ─────────────────────────── commands ───────────────────────────

    @staticmethod
    def _args(event: AstrMessageEvent) -> str:
        """The message with its leading command word removed."""
        text = (event.message_str or "").strip()
        return re.sub(
            r"^(?:" + "|".join(re.escape(n) for n in COMMAND_NAMES) + r")\b\s*",
            "", text, count=1, flags=re.I,
        ).strip()

    @classmethod
    def _split_server(cls, text: str) -> tuple[str, str]:
        """末尾的 -sb 后缀 -> (去掉后缀的文本, 服务器标识)。

        `"F6A8AF -sb"` -> `("F6A8AF", "sb")`
        `"-sb"`        -> `("", "sb")`
        `"F6A8AF"`     -> `("F6A8AF", "osu")`
        """
        raw = str(text or "")
        if SB_FLAG_RE.search(raw):
            return SB_FLAG_RE.sub("", raw).strip(), "sb"
        return raw.strip(), DEFAULT_SERVER

    def _args_server(self, event: AstrMessageEvent) -> tuple[str, str]:
        """命令参数 + 服务器标识，一次拿到。"""
        return self._split_server(self._args(event))

    def _need_binding(self, event: AstrMessageEvent,
                      server: str = DEFAULT_SERVER) -> str | None:
        return self.store.username_for(event.get_sender_id(), server)

    @filter.command("bind", alias={"绑定", "!bind", "！bind"})
    async def bind(self, event: AstrMessageEvent):
        """把 osu! 用户名和你的 QQ 绑定，之后 p / r 就能直接出图。

        用法：bind <osu!用户名> [-sb]
        例：bind Cookiezi        （官服）
        例：bind Cookiezi -sb    （SB 私服）
        """
        username, server = self._args_server(event)
        srv_label = SERVER_LABEL.get(server, server)
        if not username:
            yield event.plain_result(
                f"用法：bind <osu!用户名> [-sb]\n例：bind Cookiezi\n"
                f"例：bind Cookiezi -sb   （绑定 SB 私服）\n"
                f"绑定后可以用 mode 切换模式，用 help 看全部指令。")
            return
        try:
            profile = await self._profile(username, use_cache=False, server=server)
        except Exception as exc:  # noqa: BLE001
            yield event.plain_result(
                f"在{SERVER_LABEL.get(server, server)}上"
                + self._explain(exc, "找不到这个玩家"))
            return

        qq = str(event.get_sender_id())
        name = str(profile.get("username") or username)
        uid = profile.get("user_id")
        ruleset = self._ruleset_for(qq, server)
        self.store.bind(qq, name, ruleset, server)

        # 用户给的期望格式（另一个 bot 的输出），照抄排版：
        #   已将 (uid) name 绑定到 qq 上！
        #   当前绑定模式为：osu!mania
        #   您可以输入 mode (mode) 来切换绑定的模式，输入 help 获取简洁的帮助信息。
        # 分服之后多一行「服务器」，否则用户分不清这次绑的是官服还是私服。
        uid_text = f"({uid}) " if uid else ""
        tail = "".join(
            f"\n        · {SERVER_LABEL.get(s, s)}：{self.store.username_for(qq, s)}"
            for s in self.store.servers_for(qq))
        text = (
            f"已将 {uid_text}{name} 绑定到 {qq} 上！\n"
            f"服务器：{srv_label}\n"
            f"当前绑定模式为：{RULESET_LABEL.get(ruleset, ruleset)}\n"
            f"您可以输入 mode (mode) 来切换绑定的模式，输入 help 获取简洁的帮助信息。"
            + (f"\n你当前的绑定：{tail}" if tail else ""))

        yield event.plain_result(text)

        # 官服还差一次授权才能查最近成绩。绑定提示先单独发完，再单独发授权链接 ——
        # 分两条是为了 30 秒后只撤回链接那一条，不动「绑定成功」的提示。
        # （让用户自己去翻 help 找 authorize 是不现实的，他会觉得「绑了怎么还用不了」。）
        if server == DEFAULT_SERVER:
            if self.store.oauth_for(qq, "osu"):
                yield event.plain_result("官服已授权，p / r 可以直接用了。")
            elif self.oauth_ready:
                async for r in self._send_oauth_link(event, qq, ruleset):
                    yield r
            else:
                yield event.plain_result(
                    "官服凭据没配好，暂时发不出授权链接；"
                    "不过 s <成绩ID> 和贴成绩链接不受影响。")

    @filter.command("authorize", alias={"授权", "oauth", "!authorize", "！授权"})
    async def authorize(self, event: AstrMessageEvent):
        """重新拿一次官服授权链接（绑定过但没授权、或者链接过期了）。

        用法：authorize
        私服不需要授权，所以这条只对官服有意义。
        """
        qq = str(event.get_sender_id())
        username = self.store.username_for(qq, "osu")
        if not username:
            sb_name = self.store.username_for(qq, "sb")
            extra = (f"\n（你在 SB 私服绑的是 {sb_name}；私服不需要授权，"
                     f"直接用 p -sb 就行）" if sb_name else "")
            yield event.plain_result(
                f"你还没有绑定官服账号。先发：bind <官服名字>{extra}")
            return
        if not self.oauth_ready:
            yield event.plain_result(
                "官服授权流程不可用（凭据没配好，或者配置里关掉了 oauth_enabled）。\n"
                "s <成绩ID> 和直接贴成绩链接都不需要授权，可以先用。")
            return
        if self.store.oauth_for(qq, "osu"):
            yield event.plain_result(
                f"{username} 已经授权过了，p / r 可以直接用。\n"
                f"如果查不到成绩，可能是授权被撤销了 —— 再发一次 authorize 会重新授权。")
            return
        async for r in self._send_oauth_link(
                event, qq, self._ruleset_for(qq, DEFAULT_SERVER)):
            yield r

    @filter.command("mode", alias={"模式", "!mode", "！mode"})
    async def mode(self, event: AstrMessageEvent):
        """切换绑定的游戏模式（总 PP / 排名是分模式的，换模式要重新查一次）。

        用法：mode <osu|taiko|fruits|mania> [-sb]
        例：mode mania
        例：mode mania -sb    （只改 SB 私服那个绑定）
        """
        qq = str(event.get_sender_id())
        raw, server = self._args_server(event)
        want = raw.strip().lower()
        srv_label = SERVER_LABEL.get(server, server)
        if not want:
            cur = self._ruleset_for(qq, server)
            yield event.plain_result(
                f"{srv_label} 当前绑定模式为：{RULESET_LABEL.get(cur, cur)}\n"
                f"可切换：{' / '.join(RULESETS)}\n用法：mode <模式> [-sb]")
            return
        if want not in RULESETS:
            yield event.plain_result(
                f"不认识这个模式：{want}\n可选：{' / '.join(RULESETS)}")
            return

        bound = self.store.binding_for(qq, server)
        if not bound:
            yield event.plain_result(
                f"你在{srv_label}还没有绑定 osu! 用户名。\n"
                f"先用 bind <osu!用户名>{' -sb' if server == 'sb' else ''} 绑定。")
            return

        # 规则集是绑定记录的一部分，先落盘再查资料。
        self.store.set_ruleset(qq, want, server)
        # 换模式要重查，别吃旧缓存
        self.store.forget_player(bound["username"], want, server)
        try:
            profile = await self._profile(bound["username"], use_cache=False,
                                          server=server)
        except Exception as exc:  # noqa: BLE001
            yield event.plain_result(
                f"模式已切到 {RULESET_LABEL.get(want, want)}（{srv_label}），"
                f"但资料没查到：" + self._explain(exc, "查询失败"))
            return

        bits = [f"{srv_label} 模式已切换为：{RULESET_LABEL.get(want, want)}"]
        pp = profile.get("total_pp")
        rank = profile.get("global_rank")
        if pp is not None:
            bits.append(f"总 PP {round(float(pp)):,}")
        if rank:
            bits.append(f"全球 #{rank}")
        yield event.plain_result(" · ".join(bits))

    @filter.command("help", alias={"帮助", "!help", "！help"})
    async def help_cmd(self, event: AstrMessageEvent):
        """列出这个插件的全部指令。"""
        yield event.plain_result(HELP_TEXT)

    @filter.command("p")
    async def passed(self, event: AstrMessageEvent):
        """最近**通过**的一个成绩，渲染成成绩卡。

        用法：p [-sb]
        没绑定时先用 bind <osu!用户名> 绑定。加 -sb 查 SB 私服。
        """
        async for r in self._recent_card(event, include_fails=False,
                                         label="最近通过", cmd="p"):
            yield r

    @filter.command("r")
    async def played(self, event: AstrMessageEvent):
        """最近**游玩**的一个成绩（没通过也算），渲染成成绩卡。

        用法：r [-sb]
        没绑定时先用 bind <osu!用户名> 绑定。加 -sb 查 SB 私服。
        """
        async for r in self._recent_card(event, include_fails=True,
                                         label="最近游玩", cmd="r"):
            yield r

    async def _recent_card(self, event: AstrMessageEvent, include_fails: bool,
                           label: str, cmd: str = "p"):
        # 服务器从指令末尾的 -sb 解析；不带就是官服。
        _unused, server = self._args_server(event)
        srv_label = SERVER_LABEL.get(server, server)
        qq = str(event.get_sender_id())
        username = self._need_binding(event, server)

        if not username:
            # 最常见的困惑：用户绑的是私服，敲的却是不带 -sb 的 p —— 两个服的
            # 绑定是分开的，这时候泛泛地说「你还没绑定」会让人以为绑定失败了。
            if server == DEFAULT_SERVER:
                other = self.store.username_for(qq, "sb")
                if other:
                    yield event.plain_result(
                        f"你绑定的是【SB 私服】（{other}），而这条查的是官服。\n"
                        f"查私服请用：{cmd} -sb\n"
                        f"想在官服也能用，先发：bind <官服名字>（会给你一个授权链接）")
                    return
            yield event.plain_result(
                f"你在{srv_label}还没有绑定 osu! 账号。\n"
                f"先发：bind <osu!用户名>{' -sb' if server == 'sb' else ''}\n"
                f"例：bind Cookiezi" + (" -sb" if server == "sb" else ""))
            return

        rs = self._ruleset_for(qq, server)

        # 官服需要用户令牌；私服不需要，传 None 就行。
        user_token = None
        if server == DEFAULT_SERVER:
            try:
                user_token = await self._user_token(qq, rs)
            except Exception as exc:  # noqa: BLE001
                logger.info(f"[scorecard] 取官服令牌失败 {type(exc).__name__}")
                user_token = None

        try:
            status, payload, _detail = await self._recent_scores(
                username, include_fails, rs, server, user_token=user_token)
        except Exception as exc:  # noqa: BLE001
            logger.info(f"[scorecard] {server} 最近成绩查询失败 {type(exc).__name__}: {exc}")
            yield event.plain_result(self._explain(exc, "查询成绩失败"))
            return

        if status == "needs_user_token":
            # 说明走普通回复（留着），链接单独发一条并定时撤回。
            # 两条分开是刻意的：撤回只撤链接那条，说明不会被一起撤掉；
            # 而且不管是 bind 还是 p/r 触发的链接，都会经过同一个撤回路径。
            ok, reason = await self._ensure_oauth_server()
            yield event.plain_result(self._needs_auth_reply(username, ok, reason))
            if ok:
                async for r in self._send_oauth_link(event, qq, rs):
                    yield r
            return
        if status == "empty":
            yield event.plain_result(
                f"{username} 在{srv_label}没有找到{label}的成绩。\n"
                f"（当前模式：{RULESET_LABEL.get(rs, rs)}）")
            return
        try:
            async with aiohttp.ClientSession() as session:
                png = await self._render_score(event, payload, session)
        except PhotoshopError as exc:
            yield event.plain_result(f"渲染失败：{exc}")
            return
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[scorecard] 渲染出错 {type(exc).__name__}: {exc}")
            yield event.plain_result(f"渲染失败：{type(exc).__name__}")
            return
        yield self._image_reply(event, png)

    @filter.command("s")
    async def specific(self, event: AstrMessageEvent):
        """渲染指定的一个成绩。

        用法：s <成绩ID 或 成绩链接> [-sb]
        例：s 6645548845
        例：s https://osu.ppy.sh/scores/6645548845
        例：s 5030104 -sb     （SB 私服的成绩 ID 是另一套编号）
        """
        raw, server = self._args_server(event)
        match = SCORE_URL_RE.search(raw)
        target = match.group(0) if match else raw
        if not target:
            yield event.plain_result(
                "用法：s <成绩ID 或 成绩链接> [-sb]\n例：s 6645548845")
            return
        async for r in self._score_card(event, target, server=server):
            yield r

    async def _score_card(self, event: AstrMessageEvent, reference: str,
                          server: str = DEFAULT_SERVER):
        server = norm_server(server)
        if server == "sb":
            async for r in self._sb_score_card(event, reference):
                yield r
            return
        client = self._client()
        try:
            from osu_api import score_id  # noqa: PLC0415
            sid = score_id(reference)
        except Exception:  # noqa: BLE001
            yield event.plain_result(
                "认不出这个成绩 ID。\n支持纯数字，或 osu.ppy.sh/scores/<数字> 链接。")
            return
        try:
            score = await self._call(client.score, sid)
        except Exception as exc:  # noqa: BLE001
            yield event.plain_result(self._explain(exc, "取成绩失败"))
            return
        try:
            async with aiohttp.ClientSession() as session:
                png = await self._render_score(event, score, session)
        except PhotoshopError as exc:
            yield event.plain_result(f"渲染失败：{exc}")
            return
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[scorecard] 渲染出错 {type(exc).__name__}: {exc}")
            yield event.plain_result(f"渲染失败：{type(exc).__name__}")
            return
        yield self._image_reply(event, png)

    # ─────────────────────────── automatic links ───────────────────────────

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def auto_link(self, event: AstrMessageEvent):
        """A pasted score link renders that score — no command, no @.

        Kept from double-firing: an explicit `s <link>` is already handled by the
        command, so a message that starts with one of our command words is left
        alone. Every distinct link gets exactly one card.
        """
        if not self.auto_link:
            return
        text = event.message_str or ""
        head = text.strip().lstrip("/.．。").lower()
        if any(head.startswith(n) for n in COMMAND_NAMES):
            return
        found = SCORE_URL_RE.findall(text)
        if not found:
            return
        # Every distinct link in the message, in the order it appears; the same
        # link twice is still one card.
        for sid in dict.fromkeys(found):
            async for r in self._score_card(event, sid):
                yield r

    # ─────────────────────────── errors ───────────────────────────

    @staticmethod
    def _scrub(text: str) -> str:
        """Remove anything that looks like a credential before it can be echoed."""
        text = re.sub(r"(?i)bearer\s+\S+", "Bearer <redacted>", text)
        text = re.sub(r"(?i)access_token[\"'=:\s]+\S+", "access_token=<redacted>", text)
        return _SCRUB_RE.sub("<redacted>", text)

    @classmethod
    def _explain(cls, exc: Exception, fallback: str) -> str:
        """A user-facing line that never leaks a token or a credential."""
        text = cls._scrub(str(exc))
        if "osu_client_id" in text or "client_secret" in text:
            return ("还没有配置 osu! OAuth 凭据。\n"
                    "请在 AstrBot 网页 → 插件管理 → osu!mania 成绩卡 里填写 "
                    "osu_client_id 和 osu_client_secret，"
                    "或把 osu_credential_file 指向已有的凭据文件。")
        if "HTTP 401" in text or "HTTP 403" in text:
            return "osu! 拒绝了这次请求，多半是凭据不对或已失效。"
        if "HTTP 404" in text:
            return "osu! 没有这个成绩，或者它不是公开的。"
        if "HTTP 429" in text:
            return "osu! 限流了，等一会儿再试。"
        if "HTTP" in text:
            return f"{fallback}（{text}）"
        return f"{fallback}：{text[:180]}" if text else fallback

    @filter.on_astrbot_loaded()
    async def on_loaded(self):
        """AstrBot 起完了就把 OAuth 回调服务拉起来。

        不等第一次 bind 才启动 —— 那样用户点链接时才刚起服务，中间任何一步
        出问题都会被当成「链接坏了」。失败也只记一行日志：回调服务起不来
        不该拖垮整个插件（s / 贴链接 / 私服都不依赖它）。
        """
        if not self.oauth_enabled:
            logger.info("[scorecard] oauth_enabled 关闭，不启动回调服务")
            return
        try:
            ok, reason = await self._ensure_oauth_server()
            if ok:
                logger.info(f"[scorecard] 官服授权回调地址：{self.oauth_redirect_uri}")
            else:
                logger.warning(f"[scorecard] 官服授权回调服务未启动：{reason}")
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[scorecard] 启动回调服务异常：{type(exc).__name__}")

    async def terminate(self):
        """Called when the plugin is unloaded."""
        server = self._oauth_server
        if server is not None:
            try:
                await server.stop()
            except Exception:  # noqa: BLE001
                pass
        logger.info("[scorecard] 插件已卸载")
