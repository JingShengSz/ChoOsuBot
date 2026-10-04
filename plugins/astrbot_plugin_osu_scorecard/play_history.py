"""Persistent observed plays. SQLite indices + JSON payloads; never OAuth data."""
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import time


def played_at(score):
    value = score.get('ended_at') or score.get('created_at') or score.get('play_time')
    try:
        dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        # SB serialises UTC timestamps without a timezone suffix.
        return dt.replace(tzinfo=timezone.utc).timestamp() if dt.tzinfo is None else dt.timestamp()
    except (TypeError, ValueError, OverflowError):
        return None


def recent_plays(rows, now=None):
    now = time.time() if now is None else now
    return sorted((s for s in rows if (t := played_at(s)) is not None
                   and now - 86400 <= t <= now), key=played_at, reverse=True)


class PlayHistory:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self.connect()) as db, db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('''CREATE TABLE IF NOT EXISTS plays (
                server TEXT NOT NULL, qq TEXT NOT NULL, account TEXT NOT NULL,
                username TEXT NOT NULL, ruleset TEXT NOT NULL, beatmap_id INTEGER NOT NULL,
                score_key TEXT NOT NULL, played_at REAL NOT NULL, observed_at REAL NOT NULL,
                payload TEXT NOT NULL,
                PRIMARY KEY(server,qq,account,ruleset,score_key))''')
            db.execute('CREATE INDEX IF NOT EXISTS map_recent ON plays '
                       '(server,qq,account,ruleset,beatmap_id,played_at DESC)')

    def connect(self):
        return sqlite3.connect(self.path, timeout=10)

    def record(self, qq, username, ruleset, server, score):
        bid = (score.get('beatmap') or {}).get('id') or score.get('beatmap_id')
        stamp = played_at(score)
        if not bid or stamp is None:
            return False
        # Explicit allow-list keeps credentials and caller metadata out of the DB.
        fields = ('id','legacy_score_id','user_id','rank','passed','accuracy','statistics',
                  'maximum_statistics','max_combo','mods','pp','total_score','score',
                  'legacy_total_score','legacy_score_id','build_id','type',
                  'ended_at','created_at','ruleset_id','mode','perfect',
                  'beatmap','beatmapset','user','server','sb_acc','rank_global')
        payload = {k: score[k] for k in fields if k in score}
        payload['server'] = server
        body = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        key = str(score.get('id') or hashlib.sha256(body.encode()).hexdigest())
        with closing(self.connect()) as db, db:
            db.execute('INSERT INTO plays VALUES (?,?,?,?,?,?,?,?,?,?) '
                       'ON CONFLICT(server,qq,account,ruleset,score_key) DO UPDATE SET '
                       'payload=excluded.payload,observed_at=excluded.observed_at,username=excluded.username',
                       (server,str(qq),username.casefold(),username,ruleset,int(bid),key,
                        stamp,time.time(),body))
        return True

    def latest(self, qq, username, ruleset, server, beatmap_id):
        with closing(self.connect()) as db:
            row = db.execute('SELECT payload FROM plays WHERE server=? AND qq=? AND account=? '
                             'AND ruleset=? AND beatmap_id=? ORDER BY played_at DESC,score_key DESC LIMIT 1',
                             (server,str(qq),username.casefold(),ruleset,int(beatmap_id))).fetchone()
        return json.loads(row[0]) if row else None
