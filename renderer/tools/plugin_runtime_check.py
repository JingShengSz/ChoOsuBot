"""Import the plugin with the real AstrBot runtime and exercise it against the live API.

Run with AstrBot's own interpreter so `astrbot.*` and `aiohttp` are the versions the bot
actually uses:

    D:\\LLBot\\bin\\astrbot\\.venv\\Scripts\\python.exe tools/plugin_runtime_check.py

It does NOT touch the running bot: no Context, no event bus. It loads `main.py` as a module,
inspects the handlers, and (with --live) drives one real render through the same code path
the command uses.
"""
from __future__ import annotations

import asyncio
import importlib.util
import inspect
import pathlib
import sys
import types

PLUGIN = pathlib.Path(__file__).resolve().parents[1] / "astrbot_plugin_mania_render" / "main.py"


def load_module():
    spec = importlib.util.spec_from_file_location("mania_plugin_under_test", PLUGIN)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class FakeMessageObj:
    def __init__(self, segments=None, raw=None):
        self.message = segments or []
        self.raw_message = raw
        self.message_str = "om 2467450"
        self.group_id = "12345"
        self.sender = types.SimpleNamespace(user_id="1", nickname="tester")
        self.message_id = "1000"


class FakeEvent:
    """Just enough of AstrMessageEvent for the reply/file plumbing."""

    def __init__(self, segments=None, raw=None, bot=None):
        self.message_obj = FakeMessageObj(segments, raw)
        self.message_str = "om 2467450"
        self.unified_msg_origin = "test:GroupMessage:12345"
        self.bot = bot
        self.sent = []

    def get_platform_name(self):
        return "aiocqhttp"

    def plain_result(self, text):
        return ("plain", text)

    def chain_result(self, chain):
        return ("chain", chain)

    async def send(self, result):
        self.sent.append(result)


async def main() -> int:
    live = "--live" in sys.argv
    mod = load_module()
    print("import OK")
    cls = mod.ManiaRenderPlugin
    print(f"class        : {cls.__name__}")
    print(f"base         : {cls.__mro__[1].__name__}")
    for name in ("om", "om_skins", "om_defaults", "render_mania_video", "terminate"):
        fn = getattr(cls, name, None)
        # Handlers that `yield` are async GENERATORS, not coroutines — both are valid here.
        async_fn = bool(fn) and (inspect.isasyncgenfunction(fn) or inspect.iscoroutinefunction(fn))
        kind = "async gen" if fn and inspect.isasyncgenfunction(fn) else (
            "coroutine" if fn and inspect.iscoroutinefunction(fn) else type(fn).__name__)
        print(f"  {name:<20} {'ok ' if async_fn else 'MISSING'} ({kind})")

    # The decorators must have registered the metadata the framework reads.
    print("\nregistered commands / tool")
    for name in ("om", "om_skins", "om_defaults", "render_mania_video"):
        fn = getattr(cls, name)
        meta = getattr(fn, "__astrbot_metadata__", None) or getattr(fn, "__wrapped__", None)
        doc = (fn.__doc__ or "").strip().splitlines()[0] if fn.__doc__ else "(no docstring)"
        print(f"  {name:<20} doc={doc!r}")

    # ── behaviour checks that need no network ──
    print("\nargument handling")
    parse = cls._parse_options
    norm = cls._normalise
    # (input, expected bid, expected skin) — the skin column matters: a key containing a
    # space ("R Skin") used to be truncated to its first word, and asserting only the bid
    # let that through.
    for raw, expect_bid, expect_skin in (
        ("2467450", "2467450", None),
        ("-s R Skin 2467450", "2467450", "R Skin"),
        ("R Skin 2467450", "2467450", "R Skin"),
        ("2467450 -s R Skin -d 30", "2467450", "R Skin"),
        ("2467450 皮肤 Cho'", "2467450", "Cho'"),
        ("2467450 暗度 30", "2467450", None),
        ("2467450 --from 10 --to 20", "2467450", None),
    ):
        opts, err = parse(raw)
        opts2, err2 = norm(opts)
        ok = (
            not err
            and not err2
            and opts2.get("bid") == expect_bid
            and opts2.get("skin") == expect_skin
        )
        shown = opts2 if not (err or err2) else (err or err2)
        print(f"  {'ok ' if ok else 'FAIL'} {raw!r:<32} -> {shown}")

    print("\nreplied-message plumbing")
    ev = FakeEvent(raw=[{"type": "reply", "data": {"id": "998877"}}])
    rid = cls._reply_message_id(ev)
    print(f"  {'ok ' if rid == '998877' else 'FAIL'} reply id from raw segments -> {rid}")
    seg = cls._osr_segment([
        {"type": "text", "data": {"text": "hi"}},
        {"type": "file", "data": {"file": "replay.osr", "url": "http://x/y.osr"}},
    ])
    ok = bool(seg) and seg["data"]["file"] == "replay.osr"
    print(f"  {'ok ' if ok else 'FAIL'} .osr segment wins -> {seg}")
    seg2 = cls._osr_segment([
        {"type": "file", "data": {"file": "notes.txt", "file_id": "abc"}},
        {"type": "file", "data": {"file": "run.osr", "file_id": "def"}},
    ])
    ok2 = bool(seg2) and seg2["data"]["file_id"] == "def"
    print(f"  {'ok ' if ok2 else 'FAIL'} picks the .osr among several files -> "
          f"{seg2 and seg2['data']}")
    print(f"  {'ok ' if cls._osr_segment([{'type': 'image', 'data': {}}]) is None else 'FAIL'} "
          f"no file segment -> None")

    # A file element that carries only a NAME (LLBot's shape) must fall through to the
    # adapter's url actions, keyed on file_id.
    class _Ev:
        def get_group_id(self):
            return ""

        def get_sender_id(self):
            return "1291415477"

    attempts = cls._file_url_attempts(_Ev(), {"file": "a.osr", "file_id": "fid-1"})
    actions = [a for a, _ in attempts]
    ok3 = "get_private_file_url" in actions and all("file_id" in p for _, p in attempts)
    print(f"  {'ok ' if ok3 else 'FAIL'} private file -> url actions -> {actions}")
    ok4 = cls._file_url_attempts(_Ev(), {"file": "just-a-name.osr"}) != []
    print(f"  {'ok ' if ok4 else 'FAIL'} falls back to `file` when file_id is absent")
    ok5 = cls._file_url_attempts(_Ev(), {}) == []
    print(f"  {'ok ' if ok5 else 'FAIL'} no handle at all -> no actions")

    if live:
        print("\nlive render through the plugin code path")
        plugin = cls.__new__(cls)          # skip Star.__init__ (needs a Context)
        plugin.config = {"server": "http://127.0.0.1:8760"}
        plugin.data_dir = pathlib.Path("cache/renders")
        plugin.data_dir.mkdir(parents=True, exist_ok=True)
        plugin._render_lock = asyncio.Lock()
        event = FakeEvent()
        opts = {"bid": "2467450", "range": "60-65"}   # 5 s excerpt keeps it quick
        sent, text = await plugin._render(event, opts, None)
        print(f"  sent={sent}  text={text!r}")
        print(f"  messages on the wire: {len(event.sent)}")
        for m in event.sent:
            print(f"    {m}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
