"""AstrBot plugin: render an osu!mania replay to an MP4 and send it back to the chat.

The heavy lifting is done by a separate `mania-render` HTTP service (see the README for how
to run it). This plugin only drives that API: it posts a render request, polls the job,
downloads the finished MP4 and hands it to the platform adapter.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import re
import time
from pathlib import Path
from urllib.parse import unquote

import aiohttp

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star
import astrbot.api.message_components as Comp

PLUGIN_NAME = "astrbot_plugin_mania_render"

# Fallbacks used when the render service does not name its own default.
FALLBACK_SKIN = "boj 1-10K"

# What the bot ships with unless the user says otherwise.
# 1080p is the default: the skin pipeline mangles sprites at 720p, and 1080p is the
# size the layout numbers were validated against.
DEFAULT_FPS = 60
DEFAULT_RESOLUTION = "1080"
DEFAULT_WIDTH = 1920
DEFAULT_HEIGHT = 1080

# A pasted osu! score link. Covers the three shapes people actually paste:
#   https://osu.ppy.sh/scores/7546371044
#   https://osu.ppy.sh/community/scores/7546371044
#   osu.ppy.sh/#/scores/7546371044        (the old in-game/website hash form)
# The score id is what /api/v2/scores/<id> takes. Wrapped in a non-capturing prefix so
# only the digits land in the group.
SCORE_URL_RE = re.compile(
    r"osu\.ppy\.sh/(?:#/)?(?:community/)?scores/(\d{3,})",
    re.I,
)

# The same links, but matched whole — scheme and all — so a message can be reduced to "just
# the user's own words" before its options are parsed. `SCORE_URL_RE` deliberately starts at
# `osu.ppy.sh`, so substituting IT leaves `https://` behind, and that leftover would then be
# read as a bare skin name. Matching from the optional scheme removes the token entirely.
SCORE_LINK_STRIP_RE = re.compile(r"(?:https?://)?osu\.ppy\.sh/\S*", re.I)

# osu! API v2 — the ONLY way to fetch a replay from a server. The website path
# (osu.ppy.sh/scores/<id>/download) answers 401 with an HTML login page because it wants a
# browser session cookie, not an API token; /api/v2/... takes a Bearer token instead.
OSU_TOKEN_URL = "https://osu.ppy.sh/oauth/token"
OSU_SCORE_URL = "https://osu.ppy.sh/api/v2/scores/{sid}"
OSU_REPLAY_URL = "https://osu.ppy.sh/api/v2/scores/{sid}/download"
MANIA_RULESET_ID = 3
DEFAULT_SCROLL = 30.0
DEFAULT_BG_DIM = 0.60

# Video bitrate in kbps, sent to the service as `bitrate_kbps`. This is the one knob that
# decides the delivered file's size, and the size is what decides whether the upload
# channel carries it at all. Measured on this pipeline, an 86 s chart:
#   6000 kbps -> 74.8 MB. The video channel timed out mid-send, the fallback file channel
#                timed out too, and the chat got a 「发送失败」 for a video the user had
#                already received. Extrapolated to a 4-minute chart: ~200 MB, undeliverable.
#   2000 kbps -> ~24 MB, and a 4-minute chart stays near 60 MB, inside the 80 MB
#                `video_file_threshold_mb` at which the plugin switches to the file channel.
DEFAULT_BITRATE_KBPS = 2000

RESOLUTIONS = {
    "720": (1280, 720),
    "720p": (1280, 720),
    "1080": (1920, 1080),
    "1080p": (1920, 1080),
}

# ── "the render node is offline" ──────────────────────────────────────────────
# Rendering happens on one Windows machine that owns the CPU budget for it. This bot
# reaches that machine through a reverse SSH tunnel: 127.0.0.1:8760 on this host is an
# sshd forward listener, NOT a local process. There is deliberately NO server-side
# renderer to fall back on, so when the tunnel or that machine is down the render is
# REFUSED rather than quietly done somewhere slow.
#
# The raw failure is aiohttp's transport error --
#   Cannot connect to host 127.0.0.1:8760 ssl:default [Connect call failed ('127.0.0.1', 8760)]
# -- which reads like a bug in the bot and says nothing about the tunnel. Say what it means.
RENDER_NODE_OFFLINE = (
    "渲染服务不可达：本机渲染节点似乎离线（隧道未建立）。\n"
    "渲染固定在本机完成，服务端不会回退渲染——请等本机上线后重试。"
)

# Exceptions meaning "the connection failed", as opposed to "the service answered with an
# error". Built via getattr because aiohttp has moved these between releases.
_TRANSPORT_EXC = tuple(
    t for t in (
        getattr(aiohttp, "ClientConnectorError", None),
        getattr(aiohttp, "ServerDisconnectedError", None),
        getattr(aiohttp, "ServerTimeoutError", None),
        getattr(aiohttp, "ClientOSError", None),
        asyncio.TimeoutError,
        ConnectionError,
        TimeoutError,
    ) if isinstance(t, type)
)

_TRANSPORT_MARKERS = (
    "cannot connect to host",
    "connect call failed",
    "connection refused",
    "connection reset",
    "server disconnected",
    "network is unreachable",
    "no route to host",
    "name or service not known",
)

# How many consecutive failed job polls before the node counts as down rather than flaky.
# At the default 5 s poll interval that is ~30 s of continuous unreachability.
POLL_UNREACHABLE_LIMIT = 6

# ── "the send call timed out" — NOT the same thing as the node being offline ──────
# Rendering succeeded and the MP4 exists; what failed is handing it to the platform
# adapter. That failure is inherently AMBIGUOUS: the adapter's API call times out on the
# client side while the upload may already have completed server-side. Measured on this
# bot: a 74.8 MB / 86 s render made `event.send` raise `WebSocket API call timeout` on the
# video channel and then again on the file channel, and the user had ALREADY received the
# video. A flat 「发送失败」 is wrong twice over there — it contradicts what the user can
# see with their own eyes, and it suggests a retry that is not needed and would post the
# same video a second time.
_SEND_TIMEOUT_MARKERS = (
    "timeout", "timed out", "time out", "超时",
)


def _is_send_timeout(exc: BaseException) -> bool:
    """True when the send failed by TIMING OUT — i.e. delivery is UNKNOWN, not failed."""
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
        return True
    server_timeout = getattr(aiohttp, "ServerTimeoutError", None)
    if isinstance(server_timeout, type) and isinstance(exc, server_timeout):
        return True
    text = str(exc).lower()
    return any(m in text for m in _SEND_TIMEOUT_MARKERS)


def _send_timeout_text(headline: str, exc: BaseException, channel: str) -> str:
    """The chat text for an ambiguous send: state what is known, and what to do about it."""
    return (
        f"{headline}\n"
        f"发送调用超时（{channel}通道）：{exc}\n"
        "超时只说明协议端没有在时限内回话，不代表视频没发出去——它很可能已经发到群里了。\n"
        "请先往上翻确认收到没有；确实没有收到，再重发一次就行。"
    )


def _is_unreachable(exc: BaseException) -> bool:
    """True when the failure is the CONNECTION, not an HTTP/API answer from the service."""
    if isinstance(exc, _TRANSPORT_EXC):
        return True
    text = str(exc).lower()
    return any(mark in text for mark in _TRANSPORT_MARKERS)


def _plugin_data_dir(name: str) -> Path:
    """Persistent scratch space. Never write inside the plugin directory itself."""
    try:
        from astrbot.core.utils.astrbot_path import get_astrbot_data_path

        base = Path(get_astrbot_data_path())
    except Exception:  # older AstrBot without that helper
        base = Path.cwd() / "data"
    d = base / "plugin_data" / name
    d.mkdir(parents=True, exist_ok=True)
    return d


class ManiaRenderPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig | None = None):
        super().__init__(context)
        self.config = config or {}
        self.data_dir = _plugin_data_dir(getattr(self, "name", PLUGIN_NAME))
        # One render at a time. The service is expected to run on a small box where two
        # concurrent renders are what makes it run out of memory.
        self._render_lock = asyncio.Lock()
        # Keep detached render tasks referenced: an unreferenced task can be garbage
        # collected mid-flight, which would drop the video without a trace.
        self._background: set[asyncio.Task] = set()

    # ─────────────────────────── configuration ───────────────────────────

    def _cfg(self, key: str, default):
        value = self.config.get(key, default) if hasattr(self.config, "get") else default
        return default if value in (None, "") else value

    @property
    def server(self) -> str:
        return str(self._cfg("server", "http://127.0.0.1:8760")).rstrip("/")

    @property
    def timeout(self) -> int:
        return int(self._cfg("timeout_seconds", 1800))

    @property
    def poll_interval(self) -> float:
        return float(self._cfg("poll_interval_seconds", 5))

    @property
    def delivery(self) -> str:
        """`file` (same machine as the protocol adapter) or `url` (adapter fetches it)."""
        mode = str(self._cfg("video_delivery", "file")).lower()
        return "url" if mode == "url" else "file"

    @property
    def engine(self) -> str:
        """Renderer to ask for. Empty means "whatever the service defaults to".

        The service ships `webgl` (drive the page in a headless Chromium) and `python`
        (the Pillow renderer). They produce different pictures and cost very different
        amounts of time, so this is a deliberate user-facing switch, not a hidden one.
        """
        mode = str(self._cfg("engine", "")).lower().strip()
        return mode if mode in ("webgl", "python") else ""

    def _default_skin(self) -> str:
        return str(self._cfg("default_skin", "") or FALLBACK_SKIN)

    def _resolution(self, opts: dict) -> tuple[int, int]:
        """`-r` wins, else the configured default, else 1080p."""
        if opts.get("width") and opts.get("height"):
            return int(opts["width"]), int(opts["height"])
        key = str(self._cfg("default_resolution", DEFAULT_RESOLUTION)).lower()
        return RESOLUTIONS.get(key, (DEFAULT_WIDTH, DEFAULT_HEIGHT))

    @property
    def bitrate_kbps(self) -> int:
        """Video bitrate in kbps. 0 means "whatever the service defaults to".

        A size control as much as a quality one — see DEFAULT_BITRATE_KBPS. Sent to the
        service as `bitrate_kbps`, exactly like `width`/`height` are sent.
        """
        try:
            return max(0, int(self._cfg("video_bitrate_kbps", DEFAULT_BITRATE_KBPS)))
        except (TypeError, ValueError):
            return DEFAULT_BITRATE_KBPS

    # ─────────────────────────── HTTP helpers ───────────────────────────

    async def _api(self, session: aiohttp.ClientSession, method: str, path: str, **kw):
        url = f"{self.server}{path}"
        async with session.request(method, url, **kw) as resp:
            raw = await resp.read()
            if resp.status >= 400:
                detail = raw.decode("utf-8", "replace")[:300]
                try:
                    detail = json.loads(raw).get("error") or detail
                except Exception:
                    pass
                raise RuntimeError(f"渲染服务 {resp.status}: {detail}")
            ctype = resp.headers.get("Content-Type", "")
            return json.loads(raw) if "json" in ctype else raw

    async def _list_skins(self, session: aiohttp.ClientSession) -> tuple[list[str], str]:
        try:
            data = await self._api(session, "GET", "/api/skins")
        except Exception as exc:
            # An unreachable node is not a cosmetic problem: hand it to the caller so the
            # render is refused with RENDER_NODE_OFFLINE, instead of quietly falling back
            # to the default skin and then failing later with a raw transport error.
            if _is_unreachable(exc):
                raise
            logger.warning(f"[mania] 无法获取皮肤列表: {exc}")
            return [], self._default_skin()
        skins = [s["key"] for s in data.get("skins", [])]
        # Precedence, most explicit first:
        #   1. `default_skin` — a setting the USER wrote in the plugin config. It must win:
        #      the whole point of setting it is to override what the service suggests.
        #   2. the service's own `default` — what to use when the user expressed no opinion.
        #   3. the first skin the service listed.
        #   4. FALLBACK_SKIN.
        # The order used to be (2) then (1), which made `default_skin` dead code: the
        # service always reports a default, so a user who configured "R Skin" silently got
        # the service's "boj 1-10K" instead. `_default_skin()` cannot be used for step 1
        # because it substitutes FALLBACK_SKIN when unset, which would win over the
        # service's default and break the documented "leave it empty" behaviour.
        configured = str(self._cfg("default_skin", "") or "").strip()
        default = configured or data.get("default") or (skins[0] if skins else self._default_skin())
        return skins, default

    @staticmethod
    def _resolve_skin(requested: str | None, skins: list[str], default: str) -> str:
        """Accept an exact key, a case-insensitive match, or a unique substring."""
        if not requested:
            return default
        want = requested.strip()
        if want in skins:
            return want
        low = want.lower()
        for k in skins:
            if k.lower() == low:
                return k
        partial = [k for k in skins if low in k.lower()]
        if len(partial) == 1:
            return partial[0]
        if partial:
            raise ValueError(f"「{want}」匹配到多个皮肤：{'、'.join(partial)}")
        raise ValueError(f"没有叫「{want}」的皮肤，可用：{'、'.join(skins) or '（服务端未注册皮肤）'}")

    # ─────────────────────────── .osr attachment ───────────────────────────

    @staticmethod
    def _osr_components(event: AstrMessageEvent) -> list:
        """Every File component in the message whose name looks like a replay."""
        found = []
        for comp in getattr(event.message_obj, "message", []) or []:
            if isinstance(comp, Comp.File):
                name = getattr(comp, "name", "") or getattr(comp, "file", "") or ""
                if str(name).lower().endswith(".osr"):
                    found.append(comp)
        return found

    @staticmethod
    async def _read_file_target(session: aiohttp.ClientSession, candidate) -> bytes | None:
        """Read whatever a file handle points at: URL, local path, or `file://` URL."""
        if not candidate:
            return None
        cand = str(candidate).strip()
        if not cand:
            return None
        if cand.startswith(("http://", "https://")):
            try:
                async with session.get(cand) as resp:
                    if resp.status < 400:
                        return await resp.read()
            except Exception as exc:      # noqa: BLE001 - any transport failure just moves on
                logger.debug(f"[mania] 下载失败 {cand[:90]}: {exc}")
            return None
        raw = cand[7:] if cand.startswith("file://") else cand
        if re.match(r"^/[A-Za-z]:", raw):          # file:///D:/... -> D:/...
            raw = raw[1:]
        p = Path(unquote(raw))
        try:
            if p.is_file():
                return p.read_bytes()
        except OSError:
            return None
        return None

    @staticmethod
    def _file_url_attempts(event: AstrMessageEvent, data: dict) -> list[tuple[str, dict]]:
        """OneBot extensions that turn a file *id* into something downloadable.

        A file element commonly carries only `file` = the display NAME plus a `file_id`;
        neither is a URL or a path, so the adapter has to be asked for a url. Different
        protocol implementations answer different actions, so try the plausible ones.
        """
        file_id = str(data.get("file_id") or data.get("file") or "").strip()
        if not file_id:
            return []
        group_id = ""
        user_id = ""
        with contextlib.suppress(Exception):
            group_id = str(event.get_group_id() or "")
        with contextlib.suppress(Exception):
            user_id = str(event.get_sender_id() or "")

        attempts: list[tuple[str, dict]] = []
        if group_id:
            attempts.append(("get_group_file_url", {"group_id": int(group_id), "file_id": file_id}))
        if user_id:
            attempts.append(("get_private_file_url", {"user_id": int(user_id), "file_id": file_id}))
        # Go-CQHTTP/NapCat style: resolves either, and also accepts `file`.
        attempts.append(("get_file", {"file_id": file_id, "file": file_id}))
        return attempts

    async def _download_file_segment(self, session: aiohttp.ClientSession,
                                     event: AstrMessageEvent, data: dict) -> bytes | None:
        """Best-effort download of one OneBot `file` element."""
        # 1) anything already usable on its own
        for key in ("url", "file", "name", "path"):
            got = await self._read_file_target(session, data.get(key))
            if got:
                return got

        client = getattr(event, "bot", None)
        if client is None or not hasattr(client, "api"):
            return None

        # 2) ask the adapter for a url / local path
        failures = []
        for action, params in self._file_url_attempts(event, data):
            try:
                res = await client.api.call_action(action, **params)
            except Exception as exc:      # noqa: BLE001 - report and try the next action
                failures.append(f"{action}: {exc}")
                continue
            res = res or {}
            for key in ("url", "file", "download_url", "path"):
                got = await self._read_file_target(session, res.get(key))
                if got:
                    logger.info(f"[mania] 经 {action} 取到 .osr（{len(got)} 字节）")
                    return got
            failures.append(f"{action}: 返回 {str(res)[:120]}")
        logger.warning("[mania] 取文件失败，尝试过: " + " | ".join(failures))
        return None

    async def _fetch_osr(self, session: aiohttp.ClientSession,
                         event: AstrMessageEvent, comp) -> bytes | None:
        """A File component can carry a local path, a URL, or a bare file id."""
        data = {}
        # AstrBot's File component keeps the raw OneBot payload, which is where file_id lives.
        raw = getattr(comp, "raw", None)
        if isinstance(raw, dict):
            for key, value in (raw.get("data") or raw).items():
                data.setdefault(key, value)
        for key in ("url", "file", "name"):
            value = getattr(comp, key, None)
            if value:
                data.setdefault(key, value)
        return await self._download_file_segment(session, event, data)

    # ── replied-to message ──
    # `om` alone (without an ID) is meant to be used as a REPLY to a message that has the
    # .osr attached: the file lives in the quoted message, not in this one.

    @staticmethod
    def _reply_message_id(event: AstrMessageEvent) -> str | None:
        """The id of the message this one replies to, if the adapter exposed one."""
        raw = getattr(event.message_obj, "raw_message", None)
        segments = raw.get("message") if isinstance(raw, dict) else raw
        if isinstance(segments, list):
            for seg in segments:
                if not isinstance(seg, dict):
                    continue
                if seg.get("type") in ("reply", "quote"):
                    data = seg.get("data") or {}
                    rid = data.get("id") or data.get("message_id")
                    if rid:
                        return str(rid)
        for owner in (event.message_obj, event):
            for attr in ("reply_id", "reply_message_id", "quote_id"):
                value = getattr(owner, attr, None)
                if value:
                    return str(value)
        return None

    @staticmethod
    def _osr_segment(segments) -> dict | None:
        """The `file` segment most likely to be a replay, else the first file segment."""
        if not isinstance(segments, list):
            return None
        fallback = None
        for seg in segments:
            if not isinstance(seg, dict) or seg.get("type") != "file":
                continue
            data = seg.get("data") or {}
            blob = " ".join(str(data.get(k) or "") for k in ("file", "name", "file_id", "url"))
            if ".osr" in blob.lower():
                return seg
            fallback = fallback or seg
        return fallback

    async def _fetch_replied_osr(self, event: AstrMessageEvent) -> bytes | None:
        """Fetch the .osr out of the message the user replied to, if there is one."""
        rid = self._reply_message_id(event)
        if not rid:
            return None
        client = getattr(event, "bot", None)
        if client is None or not hasattr(client, "api"):
            logger.debug("[mania] 该平台适配器不支持 get_msg，无法读取被回复的消息")
            return None
        try:
            info = await client.api.call_action(
                "get_msg", message_id=int(rid) if rid.isdigit() else rid
            )
        except Exception as exc:
            logger.warning(f"[mania] get_msg({rid}) 失败: {exc}")
            return None
        segment = self._osr_segment((info or {}).get("message"))
        if not segment:
            logger.warning("[mania] 被回复的消息里没有 file 段。原始内容："
                           f"{str(info)[:400]}")
            return None
        data = segment.get("data") or {}
        timeout = aiohttp.ClientTimeout(total=120)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            got = await self._download_file_segment(session, event, data)
        if got:
            return got
        # Log the real payload so the next attempt can be targeted instead of guessed at.
        logger.warning(f"[mania] 被回复的 file 段拿不到内容。原始段：{json.dumps(data, ensure_ascii=False)[:400]}")
        return None


    @staticmethod
    def _raw_segments(event: AstrMessageEvent) -> list:
        """The adapter's own message segments, which keep fields `Comp.File` drops."""
        raw = getattr(event.message_obj, "raw_message", None)
        if isinstance(raw, dict):
            raw = raw.get("message")
        return raw if isinstance(raw, list) else []

    async def _collect_osr(self, event: AstrMessageEvent) -> bytes | None:
        """The replay to render: attached to this message, else to the one it replies to."""
        timeout = aiohttp.ClientTimeout(total=120)
        tried = False
        async with aiohttp.ClientSession(timeout=timeout) as session:
            # 1) AstrBot's parsed component — carries a path or url when the adapter has one.
            comps = self._osr_components(event)
            if comps:
                tried = True
                got = await self._fetch_osr(session, event, comps[0])
                if got:
                    return got

            # 2) The raw segments. `Comp.File` keeps only name/file_/url, so a protocol
            #    that reports a file by id (LLBot does) loses it by this point — but the
            #    raw payload still has `file_id`, which is what the url actions need.
            for seg in self._raw_segments(event):
                if not isinstance(seg, dict) or seg.get("type") != "file":
                    continue
                data = seg.get("data") or {}
                blob = " ".join(str(data.get(k) or "") for k in ("file", "name", "file_id", "url"))
                if ".osr" not in blob.lower():
                    continue
                tried = True
                got = await self._download_file_segment(session, event, data)
                if got:
                    return got
                logger.warning("[mania] 直接发送的 file 段拿不到内容。原始段："
                               f"{json.dumps(data, ensure_ascii=False)[:400]}")

        if tried:
            # The message DID carry a replay — say so rather than falling back to the
            # usage text, which reads as "you did not send anything".
            raise RuntimeError("收到了 .osr 文件，但读不出内容（具体原因见 AstrBot 日志）")
        return await self._fetch_replied_osr(event)

    # ─────────────────────────── the render itself ───────────────────────────

    async def _render(self, event: AstrMessageEvent, opts: dict,
                      osr_bytes: bytes | None) -> tuple[bool, str]:
        """Drive one render job and SEND the video.

        Returns `(sent, text)`. On success the caption travelled with the video, so the
        caller must NOT send `text` again in the chat path — `text` is only for the tool
        result. On failure nothing was sent and `text` is the error to show.
        """
        async with self._render_lock:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                try:
                    skins, default_skin = await self._list_skins(session)
                except Exception as exc:
                    if _is_unreachable(exc):
                        logger.error(f"[mania] 渲染节点不可达（{self.server}）: {exc}")
                        return False, RENDER_NODE_OFFLINE
                    raise
                try:
                    skin = self._resolve_skin(opts.get("skin"), skins, default_skin)
                except ValueError as exc:
                    return False, str(exc)

                form = aiohttp.FormData()
                if opts.get("bid"):
                    form.add_field("bid", str(opts["bid"]))
                width, height = self._resolution(opts)
                form.add_field("skin", skin)
                form.add_field("scroll", str(opts.get("scroll", DEFAULT_SCROLL)))
                form.add_field("fps", str(opts.get("fps", DEFAULT_FPS)))
                form.add_field("width", str(width))
                form.add_field("height", str(height))
                # Only when non-zero: 0 means "use the service's own default", and sending
                # an explicit 0 would have to be special-cased on the other side.
                if self.bitrate_kbps:
                    form.add_field("bitrate_kbps", str(self.bitrate_kbps))
                form.add_field("bg_dim", str(opts.get("bg_dim", DEFAULT_BG_DIM)))
                if self.engine:
                    form.add_field("engine", self.engine)
                if opts.get("range"):
                    form.add_field("range", str(opts["range"]))
                if osr_bytes:
                    form.add_field("osr", osr_bytes, filename="replay.osr",
                                   content_type="application/octet-stream")

                try:
                    job = await self._api(session, "POST", "/api/render", data=form)
                except Exception as exc:
                    if _is_unreachable(exc):
                        logger.error(f"[mania] 渲染节点不可达（{self.server}）: {exc}")
                        return False, RENDER_NODE_OFFLINE
                    return False, f"提交渲染任务失败：{exc}"
                job_id = job.get("id") or (job.get("job") or {}).get("id")
                if not job_id:
                    return False, f"渲染服务没有返回任务号：{job}"

                state, err = await self._poll(session, job_id)
                if err:
                    return False, err

                video = await self._download(session, job_id)
                if isinstance(video, str):        # error text
                    return False, video
                path, size_mb = video

                headline = (f"渲染完成 · {skin} · {state.get('width')}x{state.get('height')}"
                            f" · {size_mb:.1f}MB")
                threshold = float(self._cfg("video_file_threshold_mb", 80) or 80)
                as_file = size_mb >= threshold
                name = path.name if path else f"{job_id}.mp4"

                def _video():
                    if self.delivery == "url":
                        # For an adapter that does not share the filesystem with this bot.
                        return Comp.Video.fromURL(f"{self.server}/api/download/{job_id}")
                    return Comp.Video.fromFileSystem(path=str(path))

                def _file():
                    # A FILE message and a VIDEO message travel different upload channels with
                    # different ceilings. Measured: a 174 MB / 4:11 render died inside NapCat's
                    # highway upload at offset 89,128,960 (85 MB) with code 102902 — the video
                    # channel simply will not carry a full-length 1080p chart.
                    if self.delivery == "url":
                        return Comp.File(name=name, url=f"{self.server}/api/download/{job_id}")
                    return Comp.File(name=name, file=str(path))

                async def _try(chain):
                    """Send once. Returns None on success, else the exception."""
                    try:
                        await event.send(chain)
                        return None
                    except Exception as exc:      # noqa: BLE001 - classified below
                        return exc

                # Fresh components per attempt: a Comp that already travelled may not be
                # reusable, and the retry paths below build a second chain.
                def _primary():
                    return _file() if as_file else _video()

                channel = "文件" if as_file else "视频"
                exc = await _try(event.chain_result([_primary()]))
                if exc is None:
                    logger.info(f"[mania] 已发送: {headline}"
                                + ("（以文件形式）" if as_file else ""))
                    return True, headline

                # ── a TIMEOUT is not a failure ─────────────────────────────────────
                # Stop here. Retrying is the wrong move precisely because the outcome is
                # unknown: if the upload did land, the retry posts the same render twice.
                # Say what is actually known instead of asserting a failure.
                if _is_send_timeout(exc):
                    logger.error(f"[mania] 发送调用超时（{channel}通道，投递结果未知）: {exc}")
                    return False, _send_timeout_text(headline, exc, channel)

                # ── a DEFINITE failure means nothing was delivered ─────────────────
                # So exactly ONE bounded retry is safe. Never more than one: a large upload
                # is minutes of wall clock, not a cheap call to repeat.
                logger.warning(f"[mania] {channel}通道发送失败（{exc}），重试一次")
                exc = await _try(event.chain_result([_primary()]))
                if exc is None:
                    logger.info(f"[mania] 已发送（重试成功）: {headline}")
                    return True, headline
                if _is_send_timeout(exc):
                    logger.error(f"[mania] 重试超时（{channel}通道，投递结果未知）: {exc}")
                    return False, _send_timeout_text(headline, exc, channel)

                if not as_file:
                    # A different channel, so this cannot duplicate: the video channel
                    # answered with a definite error, which means the video is not in the
                    # chat. This fallback predates the timeout handling and is kept.
                    logger.warning(f"[mania] 视频通道失败（{exc}），改以文件发送")
                    exc2 = await _try(event.chain_result([_file()]))
                    if exc2 is None:
                        logger.info(f"[mania] 已发送（文件形式，视频通道失败后回退）: {headline}")
                        return True, headline
                    if _is_send_timeout(exc2):
                        logger.error(f"[mania] 文件通道回退超时（投递结果未知）: {exc2}")
                        return False, _send_timeout_text(headline, exc2, "文件")
                    logger.error(f"[mania] 文件通道也失败: {exc2}")
                    return False, f"{headline}\n但发送失败：视频通道 {exc}；文件通道 {exc2}"
                logger.error(f"[mania] 以文件发送失败: {exc}")
                return False, f"{headline}\n但发送文件失败：{exc}"

    async def _poll(self, session: aiohttp.ClientSession, job_id: str):
        """Wait for the job. Returns `(state_dict, None)` or `(None, error_text)`.

        Progress is written to the AstrBot log only — the chat gets one "starting"
        line up front and the finished video, nothing in between.
        """
        started = time.monotonic()
        last_reported = -25
        # A render is long, so one failed poll proves nothing -- the tunnel can blip and
        # come back. But a node that is DOWN must not be waited on for the full timeout:
        # count consecutive transport failures and refuse once they are clearly not a blip.
        unreachable = 0
        while True:
            if time.monotonic() - started > self.timeout:
                return None, f"渲染超时（>{self.timeout}s），任务 {job_id} 可能还在服务端排队。"
            await asyncio.sleep(self.poll_interval)
            try:
                state = await self._api(session, "GET", f"/api/jobs/{job_id}")
                unreachable = 0
            except Exception as exc:      # transient — keep polling until the timeout
                if _is_unreachable(exc):
                    unreachable += 1
                    if unreachable >= POLL_UNREACHABLE_LIMIT:
                        logger.error(f"[mania] 渲染中途节点离线（{self.server}）: {exc}")
                        return None, RENDER_NODE_OFFLINE
                logger.warning(f"[mania] 查询任务失败({unreachable}): {exc}")
                continue
            status = state.get("state")
            if status == "error":
                return None, f"渲染失败：{state.get('error') or state.get('message') or '未知错误'}"
            if status == "done":
                return state, None
            pct = int(state.get("percent") or 0)
            if pct >= last_reported + 25:
                last_reported = pct
                logger.info(f"[mania] {job_id} {pct}% {state.get('message', '渲染中')}".rstrip())

    async def _download(self, session: aiohttp.ClientSession, job_id: str):
        """Save the MP4 under plugin_data. Returns (path, size_mb) or an error string."""
        try:
            raw = await self._api(session, "GET", f"/api/download/{job_id}")
        except Exception as exc:
            return f"渲染完成但下载失败：{exc}"
        if not isinstance(raw, (bytes, bytearray)) or not raw:
            return "渲染完成但下载到空文件。"
        out = self.data_dir / f"{job_id}.mp4"
        out.write_bytes(raw)
        self._prune_outputs()
        return out, len(raw) / 1048576

    def _prune_outputs(self, keep: int = 5) -> None:
        """Renders are large; keep only the newest few."""
        try:
            files = sorted(self.data_dir.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
            for stale in files[keep:]:
                stale.unlink(missing_ok=True)
        except Exception as exc:
            logger.debug(f"[mania] 清理旧视频失败: {exc}")

    # ─────────────────────────── option parsing ───────────────────────────

    # Chinese words users type without a dash: `2467450 暗度 30`
    BARE_ALIASES = {
        "皮肤": "skin", "速度": "scroll", "滚动": "scroll", "暗度": "bg_dim",
        "背景": "bg_dim", "分辨率": "res", "帧率": "fps", "起": "from", "止": "to",
    }

    # Every spelling of every option. Shared by the `om` command and the automatic
    # score-link path so the two accept exactly the same grammar and cannot drift apart.
    OPTION_ALIASES = {
        "s": "skin", "skin": "skin", "皮肤": "skin",
        "v": "scroll", "scroll": "scroll", "速度": "scroll", "滚动": "scroll",
        "d": "bg_dim", "dim": "bg_dim", "bgdim": "bg_dim", "暗度": "bg_dim", "背景": "bg_dim",
        "r": "res", "res": "res", "分辨率": "res",
        "f": "fps", "fps": "fps", "帧率": "fps",
        "from": "from", "to": "to", "起": "from", "止": "to",
    }

    @staticmethod
    def _parse_options(text: str, strict: bool = False) -> tuple[dict, str | None]:
        """`key=value` / `-k value` / bare-word options plus a 谱面 ID or skin name.

        `strict` is for the automatic score-link path. There the text is whatever the user
        happened to type around a pasted link — `小秋这个换boj那个皮肤渲染 <link>` — not a
        command line, so a free-standing word is prose and a free-standing number is not a
        beatmap id. Only flagged (`-s`, `--from`) and assigned (`skin=`) options count. `om`
        keeps `strict=False`: there the whole message IS the command, and a bare word really
        is a skin name.
        """
        opts: dict = {}
        error: str | None = None
        tokens = text.split()
        pending: str | None = None
        pending_flag = ""
        aliases = ManiaRenderPlugin.OPTION_ALIASES
        bare = ManiaRenderPlugin.BARE_ALIASES
        # A skin key may contain spaces ("R Skin"), so the skin value keeps absorbing
        # words until something that cannot be part of a name shows up.
        skin_parts: list[str] = []

        def stops_skin(tok: str) -> bool:
            if tok.isdigit():                                  # the beatmap id
                return True
            if tok.startswith("-") and len(tok) > 1:           # another flag
                return True
            if "=" in tok and not tok.startswith("-"):         # key=value
                return True
            return tok in bare                                 # 暗度 / 帧率 / …

        def flush_skin() -> None:
            if skin_parts:
                opts["skin"] = " ".join(skin_parts)
                skin_parts.clear()

        for tok in tokens:
            if pending == "skin":
                if not stops_skin(tok):
                    skin_parts.append(tok)
                    continue
                flush_skin()
                pending = None
                # fall through and handle `tok` on its own merits
            elif pending:
                opts[pending] = tok
                pending = None
                continue

            if "=" in tok and not tok.startswith("-"):
                k, _, v = tok.partition("=")
                key = aliases.get(k.lower())
                if key:
                    opts[key] = v
                continue
            if tok.startswith("-") and len(tok) > 1:
                key = aliases.get(tok.lstrip("-").lower())
                if key:
                    pending, pending_flag = key, tok
                continue
            if tok in bare:
                pending, pending_flag = bare[tok], tok
                continue
            if tok.isdigit() and "bid" not in opts and not strict:
                opts["bid"] = tok
            elif not strict:
                skin_parts.append(tok)                         # bare skin name
            # strict: a bare word or number is prose, not an option — natural chatter sits
            # next to a pasted link far more often than a bare skin name does.

        if pending == "skin":
            # a trailing `-s`/`皮肤` with no words after it stays pending -> error below
            if skin_parts:
                flush_skin()
                pending = None
        else:
            flush_skin()
        if pending:
            error = f"选项 {pending_flag} 后面少了值"
        return opts, error

    @staticmethod
    def _unknown_options(text: str) -> str | None:
        """Name the option-looking tokens the grammar does not know, or return None.

        `om` drops an unrecognised flag on the floor, which is survivable when the user is
        watching their own command fail to change anything. On the automatic link path they
        would get a render with the default and no hint that their parameter was discarded,
        so the token has to be said out loud.
        """
        known = ManiaRenderPlugin.OPTION_ALIASES
        bad: list[str] = []
        for tok in text.split():
            if tok.startswith("-") and len(tok) > 1:
                if tok.lstrip("-").lower() not in known:
                    bad.append(tok)
            elif "=" in tok and tok.partition("=")[0].strip().lower() not in known:
                bad.append(tok)
        if not bad:
            return None
        return (
            "认不出这些选项：" + "、".join(dict.fromkeys(bad))
            + "\n可用的选项：-s 皮肤 / -v 滚动速度 / -d 背景暗度 / "
              "-r 720|1080 / -f 帧率 / --from 秒 --to 秒"
        )

    @staticmethod
    def _normalise(opts: dict) -> tuple[dict, str | None]:
        """Turn the raw tokens into the API's units; returns (opts, error)."""
        out: dict = {}
        if opts.get("bid"):
            bid = re.sub(r"\D", "", str(opts["bid"]))
            if not bid:
                return {}, "谱面 ID 必须是数字"
            out["bid"] = bid
        if opts.get("skin"):
            out["skin"] = str(opts["skin"])
        if opts.get("scroll"):
            try:
                v = float(opts["scroll"])
            except ValueError:
                return {}, "滚动速度要是数字"
            if not 1 <= v <= 40:
                return {}, "滚动速度要在 1–40 之间"
            out["scroll"] = v
        if opts.get("bg_dim"):
            raw = str(opts["bg_dim"]).rstrip("%")
            try:
                v = float(raw)
            except ValueError:
                return {}, "背景暗度要是数字"
            if v > 1:                     # accept both 0.3 and 30(%)
                v = v / 100.0
            if not 0 <= v <= 1:
                return {}, "背景暗度要在 0–100% 之间"
            out["bg_dim"] = v
        if opts.get("fps"):
            try:
                v = int(opts["fps"])
            except ValueError:
                return {}, "帧率要是整数"
            if not 1 <= v <= 120:
                return {}, "帧率要在 1–120 之间"
            out["fps"] = v
        if opts.get("res"):
            key = str(opts["res"]).lower()
            if key not in RESOLUTIONS:
                return {}, "分辨率只支持 720 / 1080"
            out["width"], out["height"] = RESOLUTIONS[key]
        if opts.get("from") or opts.get("to"):
            try:
                start = float(opts.get("from") or 0)
                end = float(opts.get("to") or 0)
            except ValueError:
                return {}, "--from / --to 要是秒数"
            if end <= start:
                return {}, "--to 要大于 --from"
            if end - start > 120:
                return {}, "单次片段最长 120 秒"
            out["range"] = f"{start:g}-{end:g}"
        return out, None

    # ───────────────────── score link → replay (automatic) ─────────────────────

    @property
    async def _osu_token(self, session: aiohttp.ClientSession) -> str | None:
        """A client_credentials token, cached in memory until just before it expires.

        Measured against the live API: this token IS enough for
        `/api/v2/scores/<id>/download` (200, `application/x-osu-replay`) — no user-level
        OAuth is needed to fetch a replay. It is NOT enough for
        `/api/v2/beatmapsets/<id>/download` (403 `Invalid scope(s) provided.`), which is why
        the official .osz fallback still would need one; nothing here uses that endpoint.
        """
        cid = str(self._cfg("osu_client_id", "")).strip()
        secret = str(self._cfg("osu_client_secret", "")).strip()
        if not (cid and secret):
            return None
        now = time.time()
        cached = getattr(self, "_osu_tok", None)
        if cached and now < getattr(self, "_osu_tok_exp", 0.0) - 60:
            return cached
        async with session.post(OSU_TOKEN_URL, data={
            "client_id": cid, "client_secret": secret,
            "grant_type": "client_credentials", "scope": "public",
        }) as resp:
            if resp.status != 200:
                body = (await resp.text())[:200]
                logger.warning(f"[mania] osu! token 获取失败 HTTP {resp.status}: {body}")
                return None
            data = await resp.json()
        tok = str(data.get("access_token") or "")
        if not tok:
            return None
        self._osu_tok = tok
        self._osu_tok_exp = now + int(data.get("expires_in") or 3600)
        return tok

    async def _score_replay(self, score_id: str) -> tuple[str, object]:
        """Classify one score link: ('ok', (osr, bid)) | ('skip', None) | ('fail', reason).

        'skip' is reserved for the ONE case that must stay silent: the score is not mania.
        A standard/taiko/catch link is an ordinary thing to paste in a chat, so answering
        it would be noise.

        Everything else is 'fail' and gets reported, because the user cannot see those
        conditions and silence would read as the bot ignoring them: no public replay, a
        rejected request, a transport error, or missing credentials.
        """
        if not (str(self._cfg("osu_client_id", "")).strip()
                and str(self._cfg("osu_client_secret", "")).strip()):
            return "fail", "未配置 osu! OAuth（请在插件配置里填 osu_client_id / osu_client_secret）"
        timeout = aiohttp.ClientTimeout(total=120)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                tok = await self._osu_token(session)
                if not tok:
                    return "fail", "osu! API 取 token 失败（密钥是否正确？详见 AstrBot 日志）"
                hdr = {"Authorization": f"Bearer {tok}", "x-api-version": "20220705"}
                async with session.get(OSU_SCORE_URL.format(sid=score_id), headers=hdr) as resp:
                    if resp.status != 200:
                        return "fail", f"取成绩信息失败（HTTP {resp.status}），成绩 ID 是否正确？"
                    meta = await resp.json()
                ruleset = int(meta.get("ruleset_id") or 0)
                if ruleset != MANIA_RULESET_ID:
                    logger.info(f"[mania] 成绩 {score_id} 不是 mania（ruleset_id={ruleset}），静默跳过")
                    return "skip", None
                if not meta.get("replay"):
                    return "fail", "这条成绩没有公开回放（可能未过审或已被隐藏）"
                bid = str((meta.get("beatmap") or {}).get("id") or "")
                async with session.get(OSU_REPLAY_URL.format(sid=score_id), headers=hdr) as resp:
                    if resp.status != 200:
                        return "fail", f"回放下载失败（HTTP {resp.status}）"
                    raw = await resp.read()
        except Exception as exc:                       # noqa: BLE001
            logger.warning(f"[mania] 取成绩回放 {score_id} 出错: {exc!r}")
            return "fail", f"下载回放出错：{type(exc).__name__}"
        if len(raw) < 100:
            return "fail", f"下载到的回放只有 {len(raw)} 字节，不是有效文件"
        return "ok", (raw, bid)

    # 自动检测成绩链接并渲染回放已经**移除**。
    #
    # 原因：和 astrbot_plugin_osu_scorecard 冲突 —— 两个插件都会抓消息里的
    # https://osu.ppy.sh/scores/<id>，同一条链接会被渲染两次（一次视频、一次成绩卡）。
    #
    # 现在成绩链接归 astrbot_plugin_osu_scorecard 负责；本插件只保留显式指令
    # `om <谱面ID>` / `om` 回复 .osr，以及 LLM 工具里那条接受成绩 ID 的路径。
    # 想恢复的话：git 历史或 main.py.bak_before_autoscore_removal。

    # ─────────────────────────── commands ───────────────────────────

    # The command is `om`: `om <谱面ID>` or `om` as a reply to a message holding an .osr.
    COMMAND_NAMES = ("om", "mania", "渲染", "osu")

    @filter.command("om", alias={"mania", "osumania", "渲染"})
    async def om(self, event: AstrMessageEvent):
        """把 osu!mania 谱面或回放渲染成视频。

        用法一：om <谱面ID>      例：om 2467450
        用法二：回复一条带 .osr 的消息，发 om
        可加选项：-s 皮肤 -v 滚动速度 -d 背景暗度 -r 720|1080 -f 帧率 --from 秒 --to 秒
        例：om 2467450 -s R Skin -d 30 -v 25
        """
        text = (event.message_str or "").strip()
        text = re.sub(
            r"^(?:" + "|".join(re.escape(n) for n in self.COMMAND_NAMES) + r")\s*",
            "", text, count=1, flags=re.I,
        )
        opts, err = self._parse_options(text)
        if err:
            yield event.plain_result(err)
            return
        opts, err = self._normalise(opts)
        if err:
            yield event.plain_result(err)
            return

        try:
            osr_bytes = await self._collect_osr(event)
        except Exception as exc:
            yield event.plain_result(f"读取 .osr 失败：{exc}")
            return

        if not opts.get("bid") and not osr_bytes:
            yield event.plain_result(
                "用法：\n"
                "· om <谱面ID> —— 例：om 2467450\n"
                "· 回复一条带 .osr 的消息，再发 om\n"
                "选项：-s 皮肤 / -v 滚动速度 / -d 背景暗度 / -r 720|1080 / -f 帧率 / --from --to"
            )
            return

        note = "回放" if osr_bytes else "自动游玩"
        if osr_bytes and opts.get("bid"):
            note += "（MD5 匹配不上时用你给的 ID）"
        yield event.plain_result(f"开始渲染（{note}）\n渲染视频需要几分钟，请稍等")

        sent, text = await self._render(event, opts, osr_bytes)
        if not sent:                    # on success the caption went with the video
            yield event.plain_result(text)

    @filter.command("om皮肤", alias={"mania皮肤", "皮肤列表", "skinlist"})
    async def om_skins(self, event: AstrMessageEvent):
        """列出渲染服务上可用的皮肤，以及默认皮肤。"""
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
                skins, default = await self._list_skins(session)
        except Exception as exc:
            if _is_unreachable(exc):
                logger.error(f"[mania] 皮肤列表不可达（{self.server}）: {exc}")
                yield event.plain_result(RENDER_NODE_OFFLINE)
                return
            raise
        if not skins:
            yield event.plain_result(f"拿不到皮肤列表，检查渲染服务是否在 {self.server} 上运行。")
            return
        lines = [f"· {k}{'（默认）' if k == default else ''}" for k in skins]
        yield event.plain_result("可用皮肤：\n" + "\n".join(lines))

    @filter.command("om参数", alias={"mania参数", "渲染参数"})
    async def om_defaults(self, event: AstrMessageEvent):
        """显示当前的默认渲染参数。"""
        width, height = self._resolution({})
        yield event.plain_result(
            f"渲染服务：{self.server}\n"
            f"渲染引擎：{self.engine or '（服务端默认）'}\n"
            f"默认皮肤：{self._default_skin()}\n"
            f"默认分辨率：{width}x{height}   帧率：{DEFAULT_FPS}\n"
            f"默认滚动速度：{DEFAULT_SCROLL}   背景暗度：{int(DEFAULT_BG_DIM * 100)}%\n"
            f"单任务超时：{self.timeout}s   视频投递方式：{self.delivery}"
        )

    async def terminate(self):
        """插件停用/卸载时调用。"""
        logger.info("[mania] 插件已停用")

    # ───────────────────── LLM tool（已移除） ─────────────────────
    #
    # `render_mania_video` 已经**移除**。
    #
    # 原因：它能接受 osu! 成绩链接/ID，和 astrbot_plugin_osu_scorecard 争同一个触发场景 ——
    # 用户贴着链接说「渲染这个」时，模型调它会出视频、链接自动检测那路出成绩卡，
    # 同一次操作出两个结果。现在成绩链接统一归 astrbot_plugin_osu_scorecard。
    #
    # 本插件保留的能力：显式指令 `om <谱面ID>` / `om` 回复 .osr。
    #
    # 想恢复：main.py.bak_before_llmtool_removal，或按上面的名字重建工具 ——
    # 它依赖的 _score_replay() / _osu_token() / OSU_* 常量**全部原样保留**，
    # 重建时不用重写网络层。
