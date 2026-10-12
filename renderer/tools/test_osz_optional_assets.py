"""A missing background warns, while a missing audio track blocks that chart."""
import io
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mania_render import osz
from mania_render.fetch import load_beatmap_by_id


def package(*files):
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        for name, body in files:
            archive.writestr(name, body)
    return out.getvalue()


def chart(version, audio="song.mp3", bg="lynessa.jpg"):
    return (f"osu file format v14\n[General]\nAudioFilename: {audio}\nMode: 3\n"
            f"[Metadata]\nTitle: Demo\nVersion: {version}\nCreator: Mapper\n"
            f"[Difficulty]\nCircleSize: 4\n[Events]\n0,0,\"{bg}\",0,0\n")


class OszOptionalAssetsTest(unittest.TestCase):
    def test_missing_background_keeps_selectable_chart_and_warning(self):
        payload = package(("easy.osu", chart("Easy")),
                          ("hard.osu", chart("Hard")),
                          ("song.mp3", b"fake audio"))
        with tempfile.TemporaryDirectory() as tmp, patch.object(osz, "ROOT", Path(tmp)):
            maps, warnings = osz.import_package(payload)
            self.assertEqual(len(maps), 2)
            self.assertTrue(any("lynessa.jpg" in warning for warning in warnings))
            for row in maps:
                self.assertEqual(row["background_filename"], "")
                self.assertEqual(osz.asset(row["beatmap_id"], "song.mp3").read_bytes(), b"fake audio")
                beatmap, audio, background = load_beatmap_by_id(row["beatmap_id"], Path(tmp))
                self.assertEqual(audio.read_bytes(), b"fake audio")
                self.assertIsNone(background)

    def test_missing_audio_skips_only_that_chart(self):
        payload = package(("good.osu", chart("Good")),
                          ("bad.osu", chart("Bad", audio="missing.mp3")),
                          ("song.mp3", b"fake audio"))
        with tempfile.TemporaryDirectory() as tmp, patch.object(osz, "ROOT", Path(tmp)):
            maps, warnings = osz.import_package(payload)
            self.assertEqual([m["version"] for m in maps], ["Good"])
            self.assertTrue(any("missing.mp3" in warning for warning in warnings))

    def test_package_without_any_audio_reports_the_missing_file(self):
        payload = package(("only.osu", chart("Only", audio="missing.mp3")),)
        with tempfile.TemporaryDirectory() as tmp, patch.object(osz, "ROOT", Path(tmp)):
            with self.assertRaisesRegex(ValueError, "missing.mp3"):
                osz.import_package(payload)

    def test_details_can_import_all_charts_without_audio(self):
        payload = package(('easy.osu',chart('Easy',audio='')),('hard.osu',chart('Hard',audio='absent.mp3')))
        with tempfile.TemporaryDirectory() as tmp, patch.object(osz,'ROOT',Path(tmp)):
            maps,warnings=osz.import_package(payload,require_audio=False)
            self.assertEqual([m['version'] for m in maps],['Easy','Hard'])
            for row in maps:
                self.assertEqual(row['audio_filename'],'')
                self.assertIn('[Metadata]',osz.text(row['beatmap_id']))


if __name__ == "__main__":
    unittest.main()
