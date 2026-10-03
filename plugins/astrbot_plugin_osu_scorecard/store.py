"""Persistence for the score-card plugin.

Two small JSON files under ``data/plugin_data/<plugin>/`` — never inside the
plugin's own directory, which AstrBot may replace on upgrade:

  bindings.json   "<server>:<QQ>" -> {username, ruleset, server}
  players.json    "<server>:<ruleset>:<username>" -> {fetched_at, data...}   (TTL-cached)

Writes go through a temporary file plus ``os.replace`` so a crash mid-write
cannot leave a half-written file behind.

分服（重要）
------------
官服和私服是两个独立的账号体系：同一个人在官服叫 `Cookiezi`，在 SB 私服可能根本
没有账号，或者同名但是另一个人。所以**绑定必须按服分开存**：

    bind F6A8AF         ->  "osu:12345"  -> {username: F6A8AF, server: osu}
    bind F6A8AF -sb     ->  "sb:12345"   -> {username: F6A8AF, server: sb}

两条记录互不影响。玩家资料缓存同理（键里带 server），否则官服查出来的
总 PP 会被私服查询命中。
"""
from __future__ import annotations

import json
import time
from pathlib import Path

#: Accepted server keys. "osu" is the official server, "sb" is the private one.
SERVERS = ("osu", "sb")
DEFAULT_SERVER = "osu"
SERVER_LABEL = {"osu": "官服", "sb": "SB 私服"}


def norm_server(value) -> str:
    """Anything user- or config-supplied -> a known server key."""
    s = str(value or "").strip().lower()
    if s in ("sb", "ppy.sb", "apisb", "private", "私服"):
        return "sb"
    return DEFAULT_SERVER


class Store:
    def __init__(self, data_dir: Path, cache_minutes: int = 10):
        self.dir = Path(data_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.ttl = max(0, int(cache_minutes)) * 60
        self._bindings_path = self.dir / "bindings.json"
        self._players_path = self.dir / "players.json"
        self._bindings: dict[str, dict] = self._load(self._bindings_path)
        self._players: dict[str, dict] = self._load(self._players_path)
        self._migrate_bindings()

    # ─────────────────────────── generic io ───────────────────────────

    @staticmethod
    def _load(path: Path) -> dict:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    @staticmethod
    def _save(path: Path, data: dict) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        try:
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(path)
        except OSError:
            # Storage trouble must never take a request down; the in-memory copy
            # still serves this session.
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass

    # ─────────────────────────── bindings ───────────────────────────
    #
    # Key history (each step upgrades on read, so live data is never lost):
    #   1. bare `qq -> username` string
    #   2. `qq -> {username, ruleset}`            (mode command)
    #   3. `"<server>:<qq>" -> {username, ruleset, server}`   (SB support)

    def _migrate_bindings(self) -> None:
        """Rewrite any binding whose key is a bare QQ into the new server-scoped key."""
        changed = False
        for key in list(self._bindings):
            if ":" in key:
                continue
            rec = self._as_record(self._bindings.pop(key))
            rec["server"] = DEFAULT_SERVER
            self._bindings[self._bkey(key, DEFAULT_SERVER)] = rec
            changed = True
        if changed:
            self._save(self._bindings_path, self._bindings)

    @staticmethod
    def _bkey(qq, server) -> str:
        return f"{norm_server(server)}:{str(qq)}"

    @staticmethod
    def _as_record(value) -> dict:
        if isinstance(value, dict):
            rec = {
                "username": str(value.get("username") or ""),
                "ruleset": str(value.get("ruleset") or ""),
                "server": norm_server(value.get("server")),
            }
            oauth = value.get("oauth")
            if isinstance(oauth, dict) and oauth.get("refresh_token"):
                rec["oauth"] = {
                    "access_token": str(oauth.get("access_token") or ""),
                    "refresh_token": str(oauth.get("refresh_token") or ""),
                    "expires_at": float(oauth.get("expires_at") or 0),
                    "user_id": oauth.get("user_id"),
                    "scope": str(oauth.get("scope") or "public"),
                    "obtained_at": float(oauth.get("obtained_at") or 0),
                }
            return rec
        return {"username": str(value or ""), "ruleset": "", "server": DEFAULT_SERVER}

    def bind(self, qq: str, username: str, ruleset: str | None = None,
             server: str = DEFAULT_SERVER) -> None:
        server = norm_server(server)
        key = self._bkey(qq, server)
        rec = self._as_record(self._bindings.get(key))
        rec["username"] = str(username).strip()
        rec["server"] = server
        if ruleset:
            rec["ruleset"] = str(ruleset).strip().lower()
        self._bindings[key] = rec
        self._save(self._bindings_path, self._bindings)

    # ─────────────────────────── oauth tokens ───────────────────────────
    #
    # Stored on the binding record, and only ever for the official server (the
    # private one needs no authorization at all).
    #
    # A refresh_token is worth as much as a password: it can read that user's
    # data. It is written to disk because it has to survive a restart, and it
    # must never reach a log line, an exception message or a chat reply.

    def set_oauth(self, qq: str, tokens: dict,
                  server: str = DEFAULT_SERVER) -> bool:
        """Attach a token set to an existing binding. False when not bound."""
        server = norm_server(server)
        key = self._bkey(qq, server)
        if key not in self._bindings:
            return False
        rec = self._as_record(self._bindings[key])
        rec["oauth"] = {
            "access_token": str(tokens.get("access_token") or ""),
            "refresh_token": str(tokens.get("refresh_token") or ""),
            "expires_at": float(tokens.get("expires_at") or 0),
            "user_id": tokens.get("user_id"),
            "scope": str(tokens.get("scope") or "public"),
            "obtained_at": time.time(),
        }
        self._bindings[key] = rec
        self._save(self._bindings_path, self._bindings)
        return True

    def oauth_for(self, qq: str, server: str = DEFAULT_SERVER) -> dict | None:
        """This QQ's token set on this server, or None when never authorized."""
        raw = self._bindings.get(self._bkey(qq, server))
        if raw is None:
            return None
        return self._as_record(raw).get("oauth")

    def clear_oauth(self, qq: str, server: str = DEFAULT_SERVER) -> bool:
        server = norm_server(server)
        key = self._bkey(qq, server)
        if key not in self._bindings:
            return False
        rec = self._as_record(self._bindings[key])
        if "oauth" not in rec:
            return False
        rec.pop("oauth", None)
        self._bindings[key] = rec
        self._save(self._bindings_path, self._bindings)
        return True

    def authorized_count(self) -> int:
        """How many bindings hold a user token. For diagnostics, no secrets."""
        return sum(1 for raw in self._bindings.values()
                   if self._as_record(raw).get("oauth"))

    def unbind(self, qq: str, server: str = DEFAULT_SERVER) -> bool:
        removed = self._bindings.pop(self._bkey(qq, server), None) is not None
        if removed:
            self._save(self._bindings_path, self._bindings)
        return removed

    def username_for(self, qq: str, server: str = DEFAULT_SERVER) -> str | None:
        rec = self._as_record(self._bindings.get(self._bkey(qq, server)))
        return rec["username"] or None

    def ruleset_for(self, qq: str, server: str = DEFAULT_SERVER) -> str | None:
        """The ruleset bound to this QQ on this server, or None (caller uses default)."""
        rec = self._as_record(self._bindings.get(self._bkey(qq, server)))
        return rec["ruleset"] or None

    def binding_for(self, qq: str, server: str = DEFAULT_SERVER) -> dict | None:
        raw = self._bindings.get(self._bkey(qq, server))
        if raw is None:
            return None
        rec = self._as_record(raw)
        return rec if rec["username"] else None

    def set_ruleset(self, qq: str, ruleset: str,
                    server: str = DEFAULT_SERVER) -> bool:
        """Change the ruleset of an existing binding. False when unbound."""
        server = norm_server(server)
        if self._bkey(qq, server) not in self._bindings:
            return False
        self.bind(qq, self.username_for(qq, server) or "", ruleset, server)
        return True

    def servers_for(self, qq: str) -> list[str]:
        """Every server this QQ has a binding on, in SERVERS order."""
        return [s for s in SERVERS if self.binding_for(qq, s)]

    def binding_count(self) -> int:
        return len(self._bindings)

    # ─────────────────────────── player cache ───────────────────────────

    @staticmethod
    def _key(username: str, ruleset: str, server: str = DEFAULT_SERVER) -> str:
        return (f"{norm_server(server)}:{ruleset}:"
                f"{str(username).strip().lower()}")

    def cached_player(self, username: str, ruleset: str,
                      server: str = DEFAULT_SERVER) -> dict | None:
        """The cached profile, or None when missing/expired.

        `cache_minutes = 0` means "never reuse" and must actually disable the cache —
        testing `if self.ttl` alone treated 0 as falsy and served stale data forever.
        """
        entry = self._players.get(self._key(username, ruleset, server))
        if not entry:
            return None
        age = time.time() - float(entry.get("fetched_at", 0))
        if self.ttl <= 0 or age > self.ttl:
            return None
        data = entry.get("data")
        return data if isinstance(data, dict) else None

    def put_player(self, username: str, ruleset: str, data: dict,
                   server: str = DEFAULT_SERVER) -> None:
        self._players[self._key(username, ruleset, server)] = {
            "fetched_at": time.time(),
            "data": data,
        }
        self._save(self._players_path, self._players)

    def forget_player(self, username: str, ruleset: str,
                      server: str = DEFAULT_SERVER) -> bool:
        return self._players.pop(self._key(username, ruleset, server), None) is not None

    def prune_players(self, keep: int = 500) -> int:
        """Drop the oldest entries when the cache grows past `keep`."""
        if len(self._players) <= keep:
            return 0
        ordered = sorted(self._players.items(), key=lambda kv: kv[1].get("fetched_at", 0))
        drop = ordered[: len(ordered) - keep]
        for k, _ in drop:
            self._players.pop(k, None)
        self._save(self._players_path, self._players)
        return len(drop)
