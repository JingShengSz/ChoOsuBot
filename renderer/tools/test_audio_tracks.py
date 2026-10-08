import shutil
import sys
import tempfile
import threading
import unittest
import urllib.request
import zipfile
from pathlib import Path
from unittest.mock import patch
from http.server import ThreadingHTTPServer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mania_render import fetch, webapp

class AudioTracksTest(unittest.TestCase):
    def test_named_track_and_missing_track(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / 'tracks.osz'
            with zipfile.ZipFile(archive, 'w') as z:
                z.writestr('2TORI - Hiensou.mp3', b'ID3' + b'a' * 4096)
                z.writestr('other.mp3', b'ID3' + b'b' * 8192)
            with patch.object(fetch, 'FILE_MIRRORS', ()), patch.object(fetch, '_fetch_any_osz', side_effect=lambda sid, dest: shutil.copy2(archive, dest)):
                dest = fetch.audio_cache_path(root, '1701660', '2TORI - Hiensou.mp3')
                fetch.fetch_audio('1701660', '2TORI - Hiensou.mp3', dest)
                self.assertEqual(dest.read_bytes(), b'ID3' + b'a' * 4096)
                with self.assertRaises(RuntimeError):
                    fetch.fetch_audio('1701660', 'missing.mp3', root / 'missing.mp3')

    def test_http_decodes_filename_and_isolates_tracks(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(webapp, 'CACHE', Path(directory)):
            root = Path(directory)
            (root / 'audio').mkdir()
            # Legacy cache holds the wrong track and must never be reused.
            (root / 'audio/1701660.mp3').write_bytes(b'ID3' + b'x' * 8192)
            bodies = {'2TORI - Hiensou.mp3': b'ID3' + b'a' * 4096, 'other.mp3': b'ID3' + b'b' * 8192}
            for name, body in bodies.items():
                fetch.audio_cache_path(root, '1701660', name).write_bytes(body)
            server = ThreadingHTTPServer(('127.0.0.1', 0), webapp.Handler)
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                for route in ('audio', 'media'):
                    for name, body in bodies.items():
                        url = f'http://127.0.0.1:{server.server_port}/api/{route}/1701660/{urllib.parse.quote(name)}'
                        self.assertEqual(urllib.request.urlopen(url).read(), body)
            finally:
                server.shutdown()
                server.server_close()

if __name__ == '__main__':
    unittest.main()
