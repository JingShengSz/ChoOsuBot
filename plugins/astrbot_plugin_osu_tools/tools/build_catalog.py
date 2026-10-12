"""Build the reviewed API catalogue from public official sources, never credentials.

Usage: python tools/build_catalog.py /path/to/osu_api_research
Dev dependencies: PyYAML, beautifulsoup4. Runtime does not need either.
"""

import collections
import hashlib
import json
import re
import sys
from pathlib import Path

import yaml
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
DOCS = "https://osu.ppy.sh/docs/index.html"


def build(source):
    spec = yaml.safe_load((source / "openapi.yaml").read_text(encoding="utf-8"))
    html = BeautifulSoup(
        (source / "index.html").read_text(encoding="utf-8"), "html.parser"
    )
    entries = []
    for path, methods in spec["paths"].items():
        for method, op in methods.items():
            if method not in {"get", "post", "put", "delete", "patch"}:
                continue
            suffix = method.upper() + re.sub(r"[/{}]", "-", path.strip("/"))
            heading = html.find(
                "h2",
                id=lambda x, suffix=suffix: (
                    x and x.rstrip("-").endswith(suffix.rstrip("-"))
                ),
            )
            if heading is None:
                raise ValueError(f"Missing HTML permission badges: {method} {path}")
            badges = [
                a.get_text(" ", strip=True)
                for a in heading.find_next_sibling("p").select("a.badge")
            ]
            operation = op["operationId"]
            if operation == "getScores":
                operation = (
                    "getGlobalScores"
                    if path == "/api/v2/scores"
                    else "getPlaylistScores"
                )
            reason = ""
            if "lazer" in badges:
                reason = "lazer 客户端专用"
            elif "requires user" in badges or any(
                b not in {"OAuth", "public"} for b in badges
            ):
                reason = "需要用户授权或额外 scope"
            elif method != "get" and operation != "getBeatmapAttributes":
                reason = "修改账号状态的操作"
            elif path.endswith("/download"):
                reason = "二进制下载，当前 JSON 工具不开放"
            elif "deprecated" in op.get("description", "").lower():
                reason = "已弃用，请使用替代接口"
            parameters = methods.get("parameters", []) + op.get("parameters", [])
            placeholders = re.findall(r"\{(\w+)\}", path)
            # Scribe sometimes emits a phantom path parameter (e.g. team.mode).
            parameters = [
                p for p in parameters if p["in"] != "path" or p["name"] in placeholders
            ]
            clean = []
            for p in parameters:
                clean.append(
                    {
                        "name": p["name"],
                        "in": p["in"],
                        "required": p.get("required", False)
                        and "Optional parameter" not in p.get("description", ""),
                        "type": p.get("schema", {}).get("type", "string"),
                        "description": p.get("description", ""),
                    }
                )
            body = (
                op.get("requestBody", {})
                .get("content", {})
                .get("application/json", {})
                .get("schema", {})
            )
            entries.append(
                {
                    "id": operation,
                    "upstream_operation_id": op["operationId"],
                    "method": method.upper(),
                    "path": path.removeprefix("/api/v2"),
                    "category": op.get("tags", ["Other"])[0],
                    "title": op.get("summary") or path,
                    "description": op.get("summary") or f"{method.upper()} {path}",
                    "auth": badges,
                    "enabled": not reason,
                    "disabled_reason": reason,
                    "parameters": clean,
                    "body_schema": body,
                    "docs": DOCS + "#" + heading["id"],
                }
            )
    # Reviewed against BeatmapsetSearchRequestParams.php; the official spec is TODO.
    search = next(e for e in entries if e["id"] == "searchBeatmapset")
    search["parameters"] += [
        {"name": n, "in": "query", "type": t, "required": False, "description": d}
        for n, t, d in [
            ("q", "string", "搜索词；可带 stars>5 等官方搜索语法"),
            ("m", "integer", "模式：0 osu / 1 taiko / 2 fruits / 3 mania，-1 全部"),
            (
                "s",
                "string",
                "状态：any/leaderboard/ranked/qualified/loved/pending/wip/graveyard",
            ),
            (
                "sort",
                "string",
                "排序，如 ranked_desc / relevance_desc / difficulty_desc",
            ),
            ("g", "integer", "曲风 ID"),
            ("l", "integer", "语言 ID"),
            ("nsfw", "boolean", "是否允许 NSFW 结果"),
            (
                "c",
                "string",
                "通用筛选，用 . 分隔，如 converts.featured_artists；部分需要用户权限",
            ),
            ("e", "string", "video/storyboard，用 . 分隔"),
            ("page", "integer", "页码，推荐使用 cursor_string"),
            ("played", "string", "any/played/unplayed；后两者需要用户身份"),
            ("r", "string", "按自己的评级筛选；需要用户身份及 supporter 权限"),
            ("query", "string", "q 的别名"),
        ]
    ]
    search["parameter_source"] = (
        "https://github.com/ppy/osu-web/blob/master/app/Libraries/Search/BeatmapsetSearchRequestParams.php"
    )
    # Some auto-generated placeholder-only endpoints omit their query schema.
    supplement = {
        "getApiV2BeatmapsetsLookup": [("beatmap_id", "integer", "谱面难度 ID")],
        "getApiV2UsersLookup": [
            ("ids", "array", "最多 50 个用户 ID 或 @用户名"),
            ("ruleset_id", "integer", "0/1/2/3"),
            ("exclude_bots", "boolean", "排除机器人账号"),
        ],
        "getRanking": [
            ("page", "integer", "页码，也可用 cursor 对象"),
            ("sort", "string", "global/team 排行使用 performance/score"),
        ],
    }
    for e in entries:
        for name, typ, desc in supplement.get(e["id"], []):
            if name not in {p["name"] for p in e["parameters"]}:
                e["parameters"].append(
                    {
                        "name": name,
                        "type": typ,
                        "in": "query",
                        "required": False,
                        "description": desc,
                    }
                )
        if e["id"] == "getUser":
            for p in e["parameters"]:
                if p["name"] == "user":
                    p.update(
                        type="string",
                        description="玩家数字 ID 或 @ 前缀用户名；纯数字用户名也加 @。",
                    )
        if e["id"] in supplement:
            e["parameter_source"] = (
                "https://github.com/ppy/osu-web/tree/"
                + json.loads((source / "commit.json").read_text(encoding="utf-8"))[
                    "sha"
                ]
                + "/app/Http/Controllers"
            )
    assert len(entries) == len({e["id"] for e in entries})
    commit = json.loads((source / "commit.json").read_text(encoding="utf-8"))["sha"]
    result = {
        "checked_at": "2026-10-10",
        "upstream_commit": commit,
        "openapi_sha256": hashlib.sha256(
            (source / "openapi.yaml").read_bytes()
        ).hexdigest(),
        "sources": [
            DOCS,
            "https://osu.ppy.sh/docs/openapi.yaml",
            "https://github.com/ppy/osu-web/blob/" + commit + "/routes/web.php",
            "https://github.com/ppy/osu-api/wiki",
        ],
        "operations": entries,
    }
    (ROOT / "api_catalog.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        "# osu! API v2 接口全表",
        "",
        "核对日期：2026-10-10。范围：官方 OpenAPI 快照内的全部 120 个 method/path 组合。",
        "",
        "权限取自官方 HTML 的标签；OpenAPI 中很多 `security: []` 丢失权限信息，不能据此当作匿名接口。",
        "",
        f"源码版本：[{commit[:12]}](https://github.com/ppy/osu-web/tree/{commit})。",
        "",
        "插件仅调用标记为“开放”的查询；其余接口保留文档索引供开发参考。运行时 `osu_api_help(operation_id=...)` 返回参数。",
        "",
    ]
    groups = collections.defaultdict(list)
    for e in entries:
        groups[e["category"]].append(e)
    for group, ops in groups.items():
        lines += [
            f"## {group}",
            "",
            "| operation_id | 方法 / 路径 | 权限 | 插件 |",
            "|---|---|---|---|",
        ]
        for e in ops:
            lines.append(
                f"| [{e['id']}]({e['docs']}) | `{e['method']} {e['path']}` | {', '.join(e['auth']) or '公开，无 OAuth 标签'} | {'开放' if e['enabled'] else e['disabled_reason']} |"
            )
        lines.append("")
    lines += [
        "## 索引校正",
        "",
        "- 官方两个 `getScores` 分别重命名为 `getGlobalScores` 和 `getPlaylistScores`，保留 `upstream_operation_id`。",
        "- team/user/me 尾部 mode 或 ruleset 是可选路径参数；过滤掉规范里不存在于路径的冗余参数。",
        "- `searchBeatmapset` 的参数取自官方搜索参数类，原 OpenAPI 大部分仍是 TODO。",
        "- `POST /beatmaps/{beatmap}/attributes` 是难度查询，无账号修改，因此允许。",
        "- 私有 `_lio` 路由、网站 session 页面和未收录的内部路由不作为稳定工具开放。",
        "",
    ]
    (ROOT / "docs" / "API_REFERENCE.md").write_text("\n".join(lines), encoding="utf-8")
    print(
        f"Catalogue: {len(entries)} operations; {sum(e['enabled'] for e in entries)} query operations enabled"
    )


if __name__ == "__main__":
    build(Path(sys.argv[1]))
