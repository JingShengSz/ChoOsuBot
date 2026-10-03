"""OAuth authorization_code flow for the official osu! server.

Why this file exists
--------------------
`/users/{id}/{mode}/scores/recent` answers **HTTP 404** to an application token
(`client_credentials`) no matter how the request is shaped. osu! only serves it
to a token that belongs to a *user*, and the only way to get one is to send the
user through the authorization_code flow. That is what `p` / `r` need.

Why the callback is not an AstrBot web API
------------------------------------------
`context.register_web_api()` looks like the natural home for a callback, but
every route it registers sits behind dashboard authentication:

    @router.get("/plugins/extensions/{plugin_path:path}")
    async def ...(..., auth: AuthContext = Depends(require_plugin_scope)):

`require_dashboard_user` accepts only a dashboard JWT cookie or an API key —
there is no public-path allowlist anywhere in `dashboard/api/auth.py`. So a
browser arriving from a 302 off osu.ppy.sh (no cookie, no key) would get a 401
and the code would never reach us.

yumu-bot solves it the same way this file does: it runs its own HTTP server
(`OsuConfig.callbackUrl` / `callbackPath = "/bind"`) rather than hosting the
callback inside the bot framework.

So: a small aiohttp server, bound to a configurable host/port, with one route.
It is deliberately tiny — it accepts a `code`, hands it to a callback function,
and returns a page telling the user what happened.

Reachability, stated plainly
----------------------------
* Browser on the **same machine** as the bot (e.g. the webchat test setup):
  `http://127.0.0.1:<port>/oauth/callback` works.
* A **QQ user on their own machine**: their browser has to reach this server,
  so it needs a public address — port forwarding, a reverse proxy, or a tunnel.
  `127.0.0.1` will never work for them, and neither will any other private IP.

The address that osu! redirects to must ALSO be registered as the app's
Callback URL at https://osu.ppy.sh/home/account/edit → OAuth. osu! compares it
literally, so the two must match character for character.
"""
from __future__ import annotations

import asyncio
import html
import secrets
import time
from pathlib import Path
from typing import Awaitable, Callable

from astrbot.api import logger

#: How long a pending authorization stays usable. The user has to click the
#: link, consent on osu.ppy.sh and be redirected back; 15 minutes is generous
#: without leaving stale state around.
PENDING_TTL = 15 * 60

#: The path the callback server serves. Changing this means changing the
#: registered Callback URL at osu! too — the two must match exactly.
CALLBACK_PATH = "/oauth/callback"


def new_state() -> str:
    """An unguessable `state`.

    Deliberately NOT the QQ number itself: `state` is visible in the URL, in
    browser history and in osu!'s logs. A random token that maps to a pending
    record leaks nothing and cannot be forged into someone else's binding.
    """
    return secrets.token_urlsafe(24)


class PendingAuth:
    """`state -> {qq, umo, ruleset, created_at}` with a TTL.

    Persisted, because the flow spans a browser round trip and the plugin may
    be reloaded in between. A pending record holds no secrets — only who is
    waiting and where to answer.
    """

    def __init__(self, path: Path, ttl: int = PENDING_TTL):
        self.path = Path(path)
        self.ttl = max(60, int(ttl))
        self._items: dict[str, dict] = self._load()
        self.prune()

    def _load(self) -> dict:
        try:
            import json

            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save(self) -> None:
        import json

        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        try:
            tmp.write_text(json.dumps(self._items, ensure_ascii=False, indent=1),
                           encoding="utf-8")
            tmp.replace(self.path)
        except OSError:
            # Losing the pending list only means the user re-runs `bind`; it must
            # never take the command down.
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass

    def put(self, state: str, qq: str, umo: str, ruleset: str) -> None:
        self._items[str(state)] = {
            "qq": str(qq),
            "umo": str(umo),
            "ruleset": str(ruleset),
            "created_at": time.time(),
        }
        self._save()

    def peek(self, state: str) -> dict | None:
        item = self._items.get(str(state))
        if not item:
            return None
        if time.time() - float(item.get("created_at", 0)) > self.ttl:
            self.take(state)
            return None
        return item

    def take(self, state: str) -> dict | None:
        """Read and remove — a code must not be replayable."""
        item = self._items.pop(str(state), None)
        if item is not None:
            self._save()
        return item

    def prune(self) -> int:
        now = time.time()
        stale = [k for k, v in self._items.items()
                 if now - float(v.get("created_at", 0)) > self.ttl]
        for k in stale:
            self._items.pop(k, None)
        if stale:
            self._save()
        return len(stale)

    def count(self) -> int:
        return len(self._items)


def _page(title: str, body: str, tone: str = "ok") -> str:
    """A minimal standalone page. No external assets — this is served from a
    machine that may have no internet access at all."""
    colour = {"ok": "#4caf50", "warn": "#ffb300", "err": "#e8503f"}.get(tone, "#666")
    return (
        "<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{html.escape(title)}</title><style>"
        "body{margin:0;background:#0b0d11;color:#eaedf6;font:16px/1.7 "
        "'Segoe UI','Microsoft YaHei',sans-serif;display:flex;align-items:center;"
        "justify-content:center;min-height:100vh;padding:24px}"
        ".card{max-width:520px;background:#12161f;border:1px solid #232a38;"
        "border-radius:14px;padding:28px 30px}"
        f"h1{{margin:0 0 12px;font-size:20px;color:{colour}}}"
        "p{margin:8px 0;color:#c8d0e0}code{background:#1b2130;padding:2px 6px;"
        "border-radius:5px;color:#8ab4f8}"
        "</style></head><body><div class='card'>"
        f"<h1>{html.escape(title)}</h1>{body}</div></body></html>"
    )


#: (code, state) -> (title, body, tone). Injected so the server stays dumb and
#: the flow logic stays testable without a socket.
CallbackFn = Callable[[str, str], Awaitable[tuple[str, str, str]]]


class OAuthCallbackServer:
    """A one-route HTTP server for the OAuth redirect.

    Started as an asyncio task from the plugin; stopped from `terminate()`.
    A failure to bind (port in use, no permission) is reported once and then
    ignored — it must not stop the rest of the plugin from working.
    """

    def __init__(self, host: str, port: int, on_callback: CallbackFn,
                 path: str = CALLBACK_PATH):
        self.host = str(host)
        self.port = int(port)
        self.path = path
        self._on_callback = on_callback
        self._runner = None
        self._site = None
        self._started = False
        self.error: str | None = None

    @property
    def started(self) -> bool:
        return self._started

    async def start(self) -> bool:
        if self._started:
            return True
        try:
            from aiohttp import web
        except Exception as exc:  # noqa: BLE001
            self.error = f"aiohttp 不可用：{type(exc).__name__}"
            logger.warning(f"[scorecard] OAuth 回调服务未启动：{self.error}")
            return False

        app = web.Application()
        app.router.add_get(self.path, self._handle)
        self._runner = web.AppRunner(app)
        try:
            await self._runner.setup()
            self._site = web.TCPSite(self._runner, self.host, self.port)
            await self._site.start()
        except OSError as exc:
            # Port busy / not permitted. Say which address so the fix is obvious.
            self.error = (f"无法监听 {self.host}:{self.port}（{type(exc).__name__}）"
                          f" —— 端口被占用或没有权限，可在插件配置里换一个端口")
            logger.warning(f"[scorecard] OAuth 回调服务未启动：{self.error}")
            await self._cleanup()
            return False
        except Exception as exc:  # noqa: BLE001
            self.error = f"{type(exc).__name__}"
            logger.warning(f"[scorecard] OAuth 回调服务未启动：{self.error}")
            await self._cleanup()
            return False

        self._started = True
        self.error = None
        logger.info(
            f"[scorecard] OAuth 回调服务已启动：http://{self.host}:{self.port}{self.path}")
        return True

    async def _cleanup(self) -> None:
        if self._runner is not None:
            try:
                await self._runner.cleanup()
            except Exception:  # noqa: BLE001
                pass
        self._runner = None
        self._site = None
        self._started = False

    async def stop(self) -> None:
        if self._runner is None:
            return
        await self._cleanup()
        logger.info("[scorecard] OAuth 回调服务已停止")

    async def _handle(self, request):
        from aiohttp import web

        state = request.query.get("state", "")
        code = request.query.get("code", "")
        error = request.query.get("error", "")

        if error:
            # osu! sends `error=access_denied` when the user clicks "Cancel".
            body = ("<p>osu! 返回：<code>%s</code></p><p>你可以回到聊天里重新发送 "
                    "<code>bind &lt;名字&gt;</code> 再试一次。</p>" % html.escape(error))
            return web.Response(text=_page("授权被取消", body, "warn"),
                                content_type="text/html", charset="utf-8")

        if not code or not state:
            body = "<p>这个地址需要 osu! 带 <code>code</code> 和 <code>state</code> 跳转过来。</p>"
            return web.Response(text=_page("参数不全", body, "err"),
                                content_type="text/html", charset="utf-8")

        try:
            title, message, tone = await self._on_callback(code, state)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[scorecard] OAuth 回调处理失败 {type(exc).__name__}")
            title, message, tone = "授权失败", "服务器处理时出错了，请回到聊天里重试。", "err"

        return web.Response(text=_page(title, f"<p>{html.escape(message)}</p>", tone),
                            content_type="text/html", charset="utf-8")


def redirect_uri(base: str, path: str = CALLBACK_PATH) -> str:
    """Join a configured base with the callback path.

    osu! matches the redirect_uri **literally**, so this must produce exactly
    what the user registered — no trailing-slash surprises.
    """
    b = str(base or "").strip().rstrip("/")
    p = "/" + str(path or CALLBACK_PATH).lstrip("/")
    return b + p if b else p


async def run_server(server: OAuthCallbackServer) -> None:
    """Start the server, swallowing anything that would kill the task."""
    try:
        await server.start()
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001
        server.error = f"{type(exc).__name__}"
        logger.warning(f"[scorecard] OAuth 回调服务启动异常：{server.error}")
