"""Minimal Chrome DevTools Protocol client — stdlib only.

The render service deliberately has no third-party dependencies (`webapp.py` imports
Pillow/numpy lazily, only inside a render job). Driving headless Chrome therefore
cannot use Playwright, so this implements just enough of CDP: an HTTP call to
enumerate/create targets, and a small WebSocket client for the protocol itself.

WebSocket details that matter and are easy to get wrong:
  * client frames MUST be masked; server frames MUST NOT be,
  * payload length uses 7 bits, then 16, then 64,
  * a message may arrive split across continuation frames,
  * ping frames must be answered with a pong or the connection is dropped.

Usage:
    cdp = CDP("127.0.0.1", 9222)
    sid = cdp.attach_page()
    cdp.call("Runtime.evaluate", {"expression": "1+1"}, session=sid)
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import socket
import struct
import time
import urllib.request
from typing import Any

_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


class CDPError(RuntimeError):
    pass


class _WebSocket:
    """The smallest client WebSocket that can carry CDP JSON messages."""

    def __init__(self, url: str, timeout: float = 30.0) -> None:
        if not url.startswith("ws://"):
            raise CDPError(f"only ws:// is supported, got {url!r}")
        rest = url[5:]
        hostport, _, path = rest.partition("/")
        path = "/" + path
        host, _, port_s = hostport.partition(":")
        self.host, self.port = host, int(port_s or 80)
        self.sock = socket.create_connection((self.host, self.port), timeout=timeout)
        self.sock.settimeout(timeout)
        self._handshake(path)
        self._buf = b""

    def _handshake(self, path: str) -> None:
        key = base64.b64encode(os.urandom(16)).decode()
        req = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {self.host}:{self.port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        self.sock.sendall(req.encode())
        header = b""
        while b"\r\n\r\n" not in header:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise CDPError("connection closed during WebSocket handshake")
            header += chunk
        head, _, rest = header.partition(b"\r\n\r\n")
        status = head.split(b"\r\n", 1)[0].decode("latin-1")
        if "101" not in status:
            raise CDPError(f"WebSocket upgrade failed: {status}")
        expect = base64.b64encode(hashlib.sha1((key + _GUID).encode()).digest()).decode()
        if expect.encode() not in head:
            raise CDPError("WebSocket handshake returned the wrong Sec-WebSocket-Accept")
        self._buf = rest

    # ── framing ──

    def _recv_exact(self, n: int) -> bytes:
        while len(self._buf) < n:
            chunk = self.sock.recv(max(4096, n - len(self._buf)))
            if not chunk:
                raise CDPError("connection closed")
            self._buf += chunk
        out, self._buf = self._buf[:n], self._buf[n:]
        return out

    def _send_frame(self, opcode: int, payload: bytes) -> None:
        header = bytearray([0x80 | opcode])          # FIN + opcode
        n = len(payload)
        if n < 126:
            header.append(0x80 | n)                  # mask bit set
        elif n < (1 << 16):
            header.append(0x80 | 126)
            header += struct.pack(">H", n)
        else:
            header.append(0x80 | 127)
            header += struct.pack(">Q", n)
        mask = os.urandom(4)
        header += mask
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.sock.sendall(bytes(header) + masked)

    def _read_message(self) -> str:
        data = bytearray()
        while True:
            b1, b2 = self._recv_exact(2)
            fin = bool(b1 & 0x80)
            opcode = b1 & 0x0F
            length = b2 & 0x7F
            if length == 126:
                length = struct.unpack(">H", self._recv_exact(2))[0]
            elif length == 127:
                length = struct.unpack(">Q", self._recv_exact(8))[0]
            mask = self._recv_exact(4) if (b2 & 0x80) else None
            payload = self._recv_exact(length) if length else b""
            if mask:
                payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))

            if opcode == 0x8:                        # close
                raise CDPError("server closed the WebSocket")
            if opcode == 0x9:                        # ping
                self._send_frame(0xA, payload)
                continue
            if opcode == 0xA:                        # pong
                continue
            data += payload
            if fin:
                return data.decode("utf-8", "replace")

    def send_json(self, obj: dict) -> None:
        self._send_frame(0x1, json.dumps(obj).encode())

    def recv_json(self) -> dict:
        return json.loads(self._read_message())

    def close(self) -> None:
        try:
            self._send_frame(0x8, b"")
        except Exception:
            pass
        try:
            self.sock.close()
        except Exception:
            pass


class CDP:
    """Browser-level CDP connection. Page commands go through an attached session."""

    def __init__(self, host: str = "127.0.0.1", port: int = 9222,
                 timeout: float = 120.0) -> None:
        self.host, self.port, self.timeout = host, port, timeout
        self._next_id = 0
        self.ws: _WebSocket | None = None

    # ── HTTP side ──

    def _http(self, path: str, method: str = "GET") -> Any:
        url = f"http://{self.host}:{self.port}{path}"
        req = urllib.request.Request(url, method=method)
        with urllib.request.urlopen(req, timeout=10) as r:
            body = r.read()
        return json.loads(body) if body.strip().startswith(b"{") else body

    def version(self) -> dict:
        return self._http("/json/version")

    # ── lifecycle ──

    def connect(self) -> "CDP":
        info = self.version()
        ws_url = info.get("webSocketDebuggerUrl")
        if not ws_url:
            raise CDPError("no webSocketDebuggerUrl from /json/version")
        self.ws = _WebSocket(ws_url, timeout=self.timeout)
        return self

    def close(self) -> None:
        if self.ws:
            self.ws.close()
            self.ws = None

    # ── protocol ──

    def call(self, method: str, params: dict | None = None,
             session: str | None = None, timeout: float | None = None) -> dict:
        """Send one command and wait for its reply, discarding unrelated events."""
        if self.ws is None:
            raise CDPError("connect() first")
        self._next_id += 1
        msg_id = self._next_id
        payload = {"id": msg_id, "method": method, "params": params or {}}
        if session:
            payload["sessionId"] = session
        self.ws.send_json(payload)

        deadline = time.monotonic() + (timeout or self.timeout)
        while True:
            if time.monotonic() > deadline:
                raise CDPError(f"{method} timed out")
            msg = self.ws.recv_json()
            if msg.get("id") != msg_id:
                continue                              # an event or another reply
            if "error" in msg:
                raise CDPError(f"{method} failed: {msg['error']}")
            return msg.get("result") or {}

    def evaluate(self, expression: str, session: str | None = None,
                 await_promise: bool = False, timeout: float | None = None) -> Any:
        """Run JS in the page and return its value (raises on a JS exception)."""
        res = self.call("Runtime.evaluate", {
            "expression": expression,
            "returnByValue": True,
            "awaitPromise": await_promise,
            "userGesture": True,
        }, session=session, timeout=timeout)
        if res.get("exceptionDetails"):
            detail = res["exceptionDetails"]
            text = (detail.get("exception") or {}).get("description") or detail.get("text")
            raise CDPError(f"JS error: {text}")
        return (res.get("result") or {}).get("value")

    # ── targets ──

    def attach_page(self, url: str = "about:blank") -> str:
        """Create a new tab and return its session id."""
        target = self.call("Target.createTarget", {"url": url})
        target_id = target["targetId"]
        self._last_target = target_id
        attached = self.call("Target.attachToTarget",
                             {"targetId": target_id, "flatten": True})
        return attached["sessionId"]

    def close_last_target(self) -> None:
        tid = getattr(self, "_last_target", None)
        if tid:
            try:
                self.call("Target.closeTarget", {"targetId": tid})
            except Exception:
                pass
            self._last_target = None
