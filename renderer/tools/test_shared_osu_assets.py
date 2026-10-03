"""Offline contract checks for the shared player/background interfaces."""
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mania_render import fetch
from mania_render.osu_api import OsuApi, player_profile, score_id

PNG = b'\x89PNG\r\n\x1a\n' + b'fixture' * 30


class SharedAssetsTests(unittest.TestCase):
    def test_same_set_different_backgrounds_and_cache_reuse(self):
        def download(sid, filename, dest):
            dest.write_bytes(PNG + filename.encode())
        with tempfile.TemporaryDirectory() as tmp, patch.object(fetch, 'fetch_bg', side_effect=download) as call:
            a = fetch.get_background('123', 'easy/bg.png', Path(tmp))
            b = fetch.get_background('123', 'hard/bg.png', Path(tmp))
            self.assertNotEqual(a, b)
            self.assertNotEqual(a.read_bytes(), b.read_bytes())
            self.assertEqual(a, fetch.get_background('123', 'easy/bg.png', Path(tmp)))
            self.assertEqual(call.call_count, 2)

    def test_invalid_response_not_published_and_can_recover(self):
        with tempfile.TemporaryDirectory() as tmp:
            def bad(sid, name, dest):
                dest.write_bytes(b'<html>error</html>')
            with patch.object(fetch, 'fetch_bg', side_effect=bad):
                with self.assertRaises(RuntimeError):
                    fetch.get_background('123', 'bg.png', Path(tmp))
            self.assertEqual(list((Path(tmp) / 'backgrounds').iterdir()), [])
            with patch.object(fetch, 'fetch_bg', side_effect=lambda sid, name, dest: dest.write_bytes(PNG)):
                self.assertTrue(fetch.get_background('123', 'bg.png', Path(tmp)).exists())

    def test_zip_uses_requested_image_not_first_image(self):
        def archive(sid, dest):
            with zipfile.ZipFile(dest, 'w') as z:
                z.writestr('other.png', PNG + b'wrong')
                z.writestr('folder/bg.png', PNG + b'correct')
        with tempfile.TemporaryDirectory() as tmp, patch.object(fetch, '_curl', side_effect=RuntimeError), patch.object(fetch, '_fetch_any_osz', side_effect=archive):
            dest = Path(tmp) / 'image.png'
            fetch.fetch_bg('123', 'folder/bg.png', dest)
            self.assertTrue(dest.read_bytes().endswith(b'correct'))
            with self.assertRaises(RuntimeError):
                fetch.fetch_bg('123', 'absent.png', Path(tmp) / 'absent.png')

    def test_no_declared_background_does_not_download_images(self):
        with tempfile.TemporaryDirectory() as tmp:
            osu = Path(tmp) / 'osu' / '5.osu'
            osu.parent.mkdir()
            osu.write_text('osu file format v14\n[Metadata]\nBeatmapID:5\nBeatmapSetID:123\n')
            with patch.object(fetch, 'fetch_bg') as download:
                self.assertIsNone(fetch.get_beatmap_background('5', Path(tmp)))
                download.assert_not_called()

    def test_player_fields_missing_and_zero_pp(self):
        user = {'id': 1, 'username': 'Test', 'avatar_url': 'https://a.ppy.sh/1?v=2'}
        p = player_profile(user, 'mania')
        self.assertIsNone(p.total_pp)
        self.assertIsNone(p.team)
        user.update(statistics={'pp': 0}, team={'id': 2, 'name': 'Team', 'short_name': 'T'})
        p = player_profile(user, 'mania')
        self.assertEqual(p.total_pp, 0.0)
        self.assertEqual(p.team['short_name'], 'T')
        self.assertEqual(p.avatar_url, user['avatar_url'])

    def test_token_reused_and_mode_specific_player_endpoint(self):
        responses = [
            {'access_token': 'test-token', 'expires_in': 3600},
            {'id': 1, 'username': 'Test', 'statistics': {'pp': 123}},
            {'id': 12, 'pp': 4},
        ]
        def respond(request, timeout):
            return io.BytesIO(json.dumps(responses.pop(0)).encode())
        with patch('urllib.request.urlopen', side_effect=respond) as http:
            api = OsuApi('test-id', 'test-secret')
            self.assertEqual(api.player(1, 'mania').total_pp, 123)
            self.assertEqual(api.score('12')['pp'], 4)
            self.assertEqual(http.call_count, 3)
            self.assertTrue(http.call_args_list[1].args[0].full_url.endswith('/users/1/mania'))

    def test_score_reference_validation(self):
        self.assertEqual(score_id('https://osu.ppy.sh/scores/6645548845'), '6645548845')
        with self.assertRaises(ValueError):
            score_id('https://example.org/scores/6645548845')


if __name__ == '__main__':
    unittest.main()
