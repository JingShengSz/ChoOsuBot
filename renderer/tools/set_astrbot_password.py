"""Set the AstrBot dashboard password, using AstrBot's own hashing helpers.

Runs against the config FILE only — AstrBot must be stopped (login reads the in-memory config,
so the new password takes effect on the next start).

    <astrbot venv>\\Scripts\\python.exe tools/set_astrbot_password.py [new-password]

With no argument it generates a typeable 16-character password that satisfies the policy
(>=8 chars, at least one upper, one lower, one digit).
"""
from __future__ import annotations

import json
import secrets
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(r"D:\LLBot\bin\astrbot")
CONFIG = ROOT / "data" / "cmd_config.json"

# No 0/O/1/l/I — this is meant to be read off a screen and typed by hand.
ALPHABET = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ23456789"


def generate() -> str:
    while True:
        raw = "".join(secrets.choice(ALPHABET) for _ in range(16))
        if any(c.isupper() for c in raw) and any(c.islower() for c in raw) and any(c.isdigit() for c in raw):
            return raw


def main() -> int:
    sys.path.insert(0, str(ROOT))
    from astrbot.core.utils.auth_password import (
        hash_dashboard_password,
        hash_md5_dashboard_password,
        validate_dashboard_password,
        verify_dashboard_password,
    )

    new_password = sys.argv[1] if len(sys.argv) > 1 else generate()
    validate_dashboard_password(new_password)          # raises with the exact policy reason

    if not CONFIG.is_file():
        print(f"config not found: {CONFIG}")
        return 1

    # The file is written with a UTF-8 BOM (utf-8-sig); keep it that way.
    original = CONFIG.read_text(encoding="utf-8-sig")
    backup = CONFIG.with_suffix(f".json.bak_pwreset_{datetime.now():%Y%m%d%H%M%S}")
    backup.write_text(original, encoding="utf-8-sig")
    print(f"backup: {backup.name}")

    cfg = json.loads(original)
    dash = cfg.setdefault("dashboard", {})
    old_user = dash.get("username", "astrbot")

    dash["pbkdf2_password"] = hash_dashboard_password(new_password)
    dash["password"] = hash_md5_dashboard_password(new_password)
    dash["password_storage_upgraded"] = True
    dash["password_change_required"] = False

    CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8-sig")

    # read it back and verify through AstrBot's own verifier
    reread = json.loads(CONFIG.read_text(encoding="utf-8-sig"))
    stored = reread["dashboard"]["pbkdf2_password"]
    ok = verify_dashboard_password(stored, new_password)
    wrong = verify_dashboard_password(stored, new_password + "x")

    print()
    print(f"  username        : {old_user}")
    print(f"  new password    : {new_password}")
    print(f"  stored (pbkdf2) : {stored[:46]}...")
    print(f"  stored (legacy) : {reread['dashboard']['password']}")
    print(f"  verify(correct) : {ok}")
    print(f"  verify(wrong)   : {wrong}")
    print(f"  change_required : {reread['dashboard'].get('password_change_required')}")
    print()
    print("RESULT:", "OK" if ok and not wrong else "FAILED")
    return 0 if ok and not wrong else 1


if __name__ == "__main__":
    raise SystemExit(main())
