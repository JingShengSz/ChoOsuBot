import hashlib
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mania_render.malody_v import parse_mrv
from mania_render.replay_input import resolve_replay
from mania_render import osz
from test_malody_input import mc, package


def varint(value):
    out = bytearray()
    while value > 127:
        out.append((value & 127) | 128)
        value >>= 7
    out.append(value)
    return bytes(out)


def integer(number, value):
    return varint(number << 3) + varint(value)


def blob(number, value):
    return varint(number << 3 | 2) + varint(len(value)) + value


def mrv(md5, events=None, mods=16392):
    events = events or [(1000, 0), (1500, 1), (2250, 3)]
    stats = (
        integer(2, mods)
        + integer(5, 5700)
        + integer(6, len(events))
        + integer(7, len(events))
    )
    out = (
        blob(1, b"Test")
        + blob(4, b"Easy")
        + blob(5, md5.encode())
        + blob(6, b"Tester")
        + blob(8, stats)
    )
    for i, (time, key) in enumerate(events):
        judgement = integer(1, key) + integer(2, 1) + integer(3, 66)
        frame = (
            integer(1, time)
            + blob(3, integer(1, key))
            + blob(3, blob(31, judgement))
            + blob(3, integer(42, i + 1))
        )
        frame += blob(3, varint(43 << 3 | 5) + struct.pack("<f", 100))
        out += blob(9, frame)
        out += blob(9, integer(1, time + 20) + blob(3, integer(2, key)))
    return out


class MRVTests(unittest.TestCase):
    def test_zero_column_recorded_judgements_and_snapshots(self):
        data = parse_mrv(mrv("a" * 32))
        self.assertEqual([p["key"] for p in data["presses"]], [0, 1, 3])
        self.assertEqual(len(data["releases"]), 3)
        self.assertEqual([j["combo"] for j in data["recorded_judgements"]], [1, 2, 3])
        self.assertEqual(data["counts"]["perfect"], 3)
        self.assertTrue(data["holds_to_notes"])
        self.assertTrue(data["constant_scroll"])

    def test_matching_and_audio_shift_applies_to_snapshots(self):
        chart = mc()
        with tempfile.TemporaryDirectory() as tmp, patch.object(osz, "ROOT", Path(tmp)):
            maps, _ = osz.import_package(
                package([("chart.mc", chart), ("song.wav", b"wave")])
            )
            p = Path(tmp) / "play.mrv"
            p.write_bytes(mrv(hashlib.md5(chart).hexdigest()))
            data = resolve_replay(p, Path(tmp))
            self.assertEqual(data["bid"], maps[0]["beatmap_id"])
            self.assertEqual(data["presses"][0]["time"], 900)
            self.assertEqual(data["recorded_judgements"][0]["time"], 900)
            self.assertEqual(data["rate"], 1)

    def test_converted_osu_matches_all_lanes_and_never_title_alone(self):
        from mania_render.malody import convert_chart

        text, _ = convert_chart(mc(offset=0))
        with tempfile.TemporaryDirectory() as tmp, patch.object(osz, "ROOT", Path(tmp)):
            maps, _ = osz.import_package(
                package([("chart.osu", text.encode()), ("song.wav", b"wave")])
            )
            path = Path(tmp) / "play.mrv"
            path.write_bytes(mrv("a" * 32))
            data = resolve_replay(path, Path(tmp))
            self.assertEqual(data["bid"], maps[0]["beatmap_id"])
            self.assertEqual(data["match_method"], "converted_osu_timeline")
            self.assertEqual(data["recorded_judgements"][1]["obj_time"], 1500)
            changed = text.replace("192,192,1500", "320,192,1500")
            # Same title and count, different lane: rejected as another chart.
            wrong, _ = osz.import_package(
                package([("wrong.osu", changed.encode()), ("song.wav", b"wave")])
            )
            self.assertFalse(
                osz.matches_converted_mrv(
                    wrong[0]["beatmap_id"], parse_mrv(path.read_bytes())
                )
            )
            with self.assertRaisesRegex(ValueError, "MD5"):
                resolve_replay(path, Path(tmp), wrong[0]["beatmap_id"])

    def test_ambiguous_converted_charts_require_explicit_choice(self):
        from mania_render.malody import convert_chart

        text, _ = convert_chart(mc(offset=0))
        with tempfile.TemporaryDirectory() as tmp, patch.object(osz, "ROOT", Path(tmp)):
            osz.import_package(
                package(
                    [
                        ("one.osu", text.encode()),
                        ("two.osu", (text + "// changed version\n").encode()),
                        ("song.wav", b"wave"),
                    ]
                )
            )
            with self.assertRaisesRegex(ValueError, "多个"):
                osz.find_converted_mrv(parse_mrv(mrv("a" * 32)))

    def test_bad_data_and_unverified_settings_are_rejected(self):
        for raw in (b"", b"\x00", mrv("a" * 32)[:-1], mrv("a" * 32, mods=1), mrv("b")):
            with (
                self.subTest(size=len(raw)),
                self.assertRaises((ValueError, UnicodeDecodeError)),
            ):
                parse_mrv(raw)

    def test_unknown_fields_are_skipped(self):
        data = parse_mrv(mrv("a" * 32) + integer(100, 42) + blob(101, b"ignored"))
        self.assertEqual(data["press_count"], 3)


if __name__ == "__main__":
    unittest.main()
