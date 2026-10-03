"""Enable the LLBot -> AstrBot reverse-WebSocket link for the active QQ account.

    python tools/llbot_link.py              # show what would change
    python tools/llbot_link.py --apply      # write it (backs the file up first)

LLBot keeps one `config_<uin>.json` per QQ account and only writes it when you
save from its WebUI -- restarts do not touch it. So the file can be corrected
safely while LLBot runs, but LLBot must be RESTARTED for it to take effect
(the config is read once at startup).
"""
from __future__ import annotations

import argparse
import json
import pathlib
import shutil
import time

LLBOT_DATA = pathlib.Path(r"D:\LLBot\bin\llbot\data")
ASTRBOT_WS_URL = "ws://127.0.0.1:6199/ws"

ENTRY = {
    "type": "ws-reverse",
    "enable": True,
    "url": ASTRBOT_WS_URL,
    "heartInterval": 60000,
    "token": "",
    "reportSelfMessage": False,
    "reportOfflineMessage": False,
    "messageFormat": "array",
    "debug": False,
}


def active_config() -> pathlib.Path:
    """The account LLBot logged into, by newest session file."""
    sessions = sorted(
        LLBOT_DATA.glob("qq-session-*.json"), key=lambda p: p.stat().st_mtime
    )
    if not sessions:
        raise SystemExit("no qq-session-*.json found; cannot tell which account is active")
    uin = sessions[-1].stem.removeprefix("qq-session-")
    cfg = LLBOT_DATA / f"config_{uin}.json"
    if not cfg.is_file():
        raise SystemExit(f"active account {uin} has no {cfg.name}")
    print(f"active account: {uin}  (newest session {sessions[-1].name})")
    return cfg


def describe(connects: list[dict]) -> None:
    for c in connects:
        print(f"  {c['type']:<10} enable={str(c['enable']):<5} url={c.get('url', '')}")


def link(doc: dict) -> list[dict]:
    """Point this account's ws-reverse slot at AstrBot; return the connect list."""
    connects = doc.setdefault("ob11", {}).setdefault("connect", [])

    existing = next(
        (c for c in connects if c["type"] == "ws-reverse" and c.get("url") == ASTRBOT_WS_URL),
        None,
    )
    if existing:
        print(f"\nentry for {ASTRBOT_WS_URL} already present — enabling it in place")
        existing.update(ENTRY)
    else:
        blank = next(
            (c for c in connects if c["type"] == "ws-reverse" and not c.get("url")), None
        )
        if blank:
            print(f"\nfilling the empty ws-reverse slot with {ASTRBOT_WS_URL}")
            blank.update(ENTRY)
        else:
            print(f"\nappending a new ws-reverse entry for {ASTRBOT_WS_URL}")
            connects.append(dict(ENTRY))

    doc["ob11"]["enable"] = True
    return connects


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="actually write the file")
    args = ap.parse_args()

    path = active_config()
    doc = json.loads(path.read_text(encoding="utf-8"))

    print(f"\n{path.name} — ob11.connect before:")
    describe(doc.get("ob11", {}).get("connect", []))

    link(doc)

    print(f"\n{path.name} — ob11.connect after:")
    describe(doc["ob11"]["connect"])

    if not args.apply:
        print("\nDRY RUN — nothing written. Re-run with --apply to write.")
        return 0

    backup = path.with_suffix(f".json.bak_{time.strftime('%Y%m%d%H%M%S')}")
    shutil.copy2(path, backup)
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\nbackup : {backup.name}")
    print(f"written: {path}")
    print("\nNEXT: restart LLBot (its config is read once at startup).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
