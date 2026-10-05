import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main
from play_history import PlayHistory
from store import Store


class MediaCommandTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.plugin = object.__new__(main.OsuScoreCardPlugin)
        self.plugin.config = {}
        self.plugin.data_dir = Path(self.tmp.name)
        self.plugin.history = PlayHistory(self.plugin.data_dir / 'plays.sqlite3')
        self.plugin.store = Store(self.plugin.data_dir)
        self.event = Mock(message_str='bg', unified_msg_origin='group-a')
        self.event.get_sender_id.return_value = 'different-user'
        self.event.plain_result.side_effect = lambda x: x
        self.event.image_result.side_effect = lambda x: x

    async def test_current_chat_last_map_and_compact_id(self):
        self.plugin.history.remember_chat_map('group-a', 4021083)
        with patch.object(main, 'BeatmapMedia') as factory:
            factory.return_value.background.return_value = Path('bg.png')
            self.assertEqual([x async for x in self.plugin.background(self.event)], ['bg.png'])
            factory.return_value.background.assert_called_with(4021083)
            self.event.message_str = '.bg123'
            self.assertEqual([x async for x in self.plugin.media_compact(self.event)], ['bg.png'])
            factory.return_value.background.assert_called_with(123)

    async def test_unbind_is_scoped_to_server(self):
        self.plugin.store.bind('different-user', 'official', 'mania', 'osu')
        self.plugin.store.bind('different-user', 'private', 'mania', 'sb')
        self.event.message_str = 'unbind -sb'
        result = [x async for x in self.plugin.unbind(self.event)]
        self.assertIn('已解绑', result[0])
        self.assertIsNone(self.plugin.store.username_for('different-user', 'sb'))
        self.assertEqual(self.plugin.store.username_for('different-user', 'osu'), 'official')
