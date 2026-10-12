"""Async official osu! client. Only this module handles application credentials.

Public client_credentials only. No user tokens, no refresh-token import, no
cross-plugin credential stores. Errors never include bodies or HTTP headers.
"""

import asyncio
import json
import time
from collections import OrderedDict
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

import aiohttp

API_BASE = "https://osu.ppy.sh/api/v2"
TOKEN_URL = "https://osu.ppy.sh/oauth/token"


class APIError(Exception):
    def __init__(self, code, message, status=None):
        super().__init__(message)
        self.code, self.status = code, status


def retry_seconds(value):
    try:
        return max(0, float(value))
    except (TypeError, ValueError):
        try:
            return max(
                0, (parsedate_to_datetime(value) - datetime.now(UTC)).total_seconds()
            )
        except (TypeError, ValueError, OverflowError):
            return 2.0


class OsuClient:
    def __init__(self, credential_file, *, proxy="", timeout=20, cache_seconds=60):
        self.credential_file = Path(credential_file)
        self.proxy = proxy or None
        self.timeout = min(30, max(5, int(timeout)))
        self.cache_seconds = min(3600, max(60, int(cache_seconds)))
        self._session = None
        self._token = ""
        self._expires = 0.0
        self._token_lock = asyncio.Lock()
        self._rate_lock = asyncio.Lock()
        self._next_request = 0.0
        self._blocked_until = 0.0
        self._cache = OrderedDict()
        self._inflight = {}

    async def close(self):
        for task in self._inflight.values():
            task.cancel()
        await asyncio.gather(*self._inflight.values(), return_exceptions=True)
        self._inflight.clear()
        if self._session is not None:
            await self._session.close()
            self._session = None
        self._token = ""
        self._cache.clear()

    async def _session_get(self):
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout),
                headers={
                    "Accept": "application/json",
                    "User-Agent": "AstrBot-osu-tools/1.0.0",
                    "x-api-version": "20220705",
                },
                trust_env=False,
            )
        return self._session

    async def _rate_wait(self):
        async with self._rate_lock:
            await asyncio.sleep(max(0, self._next_request - time.monotonic()))
            self._next_request = time.monotonic() + 1.05

    async def _http(self, method, url, *, token=None, params=None, body=None):
        session = await self._session_get()
        await self._rate_wait()
        self._check_cooldown()
        try:
            async with session.request(
                method,
                url,
                headers={"Authorization": "Bearer " + token} if token else {},
                params=params,
                json=body,
                proxy=self.proxy,
                allow_redirects=False,
            ) as response:
                status = response.status
                if status == 429:
                    self._set_cooldown(response.headers.get("Retry-After"))
                if status >= 300:
                    # Do not read error bodies, which can contain request data.
                    return status, None, response.headers.get("Retry-After")
                raw = bytearray()
                async for chunk in response.content.iter_chunked(65536):
                    raw.extend(chunk)
                    if len(raw) > 4 * 1024 * 1024:
                        raise APIError(
                            "response_too_large", "响应超过 4 MiB；请缩小查询。"
                        )
                try:
                    return status, json.loads(raw), None
                except (ValueError, UnicodeError):
                    raise APIError(
                        "invalid_response", "osu! 返回的内容不是 JSON。"
                    ) from None
        except (TimeoutError, aiohttp.ClientError):
            raise APIError(
                "network_error", "连接 osu! 超时或网络不可用，请稍后重试。"
            ) from None

    def _set_cooldown(self, retry_after):
        wait = min(86400, max(1, retry_seconds(retry_after)))
        self._blocked_until = max(self._blocked_until, time.monotonic() + wait)
        return wait

    def _check_cooldown(self):
        if self._blocked_until > time.monotonic():
            raise APIError(
                "rate_limited", "osu! 要求等待后重试，目前仍处于限流等待期。", 429
            )

    def _credentials(self):
        try:
            values = json.loads(self.credential_file.read_text(encoding="utf-8-sig"))
            client_id = values.get("osu_client_id", values.get("client_id"))
            secret = values.get("osu_client_secret", values.get("client_secret"))
            if (
                not str(client_id).isdigit()
                or not isinstance(secret, str)
                or not secret
            ):
                raise ValueError
            return {
                "client_id": int(client_id),
                "client_secret": secret,
                "grant_type": "client_credentials",
                "scope": "public",
            }
        except (OSError, ValueError, TypeError, AttributeError):
            raise APIError(
                "credential_error", "凭据文件不可用，请管理员检查文件路径和字段。"
            ) from None

    async def _access_token(self, stale=None):
        async with self._token_lock:
            if (
                self._token
                and time.monotonic() < self._expires
                and self._token != stale
            ):
                return self._token
            payload = await asyncio.to_thread(self._credentials)
            status, data, _retry = await self._http("POST", TOKEN_URL, body=payload)
            if status != 200:
                raise APIError(
                    "oauth_error",
                    f"OAuth 获取令牌失败（HTTP {status}），请管理员检查应用凭据。",
                    status,
                )
            if not isinstance(data, dict) or not isinstance(
                data.get("access_token"), str
            ):
                raise APIError("oauth_error", "OAuth 响应缺少令牌。")
            try:
                ttl = float(data["expires_in"])
                if not 0 < ttl < 365 * 86400:
                    raise ValueError
            except (KeyError, ValueError, TypeError):
                raise APIError("oauth_error", "OAuth 响应有效期异常。") from None
            self._token = data["access_token"]
            self._expires = time.monotonic() + max(1, ttl - min(60, ttl / 10))
            return self._token

    async def query(self, method, path, params, body, *, authenticated=True):
        if (
            method not in {"GET", "POST"}
            or not path.startswith("/")
            or path.startswith("//")
        ):
            raise APIError("invalid_request", "请求不在查询范围。")
        if method == "POST" and not (
            path.startswith("/beatmaps/") and path.endswith("/attributes")
        ):
            raise APIError("invalid_request", "仅允许公开查询及谱面难度计算。")
        key = json.dumps([method, path, params, body, authenticated], sort_keys=True)
        now = time.monotonic()
        cached = self._cache.get(key)
        if cached and cached[0] > now:
            self._cache.move_to_end(key)
            return cached[1], True
        self._check_cooldown()
        task = self._inflight.get(key)
        if task is None:
            if len(self._inflight) >= 16:
                raise APIError("busy", "查询队列已满，请稍后再试。")
            task = asyncio.create_task(
                self._fetch(method, path, params, body, authenticated)
            )
            self._inflight[key] = task
            task.add_done_callback(lambda done: self._inflight.pop(key, None))
        data = await asyncio.shield(task)
        self._cache[key] = (time.monotonic() + self.cache_seconds, data)
        while len(self._cache) > 128:
            self._cache.popitem(last=False)
        return data, False

    async def _fetch(self, method, path, params, body, authenticated):
        token = await self._access_token() if authenticated else None
        refreshed = False
        for attempt in range(3):
            status, data, retry = await self._http(
                method,
                API_BASE + path,
                token=token,
                params=params,
                body=body if method == "POST" else None,
            )
            if 200 <= status < 300:
                return data
            if status == 401 and authenticated and not refreshed:
                token = await self._access_token(stale=token)
                refreshed = True
                continue
            if status == 429:
                wait = self._set_cooldown(retry)
                if wait > 5 or attempt == 2:
                    raise APIError(
                        "rate_limited", "osu! 请求限流，请稍后再试。", status
                    )
                await asyncio.sleep(max(1, wait))
                continue
            if status >= 500 and attempt < 2:
                await asyncio.sleep(2**attempt)
                continue
            messages = {
                401: "应用令牌无效。",
                403: "接口拒绝访问；可能需要用户授权或额外权限。",
                404: "没有找到数据；检查 ID、模式、成绩 ID 类型和访问权限。",
                422: "osu! 拒绝了请求参数；请核对接口说明。",
            }
            raise APIError(
                "api_error",
                messages.get(status, f"osu! 查询失败（HTTP {status}）。"),
                status,
            )
        raise APIError("api_error", "osu! 查询重试次数已用完。")
