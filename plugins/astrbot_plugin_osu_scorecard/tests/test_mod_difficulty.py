"""DT star rating and speed labels on a failed score card."""
import sys
import unittest
import io
import json
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import card
import raster
from osu_api import OsuApi


class ModDifficultyTest(unittest.TestCase):
    def test_dt_card_uses_calculated_mod_star_rating(self):
        score = {"mods": [{"acronym": "DT"}], "passed": False,
                 "statistics": {"perfect": 356, "great": 348}}
        beatmap = {"difficulty_rating": 8.75, "id": 5111622}
        data = card.build_card(score, beatmap, {}, modded_star_rating=11.07)
        self.assertAlmostEqual(data.star_value, 11.07)

    def test_speed_label_stays_clear_of_density_heading(self):
        sheet, placed = raster.render_mod_row(["DT"], Path("template/assets/mods/line_v1"))
        labels = raster.render_mod_speed_labels([1.5], placed)
        alpha = labels.getchannel("A")
        self.assertIsNotNone(alpha.crop((60, 890, 170, 909)).getbbox())
        self.assertIsNone(alpha.crop((60, 909, 170, 1080)).getbbox())

    def test_official_attributes_request_keeps_exact_mod_settings_and_caches(self):
        api = OsuApi("unused", "unused")
        api._token_value = lambda: "test-token"
        api._opener = Mock()
        api._opener.open.return_value = io.BytesIO(
            b'{"attributes":{"star_rating":11.070799827575684}}')
        mods = [{"acronym": "DT", "settings": {"speed_change": 1.5}}]
        self.assertAlmostEqual(api.beatmap_star_rating(5111622, mods, "mania"), 11.0708, places=4)
        request = api._opener.open.call_args.args[0]
        self.assertEqual(json.loads(request.data), {"mods": mods, "ruleset": "mania"})
        self.assertAlmostEqual(api.beatmap_star_rating(5111622, mods, "mania"), 11.0708, places=4)
        self.assertEqual(api._opener.open.call_count, 1)


if __name__ == "__main__":
    unittest.main()
