"""Render a short slice with every registered skin through the API.

Regression check for skin-loader changes: a bad texture size or a missing sprite
shows up as an API error, and the frame count/size catches silent breakage.

    python tools/skin_matrix.py [bid] [seconds]
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
import uuid

SERVER = "http://127.0.0.1:8760"


def api(path: str, data: bytes | None = None, ctype: str | None = None):
    req = urllib.request.Request(SERVER + path, data=data, method="POST" if data else "GET")
    if ctype:
        req.add_header("Content-Type", ctype)
    with urllib.request.urlopen(req, timeout=900) as r:
        raw = r.read()
        return json.loads(raw) if "json" in r.headers.get("Content-Type", "") else raw


def multipart(fields: dict[str, str]) -> tuple[bytes, str]:
    b = "----skinMatrix" + uuid.uuid4().hex
    parts = [f"--{b}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n" for k, v in fields.items()]
    return ("".join(parts) + f"--{b}--\r\n").encode(), f"multipart/form-data; boundary={b}"


def main() -> int:
    bid = sys.argv[1] if len(sys.argv) > 1 else "4399290"
    seconds = float(sys.argv[2]) if len(sys.argv) > 2 else 3.0

    skins = api("/api/skins")
    if isinstance(skins, (bytes, bytearray)):
        skins = json.loads(skins.decode())
    print(f"keys available: {[s['key'] for s in skins['skins']]}\n")

    failures = 0
    for entry in skins["skins"]:
        key = entry["key"]
        body, ctype = multipart({
            "bid": bid, "skin": key, "scroll": "30", "fps": "60",
            "width": "1920", "height": "1080", "range": f"0-{seconds:g}",
        })
        t0 = time.monotonic()
        try:
            job = api("/api/render", body, ctype)
            jid = job.get("id")
            deadline = time.time() + 600
            while time.time() < deadline:
                time.sleep(1.0)
                st = api(f"/api/jobs/{jid}")
                if st.get("state") == "done":
                    break
                if st.get("state") == "error":
                    raise RuntimeError(st.get("error") or st.get("message"))
            else:
                raise RuntimeError("timeout")
            raw = api(f"/api/download/{jid}")
            dt = time.monotonic() - t0
            print(f"  OK    {key:<16} {len(raw)/1048576:6.2f} MB   {dt:5.1f}s")
        except Exception as exc:  # noqa: BLE001 - report and continue
            failures += 1
            print(f"  FAIL  {key:<16} {exc}")

    print(f"\n{len(skins['skins']) - failures}/{len(skins['skins'])} skins rendered")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
