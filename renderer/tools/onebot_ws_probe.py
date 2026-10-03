"""Prove AstrBot's aiocqhttp reverse-WS endpoint accepts an OneBot connection.

    python tools/onebot_ws_probe.py [ws://127.0.0.1:6199/ws] [self_id]

Connects, sends a lifecycle meta event, prints whatever the server pushes back,
then disconnects. If this succeeds while LLBot is NOT connected, the AstrBot
side is healthy and the missing link is purely LLBot's ob11 `ws-reverse` entry.

The handshake headers are not optional: aiocqhttp's `_handle_wsr` reads
`websocket.headers['X-Client-Role']` and `_add_wsr_api_client` reads
`['X-Self-ID']` with no fallback, so a client that omits them gets a bare
HTTP 400 with no explanation. LLBot sends both on its own.
"""
from __future__ import annotations

import asyncio
import json
import sys
import time

import aiohttp

DEFAULT_URL = "ws://127.0.0.1:6199/ws"


async def main(url: str, self_id: int) -> int:
    headers = {
        "X-Client-Role": "Universal",
        "X-Self-ID": str(self_id),
        "User-Agent": "OneBot/11",
    }
    print(f"connecting to {url}")
    print(f"  X-Client-Role: Universal   X-Self-ID: {self_id}")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(
                url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)
            ) as ws:
                print("  CONNECTED (upgrade accepted)")

                hello = {
                    "post_type": "meta_event",
                    "meta_event_type": "lifecycle",
                    "sub_type": "connect",
                    "time": int(time.time()),
                    "self_id": self_id,
                }
                await ws.send_str(json.dumps(hello))
                print(f"  sent lifecycle/connect: {json.dumps(hello, ensure_ascii=False)}")

                # AstrBot pushes its own lifecycle handshake through the same socket.
                try:
                    msg = await asyncio.wait_for(ws.receive(), timeout=3.0)
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        print(f"  <- server said: {msg.data[:400]}")
                    else:
                        print(f"  <- server frame type: {msg.type.name}")
                except asyncio.TimeoutError:
                    print("  <- (no reply within 3s)")

                await ws.close()
                print("  closed cleanly")
        print("\nRESULT: AstrBot accepts reverse-WS connections.")
        return 0
    except aiohttp.WSServerHandshakeError as exc:
        print(f"  HANDSHAKE REJECTED: HTTP {exc.status} {exc.message}")
        print("\nRESULT: endpoint refused the upgrade.")
        return 2
    except aiohttp.ClientConnectorError as exc:
        print(f"  CANNOT CONNECT (nothing listening?): {exc}")
        print("\nRESULT: no listener on that port.")
        return 3
    except Exception as exc:  # noqa: BLE001 - diagnostic script
        print(f"  FAILED: {type(exc).__name__}: {exc}")
        return 4


if __name__ == "__main__":
    ws_url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL
    bot_uin = int(sys.argv[2]) if len(sys.argv) > 2 else 10001
    raise SystemExit(asyncio.run(main(ws_url, bot_uin)))
