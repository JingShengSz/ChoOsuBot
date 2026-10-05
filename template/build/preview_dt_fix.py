"""Offline visual check for beatmap 5111622 with DT and the density panel."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "plugins/astrbot_plugin_osu_scorecard"
sys.path.insert(0, str(PLUGIN))

import card
import raster
from render import PilScoreCardRenderer


def main():
    fixture = json.loads((PLUGIN / "tests/fixture_score.json").read_text(encoding="utf-8"))
    score = fixture["score"]
    score["mods"] = [{"acronym": "DT"}]
    score["passed"] = False
    score["rank"] = "F"
    score["beatmap"].update({"id": 5111622, "difficulty_rating": 8.75,
                             "version": "[4K] Harbinger of Death"})
    score["beatmapset"].update({"title": "Executioner", "title_unicode": "Executioner",
                                "artist": "Laur", "artist_unicode": "Laur"})
    data = card.build_card(score, score["beatmap"], score["beatmapset"],
                           fixture["player"], modded_star_rating=11.070799827575684,
                           density_counts=[3, 5, 8, 10, 10, 10, 10, 9, 7, 6, 5, 5, 6,
                                           8, 10, 11, 10, 8, 7, 9, 11, 11, 10, 10, 9, 10],
                           fail_progress=.26)
    output = ROOT / "template/build"
    sheet, placed = raster.render_mod_row(data.mods, ROOT / "template/assets/mods/line_v1")
    sheet.alpha_composite(raster.render_mod_speed_labels(data.mod_speeds, placed))
    sheet.alpha_composite(raster.render_density_panel(
        data.density_counts, data.fail_progress, data.ratio_text, data.star_value))
    sheet_path = output / "preview_dt_mod_overlay.png"
    sheet.save(sheet_path)
    stars = raster.render_star_strip(data.star_value, 600)
    from PIL import Image
    star_sheet = Image.new("RGBA", (1920, 1080))
    star_sheet.alpha_composite(stars, (60, 310))
    star_path = output / "preview_dt_star_overlay.png"
    star_sheet.save(star_path)
    jobs = [{"name": name, "value": value, "font": None, "accent": None}
            for name, value in data.to_layers().items()
            if not name.startswith("mod_") or not name.endswith("_mult")]
    renderer = PilScoreCardRenderer(ROOT / "template/layer_mapping.json",
                                    ROOT / "template/assets", output / "density_work")
    preview = output / "preview_dt_fixed.png"
    renderer.render(jobs, [{"layer": "mod_1", "path": str(sheet_path)},
                           {"layer": "star_strip", "path": str(star_path)}],
                    renderer.signboard_chain(data.grade), preview)
    print(preview)


if __name__ == "__main__":
    main()
