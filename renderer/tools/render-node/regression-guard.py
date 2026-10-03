#!/usr/bin/env python
"""Regression guard: prove the Task B edit did not disturb the behaviours that were
already verified -- WITHOUT running a real render.

Deliberately does NOT call `_render` against the live node (that would occupy the user's
Windows render machine). Covers the offline text, skin resolution, the send-timeout
classifier, the automatic-path toggle, and the `om` grammar.

Run: /opt/astrbot/.venv/bin/python /tmp/regression-guard.py
"""
import asyncio
import importlib.util
import json
import sys
from pathlib import Path

sys.path.insert(0, "/opt/astrbot")

PLUGIN = Path("/opt/astrbot/data/plugins/astrbot_plugin_mania_render/main.py")
CONFIG = Path("/opt/astrbot/data/config/astrbot_plugin_mania_render_config.json")

EXPECTED_OFFLINE = (
    "渲染服务不可达：本机渲染节点似乎离线（隧道未建立）。\n"
    "渲染固定在本机完成，服务端不会回退渲染——请等本机上线后重试。"
)
SKIN_KEYS = ["owc (default)", "Cho'", "R Skin", "boj 1-10K"]

spec = importlib.util.spec_from_file_location("mania_regression", PLUGIN)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
cfg = json.loads(CONFIG.read_text(encoding="utf-8-sig"))

failures = []


def check(label, got, want):
    ok = got == want
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}: got={got!r} want={want!r}", flush=True)
    if not ok:
        failures.append(label)


def make_plugin():
    p = mod.ManiaRenderPlugin.__new__(mod.ManiaRenderPlugin)
    p.config = dict(cfg)
    p.data_dir = Path("/tmp/mania-harness-data")
    p.data_dir.mkdir(parents=True, exist_ok=True)
    p._render_lock = asyncio.Lock()
    p._background = set()
    return p


print("A. RENDER_NODE_OFFLINE byte-for-byte", flush=True)
check("offline text unchanged", mod.RENDER_NODE_OFFLINE, EXPECTED_OFFLINE)

print("\nB. _resolve_skin", flush=True)
r = mod.ManiaRenderPlugin._resolve_skin
check("explicit exact key wins", r("boj 1-10K", SKIN_KEYS, "R Skin"), "boj 1-10K")
check("case-insensitive", r("r skin", SKIN_KEYS, "boj 1-10K"), "R Skin")
check("unique substring", r("Cho", SKIN_KEYS, "R Skin"), "Cho'")
check("no request -> default", r(None, SKIN_KEYS, "R Skin"), "R Skin")
try:
    r("nope-not-a-skin", SKIN_KEYS, "R Skin")
    check("unknown skin raises", "no raise", "ValueError")
except ValueError:
    check("unknown skin raises", "ValueError", "ValueError")

print("\nC. _is_send_timeout", flush=True)
f = mod._is_send_timeout
check("adapter timeout text", f(Exception("WebSocket API call timeout")), True)
check("asyncio.TimeoutError", f(asyncio.TimeoutError()), True)
check("connection refused is not a timeout", f(Exception("Connection refused")), False)
check("adapter error is not a timeout", f(Exception("retcode 1200 发送失败")), False)

print("\nD. automatic-path toggle", flush=True)
check("auto_score_render on", make_plugin().auto_score_enabled, True)
p = make_plugin()
p.config["auto_score_render"] = "false"
check("'false' string disables", p.auto_score_enabled, False)
p.config["auto_score_render"] = False
check("False disables", p.auto_score_enabled, False)

print("\nE. the `om` grammar is unchanged (strict=False)", flush=True)
parse = mod.ManiaRenderPlugin._parse_options
check("om <bid>", parse("2467450"), ({"bid": "2467450"}, None))
check("om <bid> -d 30", parse("2467450 -d 30"), ({"bid": "2467450", "bg_dim": "30"}, None))
check("om <bid> R Skin", parse("2467450 R Skin"), ({"bid": "2467450", "skin": "R Skin"}, None))
check("om skin= form", parse("2467450 skin=Cho'"), ({"bid": "2467450", "skin": "Cho'"}, None))
check("om --from/--to", parse("2467450 --from 10 --to 40"),
      ({"bid": "2467450", "from": "10", "to": "40"}, None))
check("om -s with no value errors", parse("2467450 -s"), ({"bid": "2467450"}, "选项 -s 后面少了值"))
check("om bare alias 暗度", parse("2467450 暗度 30"), ({"bid": "2467450", "bg_dim": "30"}, None))

print("\nF. _normalise unchanged", flush=True)
n = mod.ManiaRenderPlugin._normalise
check("bg_dim 30 -> 0.3", n({"bg_dim": "30"}), ({"bg_dim": 0.3}, None))
check("res 720", n({"res": "720"}), ({"width": 1280, "height": 720}, None))
check("bad res", n({"res": "900"}), ({}, "分辨率只支持 720 / 1080"))
check("range", n({"from": "10", "to": "40"}), ({"range": "10-40"}, None))
check("range inverted", n({"from": "40", "to": "10"}), ({}, "--to 要大于 --from"))

print("\n" + "=" * 70, flush=True)
if failures:
    print(f"FAILURES ({len(failures)}):", flush=True)
    for x in failures:
        print(f"  - {x}", flush=True)
    sys.exit(1)
print("NO REGRESSION", flush=True)
