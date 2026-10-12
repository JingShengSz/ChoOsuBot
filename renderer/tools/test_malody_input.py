"""Malody package timelines, real MR layout, exact matching and mux speed checks."""

import hashlib
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mania_render import osz
from mania_render.malody import convert_chart, parse_mr
from mania_render.osu_file import parse_osu
from mania_render.replay_input import resolve_replay
from mania_render.webgl_render import _mux_stream


def mc(version="Easy", offset=100):
    return json.dumps(
        {
            "meta": {
                "mode": 0,
                "mode_ext": {"column": 4},
                "version": version,
                "creator": "Mapper",
                "song": {"title": "Test", "artist": "Artist"},
            },
            "time": [{"beat": [0, 0, 1], "bpm": 120}, {"beat": [4, 0, 1], "bpm": 240}],
            "note": [
                {"beat": [0, 0, 1], "sound": "song.wav", "offset": offset, "type": 1},
                {"beat": [2, 0, 1], "column": 0},
                {"beat": [3, 0, 1], "endbeat": [6, 0, 1], "column": 1},
                {"beat": [5, 0, 1], "column": 3},
            ],
            "effect": [{"beat": [4, 0, 1], "scroll": 2}],
        }
    ).encode()


def package(files):
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        for name, raw in files:
            z.writestr(name, raw)
    return out.getvalue()


def mr(md5, mods=0, version=0x40307, events=None):
    def string(value):
        return struct.pack("<i", len(value.encode())) + value.encode()

    events = (
        events
        if events is not None
        else [
            (1000, 1, 0),
            (1100, 2, 0),
            (1500, 1, 1),
            (2500, 2, 1),
            (2250, 1, 3),
            (2300, 2, 3),
        ]
    )
    return (
        string("mr format head")
        + struct.pack("<I", version)
        + b"".join(string(value) for value in (md5, "Easy", "Test", "Tester"))
        + struct.pack("<9i", 1000000, 3, 3, 0, 0, 0, 0, mods, 0)
        + string("mr data")
        + struct.pack("<IiBiI", version, len(events), 0, 0, 0)
        + b"".join(struct.pack("<iBB", *event) for event in events)
    )


class MalodyInputTests(unittest.TestCase):
    def test_bpm_offset_hold_and_scroll_conversion(self):
        text, meta = convert_chart(mc())
        bm = parse_osu(text)
        self.assertEqual(bm.keys, 4)
        self.assertEqual(
            [(n.start_time, n.end_time, n.column) for n in bm.hit_objects],
            [(900, 900, 0), (1400, 2400, 1), (2150, 2150, 3)],
        )
        self.assertEqual(
            [round(t.bpm) for t in bm.timings if t.is_red_line], [120, 240]
        )
        self.assertEqual(bm.timings[-1].beat_length, -50)
        self.assertEqual(meta["replay_shift_ms"], -100)

    def test_mcz_two_difficulties_and_hash_matching(self):
        first, second = mc(), mc("Hard")
        with (
            tempfile.TemporaryDirectory() as temp,
            patch.object(osz, "ROOT", Path(temp)),
        ):
            maps, _ = osz.import_package(
                package(
                    [
                        ("song/easy.mc", first),
                        ("song/hard.mc", second),
                        ("song/song.wav", b"wave"),
                    ]
                )
            )
            self.assertEqual([m["version"] for m in maps], ["Easy", "Hard"])
            path = Path(temp) / "play.mr"
            path.write_bytes(mr(hashlib.md5(first).hexdigest()))
            replay = resolve_replay(path, Path(temp))
            self.assertEqual(replay["bid"], maps[0]["beatmap_id"])
            self.assertEqual(replay["presses"][0]["time"], 900)
            self.assertEqual(osz.asset(replay["bid"], "song.wav").read_bytes(), b"wave")
            with self.assertRaisesRegex(ValueError, "MD5"):
                resolve_replay(path, Path(temp), maps[1]["beatmap_id"])

    def test_no_audio_rejected_and_bad_difficulty_skipped(self):
        with (
            tempfile.TemporaryDirectory() as temp,
            patch.object(osz, "ROOT", Path(temp)),
        ):
            with self.assertRaisesRegex(ValueError, "song.wav"):
                osz.import_package(package([("easy.mc", mc())]))
            invalid = json.loads(mc())
            invalid["meta"]["mode"] = 5
            maps, warnings = osz.import_package(
                package(
                    [
                        ("bad.mc", json.dumps(invalid)),
                        ("good.mc", mc()),
                        ("song.wav", b"wave"),
                    ]
                )
            )
            self.assertEqual(len(maps), 1)
            self.assertTrue(warnings)

    def test_missing_chart_never_guesses_by_title(self):
        with (
            tempfile.TemporaryDirectory() as temp,
            patch.object(osz, "ROOT", Path(temp)),
        ):
            path = Path(temp) / "play.mr"
            path.write_bytes(mr("a" * 32))
            with self.assertRaisesRegex(ValueError, "对应谱面"):
                resolve_replay(path, Path(temp))

    def test_mr_rate_mirror_judge_and_pe(self):
        for mods, rate in ((16, 1.2), (32, 1.5), (256, 0.8), (0, 1)):
            data = parse_mr(mr("a" * 32, mods=mods | 4))
            self.assertEqual(data["rate"], rate)
            self.assertTrue(data["mirror"])
            self.assertEqual(data["windows"], [52, 92, 126, 150])
        with (
            tempfile.TemporaryDirectory() as temp,
            patch.object(osz, "ROOT", Path(temp)),
        ):
            maps, _ = osz.import_package(
                package([("easy.mc", mc()), ("song.wav", b"wave")])
            )
            path = Path(temp) / "play.mr"
            path.write_bytes(mr(maps[0]["chart_md5"]))
            data = resolve_replay(path, Path(temp), platform="pe")
            self.assertEqual(data["windows"], [61, 101, 135, 159])

    def test_truncated_and_unverified_formats_are_rejected(self):
        for payload in (
            b"no",
            mr("a" * 32)[:-1],
            mr("a" * 32, version=0x60301),
            mr("a" * 32, events=[(1000, 3, 0)]),
        ):
            with self.assertRaises(ValueError):
                parse_mr(payload)

    def test_zip_path_escape_blocked(self):
        with (
            tempfile.TemporaryDirectory() as temp,
            patch.object(osz, "ROOT", Path(temp)),
        ):
            with self.assertRaisesRegex(ValueError, "路径"):
                osz.import_package(package([("../outside.mc", mc())]))

    def test_mux_applies_same_rate_to_audio_video(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            stream = root / "x.h264"
            stream.write_bytes(b"video")
            audio = root / "x.wav"
            audio.write_bytes(b"audio")
            out = root / "x.mp4"
            seen = []

            def run(args, **kwargs):
                seen.extend(args)
                out.write_bytes(b"mp4")
                return type("Result", (), {"returncode": 0})()

            with patch("mania_render.webgl_render.subprocess.run", side_effect=run):
                _mux_stream(
                    "ffmpeg", stream, audio, out, range_s=None, playback_rate=1.2
                )
            self.assertEqual(seen[seen.index("-r") + 1], "72.0")
            self.assertIn("atempo=1.2", seen)


if __name__ == "__main__":
    unittest.main()
