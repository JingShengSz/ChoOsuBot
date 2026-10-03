#!/usr/bin/env python
"""Produce, on the VPS, the EXACT text the AstrBot plugin shows in chat when the render
node is offline -- by running the deployed plugin's own code, not by paraphrasing it.

It loads /opt/astrbot/data/plugins/astrbot_plugin_mania_render/main.py, builds the plugin
object without AstrBot's Star lifecycle, and calls the real ManiaRenderPlugin._render().
The chat command `om` does exactly this and, when `_render` returns sent=False, yields
`event.plain_result(text)` -- so the text printed here IS what lands in the chat.

Run: /opt/astrbot/.venv/bin/python /tmp/offline-harness.py [bid] [range]
"""
import asyncio
import importlib.util
import json
import sys
import traceback
from pathlib import Path

# The astrbot package lives at /opt/astrbot/astrbot; astrbot.service runs with
# WorkingDirectory=/opt/astrbot, which is what puts it on sys.path. Reproduce that here.
sys.path.insert(0, "/opt/astrbot")

PLUGIN = Path("/opt/astrbot/data/plugins/astrbot_plugin_mania_render/main.py")
CONFIG = Path("/opt/astrbot/data/config/astrbot_plugin_mania_render_config.json")

spec = importlib.util.spec_from_file_location("mania_render_under_test", PLUGIN)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

cfg = json.loads(CONFIG.read_text(encoding="utf-8-sig"))


class FakeEvent:
    """Just enough of AstrMessageEvent for _render() to run and record what it sent."""

    def __init__(self):
        self.sent = []

    async def send(self, chain):
        self.sent.append(chain)

    def plain_result(self, text):
        return text

    def chain_result(self, comps):
        return comps


def make_plugin():
    # Bypass Star.__init__ (it wants a live AstrBot Context); everything _render touches
    # is set explicitly here, so this is the same object the bot uses at runtime.
    p = mod.ManiaRenderPlugin.__new__(mod.ManiaRenderPlugin)
    p.config = cfg
    p.data_dir = Path("/tmp/mania-harness-data")
    p.data_dir.mkdir(parents=True, exist_ok=True)
    p._render_lock = asyncio.Lock()
    p._background = set()
    return p


async def main():
    bid = sys.argv[1] if len(sys.argv) > 1 else "5366777"
    rng = sys.argv[2] if len(sys.argv) > 2 else "0-8"

    p = make_plugin()
    print(f"plugin file  : {PLUGIN}")
    print(f"configured   : server={p.server!r} engine={p.engine!r} timeout={p.timeout}s")

    # Show the raw transport failure the plugin has to interpret.
    import aiohttp
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as s:
            async with s.get(f"{p.server}/api/skins") as r:
                print(f"raw probe    : HTTP {r.status} -- NODE IS UP")
    except Exception as exc:
        print(f"raw probe    : {type(exc).__name__}: {exc}")
        print(f"classified   : _is_unreachable() -> {mod._is_unreachable(exc)}")

    ev = FakeEvent()
    try:
        sent, text = await p._render(ev, {"bid": bid, "range": rng}, None)
    except Exception:
        print("!! _render RAISED -- it should have returned a refusal:")
        traceback.print_exc()
        return 1

    print(f"_render      : sent={sent}  (chat sends `text` only when sent is False)")
    print()
    print("======== EXACT TEXT THE USER SEES IN CHAT ========")
    print(text)
    print("==================================================")
    return 0


sys.exit(asyncio.run(main()))
