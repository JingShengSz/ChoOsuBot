"""Dump how LLBot stores the .osr message, to learn what `get_msg` returns for a file.

    python tools/llbot_msg_probe.py [keyword]

Copies the live SQLite DB (LLBot holds it open) and prints matching records, so the
plugin's file-download path can be written against the real shape instead of a guess.
"""
from __future__ import annotations

import json
import pathlib
import shutil
import sqlite3
import sys
import tempfile

DB = pathlib.Path(r"D:\LLBot\bin\llbot\data\database\1737493094.v3.db")


def main() -> int:
    keyword = (sys.argv[1] if len(sys.argv) > 1 else ".osr").lower()
    if not DB.is_file():
        print(f"missing {DB}")
        return 1

    with tempfile.TemporaryDirectory() as td:
        copy = pathlib.Path(td) / DB.name
        shutil.copy2(DB, copy)
        for extra in DB.parent.glob(DB.stem + "-wal"):
            shutil.copy2(extra, pathlib.Path(td) / extra.name)

        con = sqlite3.connect(copy)
        con.row_factory = sqlite3.Row
        tables = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")]
        print("tables:", ", ".join(tables))

        for table in tables:
            cols = [r[1] for r in con.execute(f"PRAGMA table_info({table})")]
            text_cols = [c for c in cols if c.lower() in
                         ("msg", "message", "content", "raw", "data", "elements", "json")]
            if not text_cols:
                continue
            where = " OR ".join(f"{c} LIKE ?" for c in text_cols)
            try:
                rows = con.execute(
                    f"SELECT * FROM {table} WHERE {where} ORDER BY rowid DESC LIMIT 3",
                    [f"%{keyword}%"] * len(text_cols),
                ).fetchall()
            except sqlite3.Error:
                continue
            if not rows:
                continue
            print(f"\n=== {table} ({len(rows)} row(s)) ===")
            for row in rows:
                for col in text_cols:
                    value = row[col]
                    if not value or keyword not in str(value).lower():
                        continue
                    text = str(value)
                    try:
                        text = json.dumps(json.loads(text), ensure_ascii=False, indent=1)
                    except Exception:
                        pass
                    print(f"--- column `{col}` ---")
                    print(text[:2600])
        con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
