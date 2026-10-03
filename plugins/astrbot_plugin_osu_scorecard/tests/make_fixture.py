"""One-off: fetch the reference score and freeze it as the offline test fixture.

Run once on a machine that has osu! credentials. After this, self_test.py needs
no network and no credentials — it reads the JSON this writes.

The fixture contains only the public /scores payload and the public /users
profile. No token, no client id, no client secret is ever written.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REFERENCE_SCORE = "6645548845"          # F6A8AF on Noumiso Rigid Girl [4K]
RENDERER = Path(r"D:\Cho Osu Bot\renderer")
CREDS = RENDERER / "data" / "osu_oauth.local.json"
OUT = Path(__file__).resolve().parent / "fixture_score.json"


def main() -> int:
    sys.path.insert(0, str(RENDERER))
    from mania_render.osu_api import OsuApi

    if not CREDS.is_file():
        print(f"凭据文件不存在: {CREDS}")
        return 1
    api = OsuApi.from_file(CREDS)

    score = api.score(REFERENCE_SCORE)
    user_id = (score.get("user") or {}).get("id")
    profile = api.user_by_name(user_id, "mania") if user_id else {}

    payload = {
        "_note": "Frozen osu! API responses for the offline self-test. Public data only.",
        "_score_id": REFERENCE_SCORE,
        "score": score,
        "player": profile,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"已写出 {OUT}  ({OUT.stat().st_size} 字节)")
    print(f"  score.total_score = {score.get('total_score')}")
    print(f"  score.pp          = {score.get('pp')}")
    print(f"  score.rank        = {score.get('rank')}")
    print(f"  player.pp         = {(profile.get('statistics') or {}).get('pp')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
