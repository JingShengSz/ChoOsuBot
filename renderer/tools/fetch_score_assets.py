"""Fetch a score, shared player fields, original background and avatar.

Run from any directory. Secrets are read from a local JSON file, never echoed.
Output is public API data only; no OAuth token is persisted.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mania_render.osu_api import OsuApi
from mania_render.score_assets import fetch_score_assets




def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("score")
    parser.add_argument("--config", type=Path, default=ROOT / "data/osu_oauth.local.json")
    parser.add_argument("--cache", type=Path, default=ROOT / "cache")
    args = parser.parse_args()
    result = fetch_score_assets(args.score, OsuApi.from_file(args.config), args.cache)
    print(json.dumps({"player": result["player"], "score_pp": result["score"].get("pp"),
                      "background_path": result["background_path"], "avatar_path": result["avatar_path"]},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
