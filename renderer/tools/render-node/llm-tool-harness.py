#!/usr/bin/env python
"""Prove `render_mania_video` -- the LLM tool -- can now serve the exact request that failed
in production: a score link plus a skin, in natural language.

Runs the DEPLOYED plugin's own tool coroutine, with `_score_replay` stubbed (no osu! API
call) and `_render` stubbed (no render, nothing sent to QQ). Shows the opts that reach the
render call.

Run: /opt/astrbot/.venv/bin/python /tmp/llm-tool-harness.py
"""
import asyncio
import importlib.util
import inspect
import json
import sys
from pathlib import Path

sys.path.insert(0, "/opt/astrbot")

PLUGIN = Path("/opt/astrbot/data/plugins/astrbot_plugin_mania_render/main.py")
CONFIG = Path("/opt/astrbot/data/config/astrbot_plugin_mania_render_config.json")
SCORE_LINK = "https://osu.ppy.sh/scores/7518410895"
BID = "5366777"

spec = importlib.util.spec_from_file_location("mania_tool_under_test", PLUGIN)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
cfg = json.loads(CONFIG.read_text(encoding="utf-8-sig"))

failures = []


def check(label, got, want):
    ok = got == want
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}: got={got!r} want={want!r}", flush=True)
    if not ok:
        failures.append(label)


class FakeEvent:
    def __init__(self, text=""):
        self.message_str = text
        self.sent = []

    async def send(self, chain):
        self.sent.append(chain)

    def plain_result(self, text):
        return ("plain", text)


def make_plugin():
    p = mod.ManiaRenderPlugin.__new__(mod.ManiaRenderPlugin)
    p.config = dict(cfg)
    p.data_dir = Path("/tmp/mania-harness-data")
    p.data_dir.mkdir(parents=True, exist_ok=True)
    p._render_lock = asyncio.Lock()
    p._background = set()
    return p


def tool_fn():
    fn = mod.ManiaRenderPlugin.render_mania_video
    for cand in (fn, getattr(fn, "__wrapped__", None), getattr(fn, "__func__", None)):
        if cand is not None and inspect.iscoroutinefunction(cand):
            return cand
    raise SystemExit("could not resolve render_mania_video to a coroutine function")


def tool_params():
    """The parameter list the LLM is shown."""
    raw = mod.ManiaRenderPlugin.render_mania_video
    fn = getattr(raw, "__wrapped__", raw)
    while not inspect.iscoroutinefunction(fn) and hasattr(fn, "__wrapped__"):
        fn = fn.__wrapped__
    sig = inspect.signature(fn)
    return [n for n in sig.parameters if n not in ("self", "event")]


async def main():
    print(f"plugin file : {PLUGIN}")
    print(f"tool fn     : {tool_fn().__qualname__}")
    print(f"tool params : {tool_params()}")
    print()

    print("1. the schema can now express the production request", flush=True)
    check("a `score` parameter exists", "score" in tool_params(), True)
    check("`bid` still exists", "bid" in tool_params(), True)
    doc = (mod.ManiaRenderPlugin.render_mania_video.__doc__ or "")
    check("docstring mentions the score link form", "osu.ppy.sh/scores/" in doc, True)
    check("docstring tells the agent NOT to shell out",
          "astrbot_execute_shell" in doc and "SKILL.md" in doc, True)

    # ── 2. a score link drives a render without any shell/python ──────────────
    print("\n2. score=<link> + skin  -> submits a render with the replay attached", flush=True)
    p = make_plugin()
    seen = {}

    async def fake_score_replay(sid):
        seen["score_id"] = sid
        return "ok", (b"r" * 400, BID)

    async def fake_render(event, opts, osr_bytes):
        seen["opts"] = dict(opts)
        seen["osr_len"] = len(osr_bytes) if osr_bytes else 0
        return True, "ok"

    p._score_replay = fake_score_replay
    p._render = fake_render
    p._collect_osr = lambda ev: (_ for _ in ()).throw(
        AssertionError("must not touch the message for a .osr when score is given"))

    result = await tool_fn()(p, FakeEvent("小秋这个换boj那个皮肤渲染"), score=SCORE_LINK, skin="boj")
    for t in list(p._background):
        await t

    check("the score id was parsed out of the link", seen.get("score_id"), "7518410895")
    check("opts.bid came from the replay", seen.get("opts", {}).get("bid"), BID)
    check("opts.skin is what the user asked for", seen.get("opts", {}).get("skin"), "boj")
    check("the replay bytes reached the render", seen.get("osr_len"), 400)
    check("no shell/.osr lookup happened", "osr_len" in seen, True)
    print(f"     tool returned: {result!r}", flush=True)
    print(f"     render opts  : {seen.get('opts')}", flush=True)

    # ── 3. bare score id works too ────────────────────────────────────────────
    print("\n3. score=<digits only>  -> same path", flush=True)
    p = make_plugin()
    seen.clear()
    p._score_replay = fake_score_replay
    p._render = fake_render
    await tool_fn()(p, FakeEvent(), score="7518410895")
    for t in list(p._background):
        await t
    check("score id parsed", seen.get("score_id"), "7518410895")
    check("bid from replay", seen.get("opts", {}).get("bid"), BID)

    # ── 4. a non-mania score is reported, not silently dropped ───────────────
    print("\n4. score=<non-mania>  -> reported", flush=True)
    p = make_plugin()
    seen.clear()

    async def fake_skip(sid):
        return "skip", None

    p._score_replay = fake_skip
    p._render = fake_render
    result = await tool_fn()(p, FakeEvent(), score=SCORE_LINK)
    check("nothing was submitted", "opts" in seen, False)
    check("the model is told why", "mania" in str(result), True)
    print(f"     tool returned: {result!r}", flush=True)

    # ── 5. a bad score argument is reported ──────────────────────────────────
    print("\n5. score=<no digits>  -> reported", flush=True)
    p = make_plugin()
    p._score_replay = fake_score_replay
    p._render = fake_render
    result = await tool_fn()(p, FakeEvent(), score="不是链接")
    check("the model is told what score wants", "成绩" in str(result), True)
    print(f"     tool returned: {result!r}", flush=True)

    print("\n" + "=" * 70, flush=True)
    if failures:
        print(f"FAILURES ({len(failures)}):", flush=True)
        for f in failures:
            print(f"  - {f}", flush=True)
        return 1
    print("ALL LLM-TOOL CHECKS PASSED", flush=True)
    return 0


sys.exit(asyncio.run(main()))
