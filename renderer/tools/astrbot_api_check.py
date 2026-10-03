"""Ask the running AstrBot dashboard whether it loaded our plugin.

Uses the password that was just set, logs in over its own HTTP API, and reads
`/api/plugins` and `/api/plugins/failed`.

    <python> tools/astrbot_api_check.py [password] [base_url]
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

PASSWORD = sys.argv[1] if len(sys.argv) > 1 else "b9KQeUTbsJZ6Wt29"
BASE = sys.argv[2] if len(sys.argv) > 2 else "http://127.0.0.1:6186"


def call(path: str, payload=None, token: str | None = None) -> tuple[int, object]:
    url = f"{BASE}{path}"
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if data else "GET")
    if data:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read().decode("utf-8", "replace")
            try:
                return resp.status, json.loads(body)
            except Exception:
                return resp.status, body[:400]
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        try:
            return exc.code, json.loads(body)
        except Exception:
            return exc.code, body[:400]
    except Exception as exc:
        return 0, f"{type(exc).__name__}: {exc}"


def main() -> int:
    status, body = call("/api/auth/login", {"username": "astrbot", "password": PASSWORD})
    print(f"POST /api/auth/login -> {status}")
    if status != 200:
        print("  body:", json.dumps(body, ensure_ascii=False)[:300])
        return 1
    token = None
    if isinstance(body, dict):
        data = body.get("data") or body
        token = data.get("token") or data.get("access_token")
    print("  token:", (token[:24] + "...") if token else f"(none; keys={list(body)[:8] if isinstance(body, dict) else '?'})")
    if not token:
        return 1

    for path in ("/api/plugins", "/api/plugins/failed"):
        status, body = call(path, token=token)
        print(f"\nGET {path} -> {status}")
        text = json.dumps(body, ensure_ascii=False)
        print(f"  mentions astrbot_plugin_mania_render : {'mania_render' in text}")
        if isinstance(body, dict):
            data = body.get("data")
            if isinstance(data, list):
                names = [d.get("name") or d.get("display_name") or d.get("root_dir_name") for d in data if isinstance(d, dict)]
                print(f"  {len(names)} entries")
                for n in names:
                    mark = "  <== OURS" if n and "mania_render" in str(n) else ""
                    print(f"    · {n}{mark}")
            elif isinstance(data, dict):
                print("  keys:", list(data)[:12])
                print("  preview:", text[:700])
            else:
                print("  preview:", text[:700])
        else:
            print("  preview:", text[:400])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
