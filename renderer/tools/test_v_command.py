"""Test command routing with AstrBot's real runtime and isolated fake events."""

import importlib.util
import asyncio
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "mania_command_test", ROOT / "plugins/astrbot_plugin_mania_render/main.py"
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class Event:
    unified_msg_origin = "test:group:1"

    def __init__(self, text):
        self.message_str = text

    def plain_result(self, text):
        return text

    def get_sender_id(self):
        return "1"


class CommandTests(unittest.IsolatedAsyncioTestCase):
    def plugin(self, package=None, replay=None):
        instance = object.__new__(mod.ManiaRenderPlugin)
        instance.captured = []

        async def collect_package(event):
            return package

        async def collect_replay(event):
            return replay

        async def render(event, opts, data):
            instance.captured.append((opts, data))
            return True, "done"

        instance._collect_osz = collect_package
        instance._collect_osr = collect_replay
        instance._render = render
        return instance

    async def test_v_requires_replay_and_cannot_autoplay_numeric_id(self):
        plugin = self.plugin()
        replies = [row async for row in plugin.v(Event("v 2"))]
        self.assertFalse(plugin.captured)
        self.assertIn("请回复", replies[-1])

    async def test_v_osr_and_options(self):
        plugin = self.plugin(replay=b"osr")
        replies = [
            row async for row in plugin.v(Event(".v -v 25 --platform pe"))
        ]
        self.assertTrue(replies)
        self.assertEqual(
            plugin.captured[0],
            ({"_engine": "mrm", "scroll": 25.0, "platform": "pe"}, b"osr"),
        )

    async def test_mcz_om_selects_and_preserves_options(self):
        maps = [
            {"beatmap_id": "local-" + "a" * 32 + "-0", "version": "Easy", "keys": 4},
            {"beatmap_id": "local-" + "a" * 32 + "-1", "version": "Hard", "keys": 4},
        ]
        plugin = self.plugin(package=(maps, []))
        event = Event("om -v 20")
        replies = [row async for row in plugin.om(event)]
        self.assertIn("请选择", replies[-1])
        self.assertFalse(plugin.captured)
        [row async for row in plugin._render_package_choice(event, 2)]
        self.assertEqual(
            plugin.captured[0], ({"scroll": 20.0, "bid": maps[1]["beatmap_id"]}, None)
        )

    async def test_replay_survives_package_choice(self):
        maps = [
            {"beatmap_id": "local-" + "b" * 32 + f"-{i}", "version": str(i), "keys": 4}
            for i in range(2)
        ]
        plugin = self.plugin(package=(maps, []), replay=b"mr")
        event = Event("v")
        [row async for row in plugin.v(event)]
        [row async for row in plugin._render_package_choice(event, 1)]
        self.assertEqual(plugin.captured[0][1], b"mr")
        self.assertEqual(plugin.captured[0][0]['_engine'], 'mrm')

    async def test_om_replay_keeps_existing_engine(self):
        plugin = self.plugin(replay=b'osr')
        [row async for row in plugin.om(Event('OM -s miku'))]
        self.assertNotIn('_engine', plugin.captured[0][0])
        self.assertEqual(plugin.captured[0][0]['skin'], 'miku')

    async def test_v_does_not_silently_accept_om_skin(self):
        plugin = self.plugin(replay=b'osr')
        replies = [row async for row in plugin.v(Event('V -s miku'))]
        self.assertFalse(plugin.captured)
        self.assertIn('Mania-Replay-Master', replies[-1])

    async def test_v_posts_mrm_even_when_om_engine_is_python(self):
        plugin = self.plugin()
        plugin.config = {'engine':'python'}
        plugin._render_lock = asyncio.Lock()
        captured = {}

        async def api(session, method, endpoint, **kwargs):
            captured.update({item[0]['name']: item[2] for item in kwargs['data']._fields})
            return {'id':'test'}

        async def poll(session, job_id):
            return {}, 'stop before delivery'

        async def list_skins(session):
            self.fail('MRM must not depend on OM skins')

        plugin._api = api
        plugin._poll = poll
        plugin._list_skins = list_skins
        await mod.ManiaRenderPlugin._render(plugin, Event('V'), {'_engine':'mrm'}, b'osr')
        self.assertEqual(captured['engine'], 'mrm')
        self.assertEqual((captured['width'],captured['height']), ('540','960'))
        self.assertEqual(captured['scroll'], '20')

    async def test_import_for_v_does_not_autoplay(self):
        plugin = self.plugin(package=([{"beatmap_id": "x"}], []))
        replies = [row async for row in plugin.v(Event("v"))]
        self.assertIn("谱面包已导入", replies[-1])
        self.assertFalse(plugin.captured)

    def test_non_replay_files_never_selected(self):
        self.assertIsNone(
            mod.ManiaRenderPlugin._osr_segment(
                [{"type": "file", "data": {"name": "chart.mcz"}}]
            )
        )
        for name in ('replay.mr','replay.MRV','replay.OSR'):
            self.assertIsNotNone(
                mod.ManiaRenderPlugin._osr_segment(
                    [{"type": "file", "data": {"name": name}}]
                )
            )


if __name__ == "__main__":
    unittest.main()
