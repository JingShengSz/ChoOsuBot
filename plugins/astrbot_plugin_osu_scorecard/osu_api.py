"""Small synchronous osu! API client shared by local tools and score cards.

Client credentials stay in memory; neither credentials nor bearer tokens are logged.
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

#: OAuth endpoints. `authorize` is a browser page; `token` is a JSON POST.
OSU_AUTHORIZE = "https://osu.ppy.sh/oauth/authorize"
OSU_TOKEN = "https://osu.ppy.sh/oauth/token"

#: The .osu download. `https://osu.ppy.sh/osu/<beatmap id>` is the beatmap file
#: itself: public, no OAuth, no application token, no rate-limit header games.
#: It is what the game client downloads, so its md5 equals the beatmap's
#: `checksum` — which is how you can prove you counted the right difficulty.
OSU_BEATMAP_FILE = "https://osu.ppy.sh/osu/{beatmap_id}"

#: A 4K map is 20-250 KB of text. Anything past this is not a beatmap file.
_MAX_OSU_BYTES = 4 * 1024 * 1024


def fetch_beatmap_file(beatmap_id, proxy: str = "", timeout: int = 30) -> str:
    """Download one beatmap's .osu text. Public endpoint — no credentials at all.

    Deliberately a module function rather than an `OsuApi` method: `OsuApi.__init__`
    refuses to exist without client credentials, and this call needs none. A card
    must still be able to count a map on a machine that has never been given an
    osu! key.

    Goes through `effective_proxies()` and its own opener for the reason spelled
    out there — the global opener is shared state, and on this machine a direct
    connection to osu.ppy.sh does not resolve at all (Cloudflare answers curl
    with 403), while the proxy answers in under a second.
    """
    text = str(beatmap_id or "").strip()
    if not text.isdigit():
        raise ValueError("Expected a numeric osu! beatmap id")
    url = OSU_BEATMAP_FILE.format(beatmap_id=text)
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler(effective_proxies(proxy)))
    request = urllib.request.Request(url, headers={"User-Agent": "mania-render/0.1"})
    try:
        with opener.open(request, timeout=timeout) as response:
            raw = response.read(_MAX_OSU_BYTES + 1)
    except urllib.error.HTTPError as exc:
        # 404 is the ordinary "no such map" answer and callers treat it as such.
        raise RuntimeError(f"osu! .osu download HTTP {exc.code} for beatmap {text}") from None
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"osu! .osu download failed for beatmap {text}: "
                           f"{type(exc).__name__}") from None
    if len(raw) > _MAX_OSU_BYTES:
        raise RuntimeError(f"osu! .osu for beatmap {text} is implausibly large")
    return raw.decode("utf-8", "replace")


@dataclass(frozen=True)
class PlayerProfile:
    """Public fields shared by score cards, player cards and other modules.

    total_pp is CURRENT user.statistics.pp for ruleset, not this score's pp and
    not a historical value at the time of the play. None means unavailable.
    team is osu!'s official user.team object (id/name/short_name/flag_url when
    present), or None for no returned team; it is not the user's country.
    avatar_url is the official user.avatar_url; callers must not construct it
    from the ID because the API URL can include a cache/version query string.
    """
    user_id: int
    username: str
    avatar_url: str | None
    total_pp: float | None
    ruleset: str
    team: dict | None
    global_rank: int | None
    country_rank: int | None


def player_profile(user: dict, ruleset: str) -> PlayerProfile:
    """Normalize a full /users/{id}/{ruleset} response without network access.

    A compact user embedded in a score may lack statistics/team. Use
    OsuApi.player() when fetching complete current information.
    Preserve unknown/missing values rather than converting them to zero.
    """
    stats = user.get("statistics") or {}
    return PlayerProfile(
        user_id=int(user["id"]), username=user["username"],
        avatar_url=user.get("avatar_url"),
        total_pp=float(stats["pp"]) if stats.get("pp") is not None else None,
        ruleset=ruleset, team=user.get("team") or None,
        global_rank=stats.get("global_rank"), country_rank=stats.get("country_rank"),
    )


def score_id(value: str) -> str:
    value = str(value).strip()
    if re.fullmatch(r"[0-9]+", value):
        return value
    match = re.fullmatch(r"https://osu\.ppy\.sh/(?:community/)?scores/([0-9]+)/?(?:\?[^#]*)?(?:#.*)?", value)
    if not match:
        raise ValueError("Expected an osu! score ID or https://osu.ppy.sh/scores/<id>")
    return match[1]

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



class OsuApi:
    def __init__(self, client_id: str, client_secret: str, proxy: str = ""):
        self._proxy = proxy
        self._id, self._secret = str(client_id).strip(), str(client_secret).strip()
        if not self._id or not self._secret:
            raise ValueError("Fill osu_client_id and osu_client_secret in the local configuration")
        self._token = ""
        self._expires = 0.0
        # 自建 opener 并显式带上系统代理。
        # 不能依赖 urllib.request.urlopen()：它用的是全局 opener，任何库调一次
        # install_opener() 都可能把它换成不带 ProxyHandler 的版本，请求就会直连。
        # 实测（本机）：直连 api.ppy.sb 要 21 秒才超时，走代理 0.12 秒。
        self._opener = urllib.request.build_opener(
            urllib.request.ProxyHandler(effective_proxies(getattr(self, "_proxy", ""))))

    @classmethod
    def from_file(cls, path: Path, proxy: str = "") -> "OsuApi":
        data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        return cls(data.get("osu_client_id", ""),
                   data.get("osu_client_secret", ""), proxy=proxy)

    def _request(self, url: str, *, data=None, authorized=False) -> dict:
        headers = {"Accept": "application/json", "User-Agent": "mania-render/0.1"}
        if authorized:
            headers.update({"Authorization": f"Bearer {self._token}", "x-api-version": "20220705"})
        body = None
        if data is not None:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
            body = urllib.parse.urlencode(data).encode()
        try:
            with self._opener.open(urllib.request.Request(url, body, headers), timeout=45) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            # Do not echo server bodies, request headers or credential payloads.
            raise RuntimeError(f"osu! API HTTP {exc.code} at {urllib.parse.urlparse(url).path}") from None

    def _token_value(self) -> str:
        """A valid bearer token, refreshed when the cached one is about to expire."""
        if time.time() >= self._expires:
            token = self._request("https://osu.ppy.sh/oauth/token", data={
                "client_id": self._id, "client_secret": self._secret,
                "grant_type": "client_credentials", "scope": "public",
            })
            self._token = token["access_token"]
            self._expires = time.time() + max(0, int(token["expires_in"]) - 60)
        return self._token

    def get(self, endpoint: str, params: dict | None = None,
            token: str | None = None):
        """GET an API path, optionally with query parameters.

        Query parameters are passed through `params` rather than baked into
        `endpoint`, so the path stays a path and the "?" guard below keeps
        rejecting a hand-built query string. Callers that already pass a bare
        path are unaffected — `params` is optional and defaults to no query.

        `token` overrides the application token with a USER token. Only that
        unlocks `/users/{id}/{mode}/scores/recent`, which answers 404 to an
        application token no matter how the request is shaped.

        The request goes through `self._opener`, never `urllib.request.urlopen`:
        the global opener is shared state that any library can replace with one
        that has no ProxyHandler, which silently turns every request into a
        direct connection. Measured in the AstrBot process: direct requests to
        the proxy-only hosts time out after 21 s, proxied ones answer in 0.1 s.
        """
        if not endpoint.startswith("/") or ".." in endpoint or "?" in endpoint:
            raise ValueError("Expected an API endpoint path; pass query values via params")
        url = "https://osu.ppy.sh/api/v2" + endpoint
        if params:
            clean = {k: v for k, v in params.items() if v is not None}
            if clean:
                url += "?" + urllib.parse.urlencode(clean)
        headers = {
            "Accept": "application/json",
            "User-Agent": "mania-render/0.1",
            "Authorization": f"Bearer {token or self._token_value()}",
            "x-api-version": "20220705",
        }
        try:
            with self._opener.open(urllib.request.Request(url, None, headers), timeout=45) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            # Never echo server bodies, request headers or credential payloads.
            raise RuntimeError(
                f"osu! API HTTP {exc.code} at {urllib.parse.urlparse(url).path}") from None

    @staticmethod
    def _user_segment(user) -> str:
        """A username or id as a safe path segment. Names carry spaces and dots."""
        return urllib.parse.quote(str(user).strip(), safe="")

    def user_by_name(self, user, ruleset: str) -> dict:
        """Full profile by username OR numeric id (the API accepts both)."""
        if ruleset not in ("osu", "taiko", "fruits", "mania"):
            raise ValueError("Unknown osu! ruleset")
        return self.get(f"/users/{self._user_segment(user)}/{ruleset}")

    def recent_scores(self, user, ruleset: str, *, include_fails: bool = False,
                      limit: int = 50, user_token: str | None = None) -> list:
        """Recent mania scores, newest first.

        include_fails=False  -> only passes, which is what `最近通过` means
        include_fails=True   -> every play, which is what `最近游玩` means

        **`user_token` is required.** osu! answers this endpoint with HTTP 404 to
        an application token whatever the request shape, so without a USER token
        the call cannot work at all. `authorize_url()` / `exchange_code()` below
        are how that token is obtained.

        路径是 `/users/{user}/scores/recent`，模式走 `mode` **查询参数**。
        把模式写成路径段（`/users/{user}/{ruleset}/scores/recent`）会 404，
        而且**应用令牌和用户令牌都 404** —— 极易被误判成「权限不够」，
        让人白做一遍 OAuth。实测（2026-10-03，同一条命令只换路径）：
            404  /users/32749965/mania/scores/recent
            200  /users/32749965/scores/recent?mode=mania
        加不加 `x-api-version`、参数叫 mode 还是 ruleset，都不影响结论。

        **第二层坑：这个端点只认数字 id，不认用户名。**
            404  /users/F6A8AF/scores/recent?mode=mania      <- body 是 {"error":null}
            200  /users/32749965/scores/recent?mode=mania
        两个 404 长得一模一样，而「没授权」也是 404，于是一个纯粹的参数
        问题会被报成「你还差一次授权」。所以这里对非数字的 `user` 先做一次
        `/users/{user}/{ruleset}` 把 id 解析出来再查。
        """
        if ruleset not in ("osu", "taiko", "fruits", "mania"):
            raise ValueError("Unknown osu! ruleset")
        ident = str(user).strip()
        if not ident.isdigit():
            # `/users/{name}/{mode}` 接受用户名，借它换成数字 id。
            resolved = self.user_by_name(ident, ruleset) or {}
            ident = str(resolved.get("id") or "").strip()
            if not ident.isdigit():
                raise RuntimeError(
                    f"osu! did not resolve '{user}' to a user id for {ruleset}")
        rows = self.get(
            f"/users/{ident}/scores/recent",
            {"mode": ruleset,
             "include_fails": 1 if include_fails else 0,
             "limit": max(1, min(100, limit))},
            token=user_token,
        )
        return rows if isinstance(rows, list) else []

    def score(self, reference: str) -> dict:
        return self.get(f"/scores/{score_id(reference)}")

    def user(self, user_id: int, ruleset: str) -> dict:
        if ruleset not in ("osu", "taiko", "fruits", "mania"):
            raise ValueError("Unknown osu! ruleset")
        return self.get(f"/users/{int(user_id)}/{ruleset}")

    def beatmap_user_scores(self, beatmap_id: int, user_id: int, ruleset: str) -> list[dict]:
        if ruleset not in ("osu", "taiko", "fruits", "mania"):
            raise ValueError("Unknown osu! ruleset")
        data = self.get(f"/beatmaps/{int(beatmap_id)}/scores/users/{int(user_id)}/all",
                        {"ruleset": ruleset, "legacy_only": 0})
        return data.get("scores", []) if isinstance(data, dict) else []

    def player(self, user_id: int, ruleset: str) -> PlayerProfile:
        """Fetch reusable current player identity, avatar, mode PP and team."""
        return player_profile(self.user(user_id, ruleset), ruleset)

    # ───────────────────────────── OAuth ─────────────────────────────
    #
    # The authorization_code flow. Needed because osu! returns HTTP 404 for
    # `/users/{id}/{mode}/scores/recent` unless the bearer token belongs to a
    # USER, not to the application. Every request here still goes through
    # `self._opener`, so the proxy fix above covers the token endpoints too.

    def authorize_url(self, redirect_uri: str, state: str,
                      scope: str = "public") -> str:
        """The URL to hand the user. Clicking it is the whole consent step.

        `state` travels through osu! untouched and comes back on the redirect,
        which is how the callback learns whose authorization this is.
        """
        query = urllib.parse.urlencode({
            "client_id": self._id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": scope,
            "state": state,
        })
        return OSU_AUTHORIZE + "?" + query

    def _token_request(self, data: dict) -> dict:
        """POST /oauth/token and normalize the reply.

        The reply carries a live `refresh_token` that is worth as much as a
        password. It is returned to the caller and never logged, never blamed
        in an exception, and never echoed to a chat.
        """
        payload = dict(data)
        payload["client_id"] = self._id
        payload["client_secret"] = self._secret
        raw = self._request(OSU_TOKEN, data=payload)
        access = str(raw.get("access_token") or "")
        if not access:
            raise RuntimeError("osu! token endpoint returned no access_token")
        try:
            expires_in = int(raw.get("expires_in") or 0)
        except (TypeError, ValueError):
            expires_in = 0
        return {
            "access_token": access,
            "refresh_token": str(raw.get("refresh_token") or ""),
            "expires_in": expires_in,
            # Refresh a minute early so a request cannot straddle the expiry.
            "expires_at": time.time() + max(0, expires_in - 60),
        }

    def exchange_code(self, code: str, redirect_uri: str) -> dict:
        """authorization_code -> a user token set."""
        return self._token_request({
            "grant_type": "authorization_code",
            "code": str(code),
            "redirect_uri": redirect_uri,
        })

    def refresh_user_token(self, refresh_token: str) -> dict:
        """refresh_token -> a fresh user token set.

        osu! invalidates the old refresh token and issues a new one on every
        call, so the caller MUST persist what comes back. Keeping the old value
        works exactly once and then fails forever.
        """
        return self._token_request({
            "grant_type": "refresh_token",
            "refresh_token": str(refresh_token),
            "scope": "public",
        })
