#!/usr/bin/env python3
"""Verify the DEPLOYED AstrBot plugin's phase-2 fixes by running its own code.

Loads /opt/astrbot/data/plugins/astrbot_plugin_mania_render/main.py (the file AstrBot
actually imports), builds the plugin without AstrBot's Star lifecycle, and exercises:

  A. `_list_skins` precedence          -- offline, fake /api/skins payload
  B. `_resolve_skin` for an explicit -s -- must be unchanged
  C. `_is_send_timeout` classification
  D. a REAL render through `_render()`  -- proves the caption names the configured skin
  E. the exact chat text for a TIMEOUT send   (poll/download stubbed: no second render)
  F. the exact chat text for a DEFINITE send failure
  G. RENDER_NODE_OFFLINE byte-for-byte unchanged

`_render` returns (sent, text); the chat path does `event.plain_result(text)` when
`sent` is False, so the text printed here is what lands in the chat.

Run: /opt/astrbot/.venv/bin/python /tmp/plugin-verify.py [bid] [range]
"""
import asyncio
import importlib.util
import json
import sys
import types
from pathlib import Path

sys.path.insert(0, "/opt/astrbot")

PLUGIN = Path("/opt/astrbot/data/plugins/astrbot_plugin_mania_render/main.py")
CONFIG = Path("/opt/astrbot/data/config/astrbot_plugin_mania_render_config.json")

EXPECTED_OFFLINE = (
    "渲染服务不可达：本机渲染节点似乎离线（隧道未建立）。\n"
    "渲染固定在本机完成，服务端不会回退渲染——请等本机上线后重试。"
)

SKIN_KEYS = ["owc (default)", "Cho'", "R Skin", "boj 1-10K"]
SERVER_DEFAULT = "boj 1-10K"

spec = importlib.util.spec_from_file_location("mania_under_test", PLUGIN)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

cfg = json.loads(CONFIG.read_text(encoding="utf-8-sig"))

failures = []


def check(name, got, want):
    ok = got == want
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: got={got!r} want={want!r}", flush=True)
    if not ok:
        failures.append(name)
    return ok


class FakeEvent:
    """Enough of AstrMessageEvent for _render() to run and record what it sent."""

    def __init__(self, send_error=None):
        self.sent = []
        self.send_error = send_error

    async def send(self, chain):
        if self.send_error is not None:
            raise self.send_error
        self.sent.append(chain)

    def plain_result(self, text):
        return text

    def chain_result(self, comps):
        return comps


def make_plugin(config=None):
    p = mod.ManiaRenderPlugin.__new__(mod.ManiaRenderPlugin)
    p.config = dict(cfg if config is None else config)
    p.data_dir = Path("/tmp/mania-harness-data")
    p.data_dir.mkdir(parents=True, exist_ok=True)
    p._render_lock = asyncio.Lock()
    p._background = set()
    return p


async def fake_api_ok(session, method, path, **kw):
    """Stand-in for the service, dispatching by path like the real client does."""
    if path == "/api/skins":
        return {"skins": [{"key": k} for k in SKIN_KEYS], "default": SERVER_DEFAULT}
    if path == "/api/render":
        return {"id": "fake-job-1", "job": {"id": "fake-job-1"}}
    raise AssertionError(f"unexpected API call {method} {path}")


async def fake_poll(session, job_id):
    return ({"state": "done", "width": 1920, "height": 1080,
             "message": "完成", "percent": 100}, None)


async def fake_download(session, job_id):
    p = Path("/tmp/mania-harness-data/fake.mp4")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"\0" * 16)
    return p, 24.4                      # under video_file_threshold_mb -> video channel


# ── A. precedence ─────────────────────────────────────────────────────────────
async def test_precedence():
    print("\nA. _list_skins precedence (explicit config must beat the server default)",
          flush=True)
    # A1: the user configured R Skin -> R Skin wins over the server's boj 1-10K.
    p = make_plugin({**cfg, "default_skin": "R Skin"})
    p._api = fake_api_ok
    skins, default = await p._list_skins(None)
    check("configured 'R Skin' beats server default", default, "R Skin")
    check("skin list still returned", skins, SKIN_KEYS)

    # A2: nothing configured -> the SERVER default wins (documented "leave it empty").
    p = make_plugin({**cfg, "default_skin": ""})
    p._api = fake_api_ok
    _, default = await p._list_skins(None)
    check("empty config falls back to server default", default, SERVER_DEFAULT)

    # A3: whitespace is not a setting.
    p = make_plugin({**cfg, "default_skin": "   "})
    p._api = fake_api_ok
    _, default = await p._list_skins(None)
    check("whitespace-only config falls back to server default", default, SERVER_DEFAULT)

    # A4: server reports no default -> first skin.
    p = make_plugin({**cfg, "default_skin": ""})
    async def fake_api_nodefault(session, method, path, **kw):
        return {"skins": [{"key": k} for k in SKIN_KEYS]}
    p._api = fake_api_nodefault
    _, default = await p._list_skins(None)
    check("no server default -> first skin", default, SKIN_KEYS[0])


def test_resolve_skin():
    print("\nB. _resolve_skin for an explicit -s request (must be unchanged)", flush=True)
    r = mod.ManiaRenderPlugin._resolve_skin
    check("explicit exact key wins over default", r("boj 1-10K", SKIN_KEYS, "R Skin"),
          "boj 1-10K")
    check("case-insensitive", r("r skin", SKIN_KEYS, "boj 1-10K"), "R Skin")
    check("unique substring", r("Cho", SKIN_KEYS, "R Skin"), "Cho'")
    check("no request -> default passed in", r(None, SKIN_KEYS, "R Skin"), "R Skin")
    try:
        r("nope-not-a-skin", SKIN_KEYS, "R Skin")
        check("unknown skin raises ValueError", "no raise", "ValueError")
    except ValueError:
        check("unknown skin raises ValueError", "ValueError", "ValueError")


def test_timeout_classifier():
    print("\nC. _is_send_timeout classification", flush=True)
    f = mod._is_send_timeout
    check("real adapter text", f(Exception("WebSocket API call timeout")), True)
    check("asyncio.TimeoutError", f(asyncio.TimeoutError()), True)
    check("'timed out'", f(Exception("connection timed out")), True)
    check("Chinese 超时", f(Exception("发送超时")), True)
    check("connection refused is NOT a timeout", f(Exception("Connection refused")), False)
    check("adapter error is NOT a timeout", f(Exception("retcode 1200 发送失败")), False)


# ── D. real render ────────────────────────────────────────────────────────────
async def test_real_render(bid, rng):
    print(f"\nD. REAL render through the deployed plugin's _render() "
          f"(bid={bid} range={rng})", flush=True)
    p = make_plugin()
    print(f"  plugin file : {PLUGIN}", flush=True)
    print(f"  configured  : server={p.server!r} engine={p.engine!r} "
          f"default_skin={p._default_skin()!r} bitrate_kbps={p.bitrate_kbps}", flush=True)
    ev = FakeEvent()
    opts = {"bid": bid}
    if rng:
        opts["range"] = rng
    sent, text = await p._render(ev, opts, None)
    print(f"  _render -> sent={sent}", flush=True)
    print(f"  CAPTION/CHAT TEXT: {text!r}", flush=True)
    if not sent:
        failures.append("real render did not send")
    if "R Skin" not in text:
        failures.append("caption does not name R Skin")
    return sent, text


# ── E/F. exact failure text ───────────────────────────────────────────────────
async def test_send_texts(label, send_error, size_mb=24.4, expect=None):
    print(f"\n{label}", flush=True)
    p = make_plugin()
    p._api = fake_api_ok
    p._poll = fake_poll
    p._download = fake_download
    ev = FakeEvent(send_error=send_error)
    sent, text = await p._render(ev, {"bid": "5415281"}, None)
    print(f"  exception raised by event.send: {send_error!r}", flush=True)
    print(f"  _render -> sent={sent}", flush=True)
    print("  ---- EXACT CHAT TEXT ----", flush=True)
    print(text, flush=True)
    print("  -------------------------", flush=True)
    check(f"{label}: sent is False", sent, False)
    if expect:
        for must in expect.get("contains", []):
            check(f"{label}: contains {must!r}", must in text, True)
        for must_not in expect.get("absent", []):
            check(f"{label}: does NOT contain {must_not!r}", must_not in text, False)
    return sent, text


async def main():
    bid = sys.argv[1] if len(sys.argv) > 1 else "5415281"
    rng = sys.argv[2] if len(sys.argv) > 2 else "0-8"
    texts_only = len(sys.argv) > 3 and sys.argv[3] == "texts-only"

    if not texts_only:
        await test_precedence()
        test_resolve_skin()
        test_timeout_classifier()

        print("\nG. RENDER_NODE_OFFLINE unchanged", flush=True)
        check("offline text byte-for-byte", mod.RENDER_NODE_OFFLINE, EXPECTED_OFFLINE)

        sent, caption = await test_real_render(bid, rng)
        check("caption names R Skin", "R Skin" in caption, True)

    await test_send_texts(
        "E. TIMEOUT send -> ambiguous message",
        Exception("WebSocket API call timeout"),
        expect={"contains": ["超时", "不代表视频没发出去", "很可能已经发到群里了",
                             "R Skin"],
                "absent": ["但发送失败"]})
    await test_send_texts(
        "F. DEFINITE send failure -> failure message",
        Exception("retcode 1200: 上传失败"),
        expect={"contains": ["发送失败", "retcode 1200"],
                "absent": ["很可能已经发到群里了"]})

    print("\n" + "=" * 70, flush=True)
    if failures:
        print(f"FAILURES ({len(failures)}):", flush=True)
        for f in failures:
            print(f"  - {f}", flush=True)
        return 1
    print("ALL CHECKS PASSED", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
