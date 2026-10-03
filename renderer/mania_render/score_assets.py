"""Reusable score assets for score cards and other consumers.

Public data only. OAuth credentials/tokens are never included in the bundle.
All functions are blocking; async callers should use asyncio.to_thread().
"""
from __future__ import annotations
from dataclasses import asdict
import json
from pathlib import Path
import urllib.parse
import urllib.request
from .fetch import get_beatmap_background, looks_like_image
from .osu_api import OsuApi, score_id


def fetch_score_assets(reference: str, api: OsuApi, cache: Path) -> dict:
    """Return public score/player data and local asset paths for any renderer.

    PP is deliberately kept separate: score.pp belongs to this play;
    player.total_pp is the player's current total for score's ruleset.
    Background acquisition uses exactly the public OM fetching interface.
    Exceptions propagate, so consumers do not unknowingly display fake data.
    """
    score = api.score(reference)
    ruleset = {0: "osu", 1: "taiko", 2: "fruits", 3: "mania"}[score["ruleset_id"]]
    player = api.player(score["user_id"], ruleset)
    output = Path(cache) / "scores" / score_id(reference)
    output.mkdir(parents=True, exist_ok=True)
    background = get_beatmap_background(str(score["beatmap"]["id"]), cache)
    avatar = None
    if player.avatar_url:
        url = urllib.parse.urljoin("https://osu.ppy.sh", player.avatar_url)
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme != "https" or not (parsed.hostname == "ppy.sh" or (parsed.hostname or "").endswith(".ppy.sh")):
            raise ValueError("Unexpected avatar host returned by osu! API")
        request = urllib.request.Request(url, headers={"User-Agent": "mania-render/0.1"})
        with urllib.request.urlopen(request, timeout=45) as response:
            content = response.read()
        avatar = output / "avatar.img"
        stage = output / "avatar.part"
        try:
            stage.write_bytes(content)
            if not looks_like_image(stage):
                raise RuntimeError("Avatar response was not an image")
            stage.replace(avatar)
        finally:
            stage.unlink(missing_ok=True)
    result = {"score": score, "player": asdict(player),
              "background_path": str(background.resolve()) if background else None,
              "avatar_path": str(avatar.resolve()) if avatar else None}
    (output / "bundle.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result

