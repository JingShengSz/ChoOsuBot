"""Render completed/failed score-card previews using the real Pillow layout."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "plugins" / "astrbot_plugin_osu_scorecard"
sys.path.insert(0, str(PLUGIN))

import card  # noqa: E402
import heading  # noqa: E402
import raster  # noqa: E402
from render import PilScoreCardRenderer  # noqa: E402


def render(score, player, counts, progress, output):
    beatmap = score.get("beatmap") or {}
    beatmapset = score.get("beatmapset") or {}
    data = card.build_card(score, beatmap, beatmapset, player,
                           density_counts=counts, fail_progress=progress)
    sheet, _ = raster.render_mod_row(data.mods,
                                     ROOT / "template/assets/mods/line_v1")
    sheet.alpha_composite(raster.render_density_panel(
        data.density_counts, data.fail_progress, data.ratio_text,
        data.star_value))
    raster_path = output.with_name(output.stem + "_overlay.png")
    sheet.save(raster_path)
    renderer = PilScoreCardRenderer(ROOT / "template/layer_mapping.json",
                                    ROOT / "template/assets", output.parent / "density_work")
    jobs = [{"name": name, "value": value, "font": None, "accent": None}
            for name, value in data.to_layers().items()]
    renderer.render(jobs, [{"layer": "mod_1", "group": "mods_block",
                            "path": str(raster_path)}],
                    renderer.signboard_chain(data.grade), output)
    print(output)


if __name__ == "__main__":
    fixture = json.loads((PLUGIN / "tests/fixture_score.json").read_text(encoding="utf-8"))
    score = fixture["score"]
    # 26 buckets measured from public beatmap 5493536, then frozen for this
    # offline visual preview. Production always resolves the current .osu file.
    values = [98, 91, 86, 91, 105, 102, 93, 99, 101, 92, 89, 79, 87,
              95, 98, 103, 91, 86, 99, 120, 90, 98, 111, 81, 92, 101]
    output = ROOT / "template/build"
    render(score, fixture["player"], values, None, output / "density_preview_passed.png")
    failed = dict(score)
    failed["passed"] = False
    failed["rank"] = "F"
    failed["statistics"] = {"perfect": 980, "great": 260, "good": 24,
                            "ok": 14, "meh": 4, "miss": 18}
    played = sum(failed["statistics"].values())
    assert played == 1300
    render(failed, fixture["player"], values, .5359528229549215,
           output / "density_preview_failed.png")
    long_score = json.loads(json.dumps(failed))
    long_score["beatmapset"]["title"] = (
        "We Could Get More Machinegun Psystyle! (And More Genre Switches)")
    long_score["beatmapset"]["title_unicode"] = long_score["beatmapset"]["title"]
    long_score["beatmapset"]["artist"] = "かめりあ"
    long_score["beatmapset"]["artist_unicode"] = "かめりあ"
    data = card.build_card(long_score, long_score["beatmap"],
                           long_score["beatmapset"], fixture["player"],
                           density_counts=values, fail_progress=.5359528229549215)
    overlay = heading.render_wrapped_heading(data.title, data.artist)
    assert overlay is not None
    overlay_path = output / "heading_preview_overlay.png"
    overlay.save(overlay_path)
    jobs = [{"name": name, "value": "" if name in ("beatmap_title", "beatmap_artist") else value,
             "font": None, "accent": None} for name, value in data.to_layers().items()]
    renderer = PilScoreCardRenderer(ROOT / "template/layer_mapping.json",
                                    ROOT / "template/assets", output / "density_work")
    renderer.render(jobs, [{"layer": "ui_extras", "group": "beatmap_info",
                            "path": str(overlay_path)},
                           {"layer": "mod_1", "group": "mods_block",
                            "path": str(output / "density_preview_failed_overlay.png")}],
                    renderer.signboard_chain(data.grade), output / "heading_preview_long.png")
