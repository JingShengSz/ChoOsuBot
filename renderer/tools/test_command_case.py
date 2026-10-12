"""Exercise real registered filters, then compact-ID handlers without API calls."""

import importlib.util
from pathlib import Path
import sys
import unittest

from astrbot.core.star.filter.command import CommandFilter
from astrbot.core.star.register.star_handler import (
    get_handler_full_name,
    star_handlers_registry,
)

ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


score = load("case_score", ROOT / "plugins/astrbot_plugin_osu_scorecard/main.py")
mania = load("case_mania", ROOT / "plugins/astrbot_plugin_mania_render/main.py")


class Event:
    is_at_or_wake_command = True

    def __init__(self, text):
        self.message_str = text
        self.extra = {}

    def get_message_str(self):
        return self.message_str

    def set_extra(self, key, value):
        self.extra[key] = value


class CaseTests(unittest.IsolatedAsyncioTestCase):
    def test_all_registered_commands_and_aliases(self):
        count = 0
        for cls in (score.OsuScoreCardPlugin, mania.ManiaRenderPlugin):
            for handler in vars(cls).values():
                if not callable(handler):
                    continue
                md = star_handlers_registry.get_handler_by_full_name(
                    get_handler_full_name(handler)
                )
                if not md:
                    continue
                for f in md.event_filters:
                    if not isinstance(f, CommandFilter):
                        continue
                    for name in f.get_complete_command_names():
                        for spelling in (
                            name,
                            name.upper(),
                            name.title(),
                            name.swapcase(),
                        ):
                            event = Event(spelling + " MiXeD User -SB")
                            self.assertTrue(f.filter(event, None), (name, spelling))
                            self.assertEqual(
                                event.message_str, spelling + " MiXeD User -SB"
                            )
                            self.assertTrue(f.equals(spelling))
                            event.is_at_or_wake_command = False
                            self.assertFalse(f.filter(event, None))
                        self.assertFalse(f.filter(Event(name + "Extra"), None))
                    count += 1
        self.assertEqual(count, 17)

    async def test_compact_ids_and_arguments_preserve_case(self):
        p = object.__new__(score.OsuScoreCardPlugin)

        async def map_card(event, bid, server, target=""):
            yield (bid, server, target)

        async def media(event, kind, bid):
            yield (kind, bid)

        detail_requests=[]
        async def detail(event, bid, *, compact=False, speed_rate=1.0):
            detail_requests.append((bid,compact,speed_rate))
            yield bid

        p._map_card = map_card
        p._media_reply = media
        p._detail_reply = detail
        self.assertEqual(
            [r async for r in p.specific_compact(Event(".S42 MiXeD -SB"))],
            [(42, "sb", "MiXeD")],
        )
        self.assertEqual(
            [r async for r in p.media_compact(Event(".SoNg42"))], [("song", "42")]
        )
        self.assertEqual(
            [r async for r in p.detail_pro_compact(Event(".DtLp42"))], ["42"]
        )
        self.assertEqual(
            [r async for r in p.detail_card_compact(Event(".DtL42 1.2"))], ["42"]
        )
        self.assertEqual(detail_requests,[("42",False,1.0),("42",True,1.2)])
        self.assertEqual(p._args(Event(".P MiXeD User -SB")), "MiXeD User -SB")

    def test_typed_arguments_keep_their_case(self):
        from command_filter import command

        @command("case_argument_test")
        async def handler(self, event, user: str):
            pass

        md = star_handlers_registry.get_handler_by_full_name(
            get_handler_full_name(handler)
        )
        f = next(x for x in md.event_filters if isinstance(x, CommandFilter))
        event = Event("CASE_ARGUMENT_TEST MiXeD")
        self.assertTrue(f.filter(event, None))
        self.assertEqual(event.extra["parsed_params"], {"user": "MiXeD"})


if __name__ == "__main__":
    unittest.main()
