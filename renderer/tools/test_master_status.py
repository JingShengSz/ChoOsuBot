"""Unit checks for the 主人状态 plugin's formatting — no network, no AstrBot event.

    D:\\LLBot\\bin\\astrbot\\.venv\\Scripts\\python.exe tools\\test_master_status.py

(The plugin's main.py imports ``astrbot``, so this needs the AstrBot venv, not the
system Python.  Nothing here touches the network: only the pure formatter is
exercised, against panel dicts exactly as blog/app/pcstatus.py builds them.)
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MAIN = HERE.parent / "astrbot_plugin_master_status" / "main.py"

spec = importlib.util.spec_from_file_location("master_status_main", MAIN)
module = importlib.util.module_from_spec(spec)
sys.modules["master_status_main"] = module
spec.loader.exec_module(module)
format_status = module.format_status

PASSED = 0
FAILED: list[str] = []


def check(label, condition, detail=""):
    global PASSED
    if condition:
        PASSED += 1
        print(f"  ok   {label}")
    else:
        FAILED.append(f"{label} {detail}")
        print(f"  FAIL {label} {detail}")


# Exactly the shape build_panel() returns, all keys present.
def panel(**over):
    base = {
        "online": True, "flowtrak_running": True,
        # The panel now distinguishes three cases behind "no session", so this
        # helper has to say which one it means.  Derived from flowtrak_running
        # unless the caller says otherwise, because the older tests that pass
        # flowtrak_running=False all mean "FlowTrak is closed" — which is now
        # only ONE of the three ways to have no session.
        "flowtrak_state": "running", "flowtrak_process": True,
        "flowtrak_stale": False, "flowtrak_heartbeat_age": 3,
        "app_name": "DeepSeek Harness", "window_title": "DeepSeek Harness",
        "is_browser": False, "duration_text": "50 秒", "idle": False,
        "render_available": True, "updated_text": "12 秒前", "updated_seconds": 12,
        "stale_after": 120,
        "media_title": None, "media_artist": None, "media_album": None,
        "media_source": None, "media_playing": None, "media_label": None,
    }
    base.update(over)
    if not base["flowtrak_running"] and "flowtrak_state" not in over:
        base["flowtrak_state"] = "stopped"
        base["flowtrak_process"] = False
    return base


print("== offline")
out = format_status(panel(online=False, app_name=None, window_title=None,
                          duration_text=None, idle=None, updated_text="5 分钟前"))
check("says offline", "离线" in out, out)
check("does not claim the machine is off for certain", "不是「一定关机了」" in out, out)
check("no app name leaks", "DeepSeek" not in out, out)
check("includes the last report age", "5 分钟前" in out, out)

print("\n== a normal session")
out = format_status(panel())
check("online", "在线" in out)
check("app", "当前应用：DeepSeek Harness" in out, out)
check("title", "窗口标题：DeepSeek Harness" in out, out)
check("duration", "50 秒" in out, out)
check("idle=否", "是否空闲" in out and "：否" in out, out)
check("render availability is NOT mentioned while it works", "渲染" not in out, out)

print("\n== the browser rule survived the panel")
# build_panel drops the title for a browser; the plugin must not resurrect one.
out = format_status(panel(app_name="Edge", window_title=None, is_browser=True))
check("browser shown by name", "当前应用：Edge" in out, out)
check("no window title line at all", "窗口标题" not in out, out)

print("\n== FlowTrak not running")
out = format_status(panel(flowtrak_running=False, app_name=None, window_title=None,
                          duration_text=None, idle=None))
check("says the tracker is off", "FlowTrak 没开着" in out, out)
check("no invented app", "当前应用" not in out, out)
check("no invented duration", "已持续" not in out, out)
check("no invented idle", "空闲" not in out, out)

print("\n== music")
out = format_status(panel(media_title="Twisted Drop Party", media_artist="t+pazolite",
                          media_playing=True, media_source="Spotify", media_label="正在播放"))
check("says playing", "正在播放：Twisted Drop Party — t+pazolite" in out, out)
out = format_status(panel(media_title="Twisted Drop Party", media_artist="t+pazolite",
                          media_playing=False, media_label="已暂停"))
check("paused is not 正在播放", "正在播放" not in out and "已暂停" in out, out)
out = format_status(panel(media_title="Solo Track", media_artist=None, media_playing=True))
check("artist optional", "正在播放：Solo Track" in out, out)
out = format_status(panel())
check("no music line when there is no music", "播放" not in out, out)

print("\n== music without FlowTrak (independent inputs)")
out = format_status(panel(flowtrak_running=False, app_name=None, window_title=None,
                          duration_text=None, idle=None,
                          media_title="Song", media_artist="A", media_playing=True))
check("music still reported", "正在播放：Song — A" in out, out)
check("and the missing tracker is still stated", "FlowTrak 没开着" in out, out)

print("\n== render service down")
out = format_status(panel(render_available=False))
check("mentioned when down", "渲染服务当前不可用" in out, out)

print("\n== the beatmap osu! has loaded")
# Read by the reporter off osu!'s own window title, which reads
# "osu! - {artist} - {title} [{difficulty}]" while a map is loaded.
out = format_status(panel(flowtrak_running=False, app_name=None, window_title=None,
                          duration_text=None, idle=None,
                          osu_label="正在游玩 osu!", osu_artist="Kurokotei",
                          osu_title="Scattered Faith",
                          osu_difficulty="Catastrophic Trust"))
check("the beatmap is reported", "正在游玩 osu!：Kurokotei — Scattered Faith [Catastrophic Trust]" in out, out)
check("reported even with no FlowTrak session", "FlowTrak 没开着" in out, out)

out = format_status(panel(osu_label="正在游玩 osu!", osu_title="Some Song",
                          osu_artist=None, osu_difficulty="Hard"))
check("a map with no artist renders without a dangling dash",
      "正在游玩 osu!：Some Song [Hard]" in out, out)

out = format_status(panel(osu_label="正在游玩 osu!", osu_title="Some Song",
                          osu_artist="A", osu_difficulty=None))
check("a map with no difficulty renders without empty brackets",
      "正在游玩 osu!：A — Some Song" in out and "[]" not in out, out)

out = format_status(panel(osu_title=None, osu_artist=None, osu_difficulty=None,
                          osu_label=None))
check("no map loaded says nothing about osu!", "osu!" not in out, out)

out = format_status(panel(media_title="Song", media_artist="A", media_playing=True,
                          osu_label="正在游玩 osu!", osu_artist="Kurokotei",
                          osu_title="Scattered Faith", osu_difficulty="Catastrophic Trust"))
check("music and the beatmap are reported side by side",
      "正在播放：Song — A" in out and "Scattered Faith" in out, out)

check("a beatmap is not reported while the PC is offline",
      "osu!" not in format_status({"online": False, "osu_title": "X"}))

print("\n== FlowTrak running vs reporting (the 2026-09-30 false claim)")
# `flowtrak_running` means "there is a session to describe", which needs a live
# heartbeat.  FlowTrak's heartbeat has been measured freezing for 28 minutes
# while the process ran, so this state must not be worded as 未运行.
out = format_status(panel(flowtrak_running=False, flowtrak_state="stale",
                          flowtrak_process=True, flowtrak_heartbeat_age=600,
                          app_name=None, window_title=None, duration_text=None, idle=None))
check("a frozen heartbeat says FlowTrak is OPEN", "FlowTrak 开着" in out, out)
check("...and says it stopped reporting", "停止更新心跳" in out, out)
check("...with the age", "600 秒前" in out, out)
check("...and never claims 未运行", "没开着" not in out and "未运行" not in out, out)

out = format_status(panel(flowtrak_running=False, flowtrak_state="stopped",
                          flowtrak_process=False, app_name=None, window_title=None,
                          duration_text=None, idle=None))
check("a genuinely closed FlowTrak still says so", "FlowTrak 没开着" in out, out)

out = format_status(panel(flowtrak_running=False, flowtrak_state="unknown",
                          flowtrak_process=None, flowtrak_heartbeat_age=None,
                          app_name=None, window_title=None, duration_text=None, idle=None))
check("unknown says unknown, neither way", "无法判断" in out, out)
check("...and does not blame FlowTrak", "没开着" not in out and "未运行" not in out, out)

out = format_status(panel(flowtrak_running=False, app_name=None, window_title=None,
                          duration_text=None, idle=None))
check("an older panel with no state field still answers",
      "FlowTrak" in out and isinstance(out, str), out)
print("\n== degenerate input")
check("an empty dict is offline, not a crash", "离线" in format_status({}))
check("updated_text=None is tolerated", isinstance(format_status(panel(updated_text=None)), str))
check("idle=None is omitted", "是否空闲" not in format_status(panel(idle=None)))
check("a missing app with a live session does not crash",
      isinstance(format_status(panel(app_name=None, window_title=None)), str))

print("\n" + "=" * 60)
print(f"PASSED: {PASSED}    FAILED: {len(FAILED)}")
for failure in FAILED:
    print("  - " + failure)
print("=" * 60)
sys.exit(1 if FAILED else 0)
