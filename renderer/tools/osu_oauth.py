"""osu! USER-level OAuth helper — the only way to reach the official .osz download.

Why this exists
---------------
`mania_render.fetch` can fall back to the official beatmap download
(`beatmapsets/{id}/download?noVideo=1`, exactly what osu!lazer uses). That endpoint needs a
**user** token: lazer gets one via the authorization_code grant, and `APIRequest.Perform()`
attaches it as `Authorization: Bearer {API.AccessToken}`.

MEASURED, and the reason this file is needed at all: a **client_credentials** token (the
`client_id` + `client_secret` pair) does NOT work. With this project's own credentials,
`/beatmapsets/{id}/download` returned `200 text/html` — the guest page — for all of
  * Bearer + x-api-version
  * Bearer alone
  * no Authorization header at all
i.e. byte-identical responses, so the client token bought nothing.

Usage
-----
1. Register/point a redirect URI on your osu! OAuth application, then:

     python tools/osu_oauth.py authorize --client-id YOUR_CLIENT_ID \
         --redirect-uri http://localhost:8760/oauth/callback

   Open the printed URL, approve, and copy the `code` query parameter out of the redirected
   address bar (if the redirect page fails to load, that is fine — the code is in the URL).

2. Exchange it:

     python tools/osu_oauth.py exchange --client-id YOUR_CLIENT_ID --client-secret <SECRET> \
         --redirect-uri http://localhost:8760/oauth/callback --code <CODE>

   This writes `cache/osu_token.json`. `cache/` is the runtime cache, so keep it out of any
   deployment artifact.

3. Verify it can actually download:

     python tools/osu_oauth.py verify --sid 2164968

The token file is read automatically by `fetch.osu_user_token()`; `$OSU_USER_TOKEN`
overrides it. Nothing here is required for the mirrors to work — this only widens coverage
to sets the mirrors do not carry (unranked / graveyard / delisted).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOKEN_PATH = ROOT / "cache" / "osu_token.json"
TOKEN_URL = "https://osu.ppy.sh/oauth/token"
AUTHORIZE_URL = "https://osu.ppy.sh/oauth/authorize"


def _post(url: str, fields: dict, timeout: int = 60) -> tuple[int, dict]:
    body = urllib.parse.urlencode(fields).encode()
    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except Exception:
            return e.code, {}


def _save(payload: dict) -> None:
    payload = dict(payload)
    payload["obtained_at"] = int(time.time())
    if payload.get("expires_in"):
        payload["expires_at"] = payload["obtained_at"] + int(payload["expires_in"])
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    try:                       # the token is a credential; do not leave it world-readable
        os.chmod(TOKEN_PATH, 0o600)
    except OSError:
        pass


def cmd_authorize(a) -> int:
    q = urllib.parse.urlencode({
        "client_id": a.client_id,
        "redirect_uri": a.redirect_uri,
        "response_type": "code",
        "scope": a.scope,
    })
    print("Open this in a browser, approve, then copy the `code=` value from the address")
    print("the browser is redirected to:\n")
    print(f"  {AUTHORIZE_URL}?{q}\n")
    print("Then run:")
    print(f"  python tools/osu_oauth.py exchange --client-id {a.client_id} "
          f"--redirect-uri {a.redirect_uri} --code <CODE>")
    return 0


def cmd_exchange(a) -> int:
    secret = a.client_secret or os.environ.get("OSU_CLIENT_SECRET", "")
    if not secret:
        print("need --client-secret (or $OSU_CLIENT_SECRET)", file=sys.stderr)
        return 2
    code = a.code.strip()
    if "code=" in code:                      # accept a whole pasted redirect URL
        code = urllib.parse.parse_qs(urllib.parse.urlparse(code).query).get("code", [code])[0]
    st, payload = _post(TOKEN_URL, {
        "client_id": a.client_id,
        "client_secret": secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": a.redirect_uri,
    })
    if st != 200 or not payload.get("access_token"):
        print(f"exchange failed: HTTP {st} {payload}", file=sys.stderr)
        return 1
    _save(payload)
    print(f"OK  saved {TOKEN_PATH}")
    print(f"    scope={payload.get('scope')}  expires_in={payload.get('expires_in')}s")
    return 0


def cmd_refresh(a) -> int:
    secret = a.client_secret or os.environ.get("OSU_CLIENT_SECRET", "")
    data = json.loads(TOKEN_PATH.read_text(encoding="utf-8"))
    rt = data.get("refresh_token")
    if not (secret and rt):
        print("need a stored refresh_token and --client-secret", file=sys.stderr)
        return 2
    st, payload = _post(TOKEN_URL, {
        "client_id": a.client_id, "client_secret": secret,
        "grant_type": "refresh_token", "refresh_token": rt,
        "redirect_uri": a.redirect_uri,
    })
    if st != 200 or not payload.get("access_token"):
        print(f"refresh failed: HTTP {st} {payload}", file=sys.stderr)
        return 1
    _save(payload)
    print(f"OK  refreshed; expires_in={payload.get('expires_in')}s")
    return 0


def cmd_status(a) -> int:
    sys.path.insert(0, str(ROOT))
    from mania_render.fetch import osu_user_token
    tok = osu_user_token()
    src = "none"
    if os.environ.get("OSU_USER_TOKEN", "").strip():
        src = "$OSU_USER_TOKEN"
    elif TOKEN_PATH.is_file():
        src = str(TOKEN_PATH)
    print(f"user token: {'present' if tok else 'ABSENT'}  (source: {src})")
    if TOKEN_PATH.is_file():
        try:
            d = json.loads(TOKEN_PATH.read_text(encoding="utf-8"))
            exp = d.get("expires_at")
            print(f"  scope={d.get('scope')}  expires_at={exp} "
                  f"({time.strftime('%Y-%m-%d %H:%M', time.localtime(exp)) if exp else '?'})")
        except Exception as exc:
            print(f"  unreadable: {exc}")
    if not tok:
        print("\nWithout a user token the official download is skipped and the mirrors are")
        print("used alone — which is fine for ranked/approved/loved sets.")
    return 0


def cmd_verify(a) -> int:
    sys.path.insert(0, str(ROOT))
    from mania_render.fetch import osu_user_token, OSU_OFFICIAL_OSZ
    tok = osu_user_token()
    if not tok:
        print("no user token configured; run `authorize` then `exchange` first", file=sys.stderr)
        return 2
    url = OSU_OFFICIAL_OSZ.format(sid=a.sid)
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {tok}", "x-api-version": "20220705",
        "Accept-Language": "en", "User-Agent": "mania-render/0.1",
    })
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            head = r.read(16)
            ctype = r.headers.get("Content-Type", "")
            clen = r.headers.get("Content-Length", "?")
        print(f"HTTP {r.status}  Content-Type={ctype}  Content-Length={clen}")
        print(f"first bytes: {head!r}")
        ok = head[:2] == b"PK"           # a real .osz is a zip
        print("\n" + ("OK — a zip; the official source will work."
                      if ok else
                      "NOT a zip — this is an HTML page, i.e. the token was not accepted."))
        return 0 if ok else 1
    except Exception as exc:
        print(f"request failed: {exc!r}", file=sys.stderr)
        return 1


def main() -> int:
    p = argparse.ArgumentParser(description="osu! user-level OAuth for the official .osz download")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp, need_code=False):
        sp.add_argument("--client-id", required=True)
        sp.add_argument("--client-secret", default=None,
                        help="omit to read $OSU_CLIENT_SECRET")
        sp.add_argument("--redirect-uri", required=True)
        if need_code:
            sp.add_argument("--code", required=True, help="code from the redirect (a full URL is fine)")

    sp = sub.add_parser("authorize"); common(sp)
    sp.add_argument("--scope", default="public")
    sp.set_defaults(fn=cmd_authorize)

    sp = sub.add_parser("exchange"); common(sp, need_code=True)
    sp.set_defaults(fn=cmd_exchange)

    sp = sub.add_parser("refresh"); common(sp)
    sp.set_defaults(fn=cmd_refresh)

    sp = sub.add_parser("status"); sp.set_defaults(fn=cmd_status)

    sp = sub.add_parser("verify"); sp.add_argument("--sid", required=True)
    sp.set_defaults(fn=cmd_verify)

    a = p.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
