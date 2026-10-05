"""Density sampling, failed-play marker, and Ratio for the score card."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import card
import density
import map_combo
import raster
import sb_api


OSU = """osu file format v14
[HitObjects]
64,192,1000,1,0,0:0:0:0:
192,192,2000,1,0,0:0:0:0:
320,192,3000,128,0,4000:0:0:0:0:
448,192,4000,1,0,0:0:0:0:
"""


class DensityTest(unittest.TestCase):
    def test_buckets_follow_object_times_and_fail_uses_judgement_index(self):
        times = density.hit_object_times(OSU)
        self.assertEqual(times, [1000, 2000, 3000, 4000])
        values = density.buckets(times)
        self.assertEqual(len(values), 26)
        self.assertEqual(sum(values), 4)
        self.assertAlmostEqual(density.fail_progress(times, 2), 1 / 3)
        self.assertEqual(density.decode_times(density.encode_times(times)), times)

    def test_resolver_reuses_density_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            resolver = map_combo.MapComboResolver(tmp)
            with patch('osu_api.fetch_beatmap_file', return_value=OSU) as fetch:
                first, fail = resolver.resolve_density(123, 2)
                second, _ = resolver.resolve_density(123)
            self.assertEqual(fetch.call_count, 1)
            self.assertEqual(first, second)
            self.assertAlmostEqual(fail, 1 / 3)

    def test_ratio_and_played_curve(self):
        score = {'passed': False, 'statistics': {'perfect': 23, 'great': 10}}
        data = card.build_card(score, {}, {}, density_counts=[1] * 26,
                               fail_progress=.5)
        self.assertEqual(data.ratio_text, '2.3')
        self.assertEqual(data.fail_progress, .5)
        panel = raster.render_density_panel(data.density_counts,
                                            data.fail_progress, data.ratio_text)
        self.assertEqual(panel.size, (1920, 1080))
        self.assertIsNotNone(panel.getbbox())
        self.assertGreater(panel.getpixel((60 + 540, 955))[3], 0)
        no_300 = card.build_card({'statistics': {'perfect': 8}}, {}, {})
        self.assertEqual(no_300.ratio_text, '--')

    def test_sb_failed_grade_sets_passed_flag(self):
        score, _, _ = sb_api.score_to_osu({'grade': 'F'})
        self.assertIs(score['passed'], False)


if __name__ == '__main__':
    unittest.main()
