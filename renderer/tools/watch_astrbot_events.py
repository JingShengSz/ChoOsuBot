"""Watch AstrBot for private messages and mania-render plugin activity.

    python tools/watch_astrbot_events.py [minutes]

Polls the dashboard log API. Exits as soon as it sees the mania plugin do
something (which is what an `om` command produces), or after the timeout.
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:6186"
PASSWORD = "b9KQeUTbsJZ6Wt29"

CODES = re.compile(r"\x1b\[[0-9;]*m")


def login() -> str:
    req = urllib.request.Request(
        BASE + "/api/auth/login",
        data=json.dumps({"username": "astrbot", "password": PASSWORD}).encode(),
        method="POST",
    )
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())["data"]["token"]


def logs(token: str) -> list[str]:
    req = urllib.request.Request(BASE + "/api/v1/logs/history")
    req.add_header("Authorization", "Bearer " + token)
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read())["data"]["logs"]
    return [CODES.sub("", str(e.get("data", ""))) for e in data]


def main() -> int:
    minutes = float(sys.argv[1]) if len(sys.argv) > 1 else 20.0
    token = login()

    seen: set[str] = set(logs(token))
    print(f"watching for {minutes:g} min; {len(seen)} log lines already present", flush=True)

    deadline = time.time() + minutes * 60
    while time.time() < deadline:
        time.sleep(5)
        try:
            current = logs(token)
        except Exception as exc:  # noqa: BLE001 - keep the watcher alive
            print(f"  poll failed: {exc}", flush=True)
            continue

        for line in current:
            if line in seen:
                continue
            seen.add(line)
            low = line.lower()
            if "mania" in low:
                print(f"HIT {line[:260]}", flush=True)
                return 0
            if "event_bus" in line and "llbot(aiocqhttp)" in line:
                print(f"EVENT {line[:200]}", flush=True)

    print("TIMEOUT: no mania plugin activity seen", flush=True)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
