#!/usr/bin/env python
"""Prove the AUTOMATIC score-link path honours options -- by running the DEPLOYED plugin's
own `auto_score()`, not by re-implementing it.

It loads /opt/astrbot/data/plugins/astrbot_plugin_mania_render/main.py (the file AstrBot
actually imports), builds the plugin object without AstrBot's Star lifecycle, and drives
the real handler with fake events.

`_api` is stubbed so the multipart form of the render REQUEST is captured field by field
instead of being posted; `_poll`/`_download` are stubbed so no render runs; the fake event's
`send` only records. Nothing reaches the render node and nothing reaches QQ.

Cases:
  1. `<link> -s Cho'`      -> the requested skin reaches the render request
  2. `<link>`              -> the CONFIGURED DEFAULT skin reaches it instead
  3. non-mania `<link>`    -> NO output at all (the silent-skip survives)
  4. `<link> -s nope`      -> a visible message, not silence
  5. `<link> -z 5`         -> the unusable option is named, not swallowed
  6. `<link> 皮肤 Cho'`    -> the Chinese bare alias works too
  7. prose + `<link>`      -> prose is not mistaken for a skin name (no regression)

Run: /opt/astrbot/.venv/bin/python /tmp/auto-score-harness.py
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

SKIN_KEYS = ["owc (default)", "Cho'", "R Skin", "boj 1-10K"]
SERVER_DEFAULT = "boj 1-10K"
SCORES = "https://osu.ppy.sh/scores/7518410895"
BID = "5366777"

spec = importlib.util.spec_from_file_location("mania_auto_under_test", PLUGIN)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

cfg = json.loads(CONFIG.read_text(encoding="utf-8-sig"))

failures = []
captured: list[dict] = []


def check(label, got, want):
    ok = got == want
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}: got={got!r} want={want!r}", flush=True)
    if not ok:
        failures.append(label)
    return ok


class FakeEvent:
    """Enough of AstrMessageEvent for auto_score()/_render() to run."""

    def __init__(self, text):
        self.message_str = text
        self.sent = []

    async def send(self, chain):
        self.sent.append(chain)

    def plain_result(self, text):
        return ("plain", text)

    def chain_result(self, comps):
        return ("chain", comps)


def make_plugin():
    p = mod.ManiaRenderPlugin.__new__(mod.ManiaRenderPlugin)
    p.config = dict(cfg)
    p.data_dir = Path("/tmp/mania-harness-data")
    p.data_dir.mkdir(parents=True, exist_ok=True)
    p._render_lock = asyncio.Lock()
    p._background = set()
    return p


def _name_and_value(entry):
    """aiohttp stores a field as `(headers, options, value)`; older builds as `(name, value)`."""
    if isinstance(entry, (tuple, list)) and len(entry) == 3:
        headers, _options, value = entry
        name = headers.get("name") if hasattr(headers, "get") else headers
        return str(name), value
    name, value = entry
    return str(name), value


def read_form(form) -> dict:
    """Pull the multipart fields out of an aiohttp.FormData -- this IS the render request."""
    out = {}
    for entry in list(getattr(form, "_fields", None) or []):
        try:
            name, value = _name_and_value(entry)
        except Exception as exc:                  # never let this break the tool call
            out[f"<unparsed entry {len(out)}>"] = f"{type(exc).__name__}: {entry!r}"[:140]
            continue
        if isinstance(value, (bytes, bytearray)):
            out[name] = f"<bytes:{len(value)}>"
        else:
            out[name] = value
    if not out:
        out["<empty>"] = repr(form)[:300]
    return out


def stub_api(p):
    async def fake_api(session, method, path, **kw):
        if path == "/api/skins":
            return {"skins": [{"key": k} for k in SKIN_KEYS], "default": SERVER_DEFAULT}
        if path == "/api/render":
            captured.append(read_form(kw.get("data")))
            return {"id": "fake-job-1", "job": {"id": "fake-job-1"}}
        raise AssertionError(f"unexpected API call {method} {path}")

    async def fake_poll(session, job_id):
        return ({"state": "done", "width": 1920, "height": 1080,
                 "message": "完成", "percent": 100}, None)

    async def fake_download(session, job_id):
        f = p.data_dir / "fake.mp4"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(b"\0" * 16)
        return f, 24.4

    p._api = fake_api
    p._poll = fake_poll
    p._download = fake_download


def stub_replay(p, status, payload):
    async def fake(score_id):
        return status, payload

    p._score_replay = fake


def auto_score_fn():
    fn = mod.ManiaRenderPlugin.auto_score
    for cand in (fn, getattr(fn, "__wrapped__", None), getattr(fn, "__func__", None)):
        if cand is not None and inspect.isasyncgenfunction(cand):
            return cand
    raise SystemExit("could not resolve auto_score() to an async-generator function")


async def drive(p, text):
    """Run the deployed handler and collect exactly what it would put in the chat."""
    out = []
    async for item in auto_score_fn()(p, FakeEvent(text)):
        out.append(item)
    return out


def texts(out):
    return [t for kind, t in out if kind == "plain"]


async def resolved_default():
    """The default skin as the PLUGIN itself computes it (stubbed transport, real logic)."""
    p = make_plugin()
    stub_api(p)
    _skins, default = await p._list_skins(None)
    return default


async def main():
    print(f"plugin file      : {PLUGIN}")
    print(f"handler resolved : {auto_score_fn().__qualname__}")
    ref = make_plugin()
    dflt = await resolved_default()
    print(f"config default_skin     : {ref._cfg('default_skin', '')!r}")
    print(f"server default (fake)   : {SERVER_DEFAULT!r}")
    print(f"RESOLVED default skin   : {dflt!r}   <- expected for any message without -s")
    print(f"auto_score_render       : {ref.auto_score_enabled}")
    print()

    # ── 1. explicit -s reaches the render request ────────────────────────────
    print("1. `<link> -s Cho'`  -> requested skin reaches the render request", flush=True)
    p = make_plugin()
    stub_api(p)
    stub_replay(p, "ok", (b"r" * 400, BID))
    captured.clear()
    out = await drive(p, f"{SCORES} -s Cho'")
    check("a render request was posted", len(captured), 1)
    check("form skin", captured[0].get("skin") if captured else None, "Cho'")
    check("form bid from the link", captured[0].get("bid") if captured else None, BID)
    check("replay attached", captured[0].get("osr") if captured else None, "<bytes:400>")
    check("only the 'started' notice was yielded", len(texts(out)), 1)
    print(f"     full form: {captured[0] if captured else None}", flush=True)
    print(f"     yields   : {texts(out)}", flush=True)

    # ── 2. no options -> the configured default ──────────────────────────────
    print("\n2. `<link>`  -> the CONFIGURED default skin reaches the render request",
          flush=True)
    p = make_plugin()
    stub_api(p)
    stub_replay(p, "ok", (b"r" * 400, BID))
    captured.clear()
    out = await drive(p, SCORES)
    check("a render request was posted", len(captured), 1)
    check("form skin is the DEFAULT", captured[0].get("skin") if captured else None, dflt)
    check("form scroll is the default 30", captured[0].get("scroll") if captured else None,
          "30.0")
    print(f"     full form: {captured[0] if captured else None}", flush=True)

    # ── 3. non-mania stays silent ────────────────────────────────────────────
    print("\n3. non-mania `<link>`  -> NO output at all", flush=True)
    p = make_plugin()
    stub_api(p)
    stub_replay(p, "skip", None)
    captured.clear()
    out = await drive(p, SCORES)
    check("zero yields", len(out), 0)
    check("no render request", len(captured), 0)

    # ── 4. an unresolvable skin is visible ───────────────────────────────────
    print("\n4. `<link> -s 不存在的皮肤`  -> a visible message, not silence", flush=True)
    p = make_plugin()
    stub_api(p)
    stub_replay(p, "ok", (b"r" * 400, BID))
    captured.clear()
    out = await drive(p, f"{SCORES} -s nope-not-a-skin")
    msgs = texts(out)
    check("something was said", len(msgs) >= 1, True)
    check("the bad skin is named", any("nope-not-a-skin" in m for m in msgs), True)
    check("no render request was posted", len(captured), 0)
    print(f"     chat text: {msgs[-1] if msgs else None!r}", flush=True)

    # ── 5. an option that cannot be honoured is named ────────────────────────
    print("\n5. `<link> -z 5`  -> the unusable option is named, not swallowed", flush=True)
    p = make_plugin()
    stub_api(p)
    stub_replay(p, "ok", (b"r" * 400, BID))
    captured.clear()
    out = await drive(p, f"{SCORES} -z 5")
    msgs = texts(out)
    check("something was said", len(msgs) >= 1, True)
    check("the unknown flag is named", any("-z" in m for m in msgs), True)
    check("no render request was posted", len(captured), 0)
    print(f"     chat text: {msgs[-1] if msgs else None!r}", flush=True)

    # ── 6. the Chinese bare alias works ──────────────────────────────────────
    print("\n6. `<link> 皮肤 Cho'`  -> the Chinese bare alias works too", flush=True)
    p = make_plugin()
    stub_api(p)
    stub_replay(p, "ok", (b"r" * 400, BID))
    captured.clear()
    await drive(p, f"{SCORES} 皮肤 Cho'")
    check("a render request was posted", len(captured), 1)
    check("form skin", captured[0].get("skin") if captured else None, "Cho'")

    # ── 7. prose is not a skin name ──────────────────────────────────────────
    print("\n7. the real symptom message: prose + `<link>`  -> default skin, still renders",
          flush=True)
    prose = f"小秋这个换boj那个皮肤渲染 {SCORES}"
    p = make_plugin()
    stub_api(p)
    stub_replay(p, "ok", (b"r" * 400, BID))
    captured.clear()
    out = await drive(p, prose)
    check("a render request was posted", len(captured), 1)
    check("form skin is the DEFAULT, not the prose", captured[0].get("skin") if captured else None,
          dflt)
    print(f"     full form: {captured[0] if captured else None}", flush=True)

    print("\n" + "=" * 70, flush=True)
    if failures:
        print(f"FAILURES ({len(failures)}):", flush=True)
        for f in failures:
            print(f"  - {f}", flush=True)
        return 1
    print("ALL AUTO-PATH CHECKS PASSED", flush=True)
    return 0


sys.exit(asyncio.run(main()))
