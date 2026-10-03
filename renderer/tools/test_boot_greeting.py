"""When the bot should say something, and what.

    python tools/test_boot_greeting.py

The whole feature is a decision, so the decision is a pure function and this
tests it directly: `bracket_for`, `greeting_text` and `decide` take a boot time,
a config dict and a clock, and touch no network and no AstrBot.

The cases that matter are the ones that would make the feature annoying:
greeting a boot that is hours old because the plugin just restarted, greeting
twice for the same boot, and greeting on every poll forever.
"""
from __future__ import annotations

import importlib.util
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PASSED = 0
FAILED: list[str] = []


def check(label, condition, detail=""):
    global PASSED
    if condition:
        PASSED += 1
        print(f"  ok   {label}")
    else:
        FAILED.append(label)
        print(f"  FAIL {label} {detail}")


# main.py imports astrbot at module level, which is not installed here.  Load it
# with those imports stubbed so the pure functions can still be exercised -- the
# alternative is not testing the logic at all.
class _Stub:
    def __getattr__(self, name):
        return lambda *a, **k: None


class _FilterStub:
    """`@filter.command(...)` / `@filter.on_astrbot_loaded()` are used as
    decorator FACTORIES, so the attribute has to return something callable that
    returns something callable."""

    #: `filter.EventMessageType.ALL` is read as a VALUE, not called.
    class EventMessageType:
        GROUP_MESSAGE = "group"
        PRIVATE_MESSAGE = "private"
        OTHER_MESSAGE = "other"
        ALL = "all"

    def __getattr__(self, name):
        def factory(*args, **kwargs):
            def decorate(fn):
                return fn
            return decorate
        return factory


def load_module():
    import types
    for name in ("astrbot", "astrbot.api", "astrbot.api.event", "astrbot.api.star",
                 "aiohttp"):
        if name not in sys.modules:
            mod = types.ModuleType(name)
            if name == "aiohttp":
                mod.ClientTimeout = lambda **k: None
                mod.ClientSession = _Stub()
            sys.modules[name] = mod
    sys.modules["astrbot.api"].AstrBotConfig = dict
    sys.modules["astrbot.api"].logger = _Stub()
    sys.modules["astrbot.api.event"].AstrMessageEvent = object
    sys.modules["astrbot.api.event"].MessageChain = _Stub()
    sys.modules["astrbot.api.event"].filter = _FilterStub()
    sys.modules["astrbot.api.star"].Context = object
    sys.modules["astrbot.api.star"].Star = object
    sys.modules["astrbot.api.star"].StarTools = _Stub()

    path = ROOT / "astrbot_plugin_boot_greeting" / "main.py"
    spec = importlib.util.spec_from_file_location("boot_greeting_main", path)
    mod = importlib.util.module_from_spec(spec)
    # Registered BEFORE exec: @dataclass looks its own module up in sys.modules to
    # resolve annotations, and fails with a bare AttributeError if it is absent.
    sys.modules["boot_greeting_main"] = mod
    spec.loader.exec_module(mod)
    return mod


M = load_module()

CFG = {
    "hour_morning": 5, "hour_forenoon": 9, "hour_noon": 12,
    "hour_afternoon": 13, "hour_evening": 18, "hour_night": 23,
    "greet_morning": "早上好，主人～",
    "greet_forenoon": "上午好，主人～",
    "greet_noon": "中午好，主人～吃饭了吗",
    "greet_afternoon": "主人是懒猪，现在才起床……都下午了",
    "greet_evening": "晚上好，主人～",
    "greet_night": "这么晚还开电脑，主人是夜猫子吗",
    "append_time": "0",
    "grace_minutes": 30, "cooldown_hours": 6,
}


def main() -> int:
    print("\n== which line applies at which hour")
    cases = [
        (5, "greet_morning"), (8, "greet_morning"),
        (9, "greet_forenoon"), (11, "greet_forenoon"),
        (12, "greet_noon"), (12, "greet_noon"),
        (13, "greet_afternoon"), (14, "greet_afternoon"), (17, "greet_afternoon"),
        (18, "greet_evening"), (22, "greet_evening"),
        (23, "greet_night"), (0, "greet_night"), (3, "greet_night"),
    ]
    for hour, want in cases:
        got = M.bracket_for(hour, CFG)
        check(f"{hour:02d}:00 -> {want}", got == want, f"got {got}")
    check("the small hours wrap to the night line", M.bracket_for(2, CFG) == "greet_night")
    check("4am is still night (before the 5am boundary)",
          M.bracket_for(4, CFG) == "greet_night")

    print("\n== the user's own example: booting in the afternoon")
    # 13:44 local, which is when this machine actually booted.
    boot = datetime(2026, 10, 1, 13, 44).timestamp()
    text = M.greeting_text(int(boot), CFG)
    check("an afternoon boot gets the 懒猪 line", "懒猪" in text, text)
    check("...exactly the configured wording",
          text == "主人是懒猪，现在才起床……都下午了", text)

    print("\n== the time suffix")
    with_time = M.greeting_text(int(boot), {**CFG, "append_time": "1",
                                           "time_suffix": "（{time} 开机）"})
    check("appends the boot clock", with_time.endswith("（13:44 开机）"), with_time)
    check("keeps the greeting first", with_time.startswith("主人是懒猪"), with_time)
    check("append_time=0 omits it", "13:44" not in M.greeting_text(int(boot), CFG))

    print("\n== which groups get it (a whitelist, not a hint)")
    check("a bare group number is expanded",
          M.parse_targets(["207686550"], "llbot") == ["llbot:GroupMessage:207686550"],
          str(M.parse_targets(["207686550"], "llbot")))
    check("the two configured groups both come back",
          M.parse_targets(["207686550", "972518329"], "llbot") ==
          ["llbot:GroupMessage:207686550", "llbot:GroupMessage:972518329"],
          str(M.parse_targets(["207686550", "972518329"], "llbot")))
    check("a full session string is passed through",
          M.parse_targets(["llbot:GroupMessage:305_207686550"], "llbot") ==
          ["llbot:GroupMessage:305_207686550"])
    check("a comma/space separated string works too",
          M.parse_targets("207686550, 972518329 935961145", "llbot") ==
          ["llbot:GroupMessage:207686550", "llbot:GroupMessage:972518329",
           "llbot:GroupMessage:935961145"],
          str(M.parse_targets("207686550, 972518329 935961145", "llbot")))
    check("Chinese punctuation splits as well",
          len(M.parse_targets("1，2、3；4", "llbot")) == 4,
          str(M.parse_targets("1，2、3；4", "llbot")))
    check("duplicates collapse (same group, two forms)",
          M.parse_targets(["207686550", "llbot:GroupMessage:207686550"], "llbot") ==
          ["llbot:GroupMessage:207686550"],
          str(M.parse_targets(["207686550", "llbot:GroupMessage:207686550"], "llbot")))
    check("empty list -> greet NOBODY (the whitelist is authoritative)",
          M.parse_targets([], "llbot") == [])
    check("None -> greet nobody", M.parse_targets(None, "llbot") == [])
    check("blank entries are ignored",
          M.parse_targets(["", "  ", "207686550"], "llbot") ==
          ["llbot:GroupMessage:207686550"])
    check("the platform name is configurable",
          M.parse_targets(["207686550"], "otherbot") ==
          ["otherbot:GroupMessage:207686550"])
    check("an extra target is appended",
          M.parse_targets(["207686550"], "llbot", "llbot:FriendMessage:42") ==
          ["llbot:GroupMessage:207686550", "llbot:FriendMessage:42"],
          str(M.parse_targets(["207686550"], "llbot", "llbot:FriendMessage:42")))
    check("junk is dropped, not sent to",
          M.parse_targets(["hello", "207686550"], "llbot") ==
          ["llbot:GroupMessage:207686550"],
          str(M.parse_targets(["hello", "207686550"], "llbot")))
    print("\n== decide(): the four ways not to greet")
    now = boot + 120                       # two minutes after boot
    state = {"last_boot_time": int(boot) - 86400, "last_greeted_at": 0}
    d = M.decide(int(boot), state, now, CFG)
    check("a new, recent boot IS greeted", d.greet, d.reason)

    d = M.decide(0, state, now, CFG)
    check("no boot time in the heartbeat -> silent", not d.greet, d.reason)

    d = M.decide(int(boot), {"last_boot_time": int(boot)}, now, CFG)
    check("the same boot twice -> silent", not d.greet, d.reason)

    d = M.decide(int(boot), {}, now, CFG)
    check("the FIRST boot time ever seen is recorded, not greeted",
          not d.greet and "第一次" in d.reason, d.reason)

    old = int(boot) - 4 * 3600
    d = M.decide(old, {"last_boot_time": old - 86400}, now, CFG)
    check("a boot from 4 hours ago is NOT greeted (grace period)",
          not d.greet and "不补说" in d.reason, d.reason)

    d = M.decide(int(boot), {"last_boot_time": int(boot) - 3600,
                             "last_greeted_at": now - 60}, now, CFG)
    check("a greeting inside the cooldown is suppressed",
          not d.greet and "分钟" in d.reason, d.reason)

    d = M.decide(int(boot), {"last_boot_time": int(boot) - 3600,
                             "last_greeted_at": now - 7 * 3600}, now, CFG)
    check("...but allowed again after the cooldown", d.greet, d.reason)

    print("\n== the grace period is configurable, including off")
    old = int(boot) - 6 * 3600
    d = M.decide(old, {"last_boot_time": old - 86400}, now,
                 {**CFG, "grace_minutes": 0})
    check("grace_minutes=0 removes the limit", d.greet, d.reason)
    d = M.decide(old, {"last_boot_time": old - 86400}, now,
                 {**CFG, "grace_minutes": 24 * 60})
    check("a 24h grace accepts it", d.greet, d.reason)

    print("\n== the message it would actually send")
    for hour, label in ((7, "morning"), (13, "afternoon"), (21, "evening"), (2, "night")):
        b = int(datetime(2026, 10, 1, hour, 30).timestamp())
        print(f"  {label:10} {M.greeting_text(b, CFG)}")

    print("\n== a blank line falls back rather than sending nothing")
    blank = {**CFG, "greet_afternoon": ""}
    b = int(datetime(2026, 10, 1, 15, 0).timestamp())
    check("never returns an empty string", M.greeting_text(b, blank).strip() != "",
          repr(M.greeting_text(b, blank)))

    print("\n== a broken config does not crash the poll loop")
    check("no hour keys at all -> night (the last bracket)",
          M.bracket_for(10, {}) == "greet_night", M.bracket_for(10, {}))
    check("non-numeric grace is tolerated",
          M.decide(int(boot), {"last_boot_time": 1}, now,
                   {**CFG, "grace_minutes": "abc"}).greet)
    check("negative grace falls back to the DEFAULT, not to 'unlimited'",
          not M.decide(int(boot) - 10 * 3600, {"last_boot_time": 1}, now,
                       {**CFG, "grace_minutes": -5}).greet)

    print("\n" + "=" * 60)
    print(f"PASSED: {PASSED}    FAILED: {len(FAILED)}")
    for f in FAILED:
        print("  - " + f)
    print("=" * 60)
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
