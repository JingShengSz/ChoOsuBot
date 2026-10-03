"""Time a mania-render API job end to end, so it can be compared with the
WebGL page's export throughput on the same beatmap.

    python tools/render_speed.py [bid] [seconds] [width] [height] [skin]

Prints the wall-clock time from POST /api/render to state=done, plus the
resulting chart-seconds-per-wall-second ratio.
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
    with urllib.request.urlopen(req, timeout=1800) as r:
        raw = r.read()
        return json.loads(raw) if "json" in r.headers.get("Content-Type", "") else raw


def multipart(fields: dict[str, str]) -> tuple[bytes, str]:
    boundary = "----renderSpeed" + uuid.uuid4().hex
    parts = [
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n"
        for k, v in fields.items()
    ]
    return ("".join(parts) + f"--{boundary}--\r\n").encode(), f"multipart/form-data; boundary={boundary}"


def main() -> int:
    bid = sys.argv[1] if len(sys.argv) > 1 else "4399290"
    seconds = float(sys.argv[2]) if len(sys.argv) > 2 else 30.0
    w = int(sys.argv[3]) if len(sys.argv) > 3 else 1920
    h = int(sys.argv[4]) if len(sys.argv) > 4 else 1080
    skin = sys.argv[5] if len(sys.argv) > 5 else "boj 1-10K"

    body, ctype = multipart({
        "bid": bid, "skin": skin, "scroll": "30", "fps": "60",
        "width": str(w), "height": str(h), "range": f"0-{seconds}",
    })
    t0 = time.monotonic()
    job = api("/api/render", body, ctype)
    jid = job.get("id")
    print(f"job {jid}: beatmap={bid} skin={skin!r} range=0-{seconds:g}s {w}x{h}")

    marks: list[tuple[float, int, str]] = []
    while True:
        time.sleep(0.5)
        st = api(f"/api/jobs/{jid}")
        state = st.get("state")
        elapsed = time.monotonic() - t0
        pct = int(st.get("percent") or 0)
        if not marks or pct != marks[-1][1]:
            marks.append((elapsed, pct, st.get("message", "")))
        if state == "done":
            break
        if state == "error":
            print("FAILED:", st)
            return 1
        if elapsed > 900:
            print("timeout")
            return 2

    total = time.monotonic() - t0
    for elapsed, pct, msg in marks:
        print(f"  t={elapsed:6.1f}s  {pct:3d}%  {msg}")

    ratio = seconds / total
    print(f"\ntotal {total:.1f}s for {seconds:g}s of video")
    print(f"chart-seconds per wall-second = {ratio:.3f}  (1.0 == real time)")
    print(f"=> a 149s chart needs about {149 / ratio:.0f}s of wall clock")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
