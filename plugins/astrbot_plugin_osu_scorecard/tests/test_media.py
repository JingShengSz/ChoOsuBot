import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from beatmap_media import map_media_info
from play_history import PlayHistory


class MediaTests(unittest.TestCase):
    def test_map_filenames_and_preview_start(self):
        info = map_media_info('[General]\nAudioFilename: song.mp3\nPreviewTime: 123456\n[Metadata]\nBeatmapSetID: 123\n[Events]\n0,0,"image, background.jpg",0,0\n')
        self.assertEqual(info['PreviewTime'], '123456')
        self.assertEqual(info['background'], 'image, background.jpg')
        self.assertEqual(info['BeatmapSetID'], '123')

    def test_chat_latest_map_persists_and_is_isolated(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'history.sqlite3'
            history = PlayHistory(path)
            history.remember_chat_map('group-a', 12)
            history.remember_chat_map('group-b', 34)
            history.remember_chat_map('group-a', 56)
            history = PlayHistory(path)
            self.assertEqual(history.chat_map('group-a'), 56)
            self.assertEqual(history.chat_map('group-b'), 34)
            self.assertIsNone(history.chat_map('group-c'))
