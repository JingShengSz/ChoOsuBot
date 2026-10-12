"""Run from an extracted staging package on an AstrBot host.

The credential file is only consumed by OsuClient. No contents, tokens, request
headers or response bodies are printed. Outputs are selected public test facts.
No messages are sent and the running bot is not restarted.
"""

import asyncio
import importlib
import inspect
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


async def run():
    module = importlib.import_module("astrbot_plugin_osu_tools.main")
    class_names = [
        name
        for name, value in vars(module).items()
        if inspect.isclass(value) and name == "OsuTools"
    ]
    print(json.dumps({"framework_import": class_names == ["OsuTools"]}))
    # Existing installed AstrBot registers the 9 decorated tools in this process.
    from astrbot.core.provider.register import llm_tools

    found = [
        t.name for t in llm_tools.func_list if getattr(t, "name", "").startswith("osu_")
    ]
    print(json.dumps({"registered_tools": sorted(found)}))
    client = module.OsuClient(sys.argv[1])
    catalog = module.Catalog()

    async def query(op, path=None, query=None, body=None):
        operation, url, params, payload = catalog.prepare(op, path, query, body)
        data, _ = await client.query(
            operation["method"],
            url,
            params,
            payload,
            authenticated="OAuth" in operation["auth"],
        )
        return data

    try:
        user = await query("getUser", {"user": "@F6A8AF", "mode": "mania"})
        print(
            json.dumps(
                {
                    "user_query": isinstance(user.get("id"), int),
                    "avatar_present": bool(user.get("avatar_url")),
                    "total_pp_present": user.get("statistics", {}).get("pp")
                    is not None,
                    "team_field_present": "team" in user,
                }
            )
        )
        beatmap = await query("getBeatmap", {"beatmap": 5111622})
        dt = await query(
            "getBeatmapAttributes",
            {"beatmap": 5111622},
            body={"mods": ["DT"], "ruleset": "mania"},
        )
        print(
            json.dumps(
                {
                    "beatmap_id": beatmap.get("id"),
                    "nm_stars": beatmap.get("difficulty_rating"),
                    "dt_stars": dt.get("attributes", {}).get("star_rating"),
                }
            )
        )
        recent = await query(
            "getUserScores",
            {"user": user["id"], "type": "recent"},
            {"mode": "mania", "limit": 1, "include_fails": 1},
        )
        print(
            json.dumps(
                {
                    "recent_query": isinstance(recent, list),
                    "returned_count": len(recent),
                }
            )
        )
        ranks = await query(
            "getRanking",
            {"mode": "mania", "type": "performance"},
            {"cursor": {"page": 2}, "country": "CN"},
        )
        print(
            json.dumps(
                {
                    "rankings_query": isinstance(ranks.get("ranking"), list),
                    "ranking_count": len(ranks.get("ranking", [])),
                }
            )
        )
        search = await query(
            "searchBeatmapset", query={"q": "Executioner", "m": 3, "s": "any"}
        )
        print(
            json.dumps(
                {
                    "search_query": isinstance(search.get("beatmapsets"), list),
                    "returned_count": len(search.get("beatmapsets", [])),
                }
            )
        )
    except module.APIError as exc:
        print(json.dumps({"ok": False, "code": exc.code, "status": exc.status}))
        return 1
    finally:
        await client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
