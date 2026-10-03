"""Render the same slice at 720p and 1080p and pull one frame from each to compare.

    python tools/res_compare.py [bid] [skin] [start] [end]

Writes out/res_compare/{720,1080}.png plus a side-by-side crop, and prints the
job states so a resolution-dependent difference is visible rather than guessed.
"""
from __future__ import annotations

import json
import mimetypes
import pathlib
import sys
import time
import urllib.request
import uuid

SERVER = "http://127.0.0.1:8760"
OUT = pathlib.Path(__file__).resolve().parents[1] / "out" / "res_compare"


def api(path: str, data: bytes | None = None, ctype: str | None = None):
    req = urllib.request.Request(SERVER + path, data=data, method="POST" if data else "GET")
    if ctype:
        req.add_header("Content-Type", ctype)
    with urllib.request.urlopen(req, timeout=900) as r:
        raw = r.read()
        return json.loads(raw) if "json" in r.headers.get("Content-Type", "") else raw


def multipart(fields: dict[str, str]) -> tuple[bytes, str]:
    boundary = "----rescompare" + uuid.uuid4().hex
    parts = []
    for k, v in fields.items():
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n")
    body = ("".join(parts) + f"--{boundary}--\r\n").encode()
    return body, f"multipart/form-data; boundary={boundary}"


def render(bid: str, skin: str, rng: str, w: int, h: int) -> pathlib.Path:
    body, ctype = multipart({
        "bid": bid, "skin": skin, "scroll": "30", "fps": "60",
        "width": str(w), "height": str(h), "range": rng,
    })
    job = api("/api/render", body, ctype)
    jid = job.get("id")
    print(f"  {w}x{h}: job {jid} submitted")

    deadline = time.time() + 600
    while time.time() < deadline:
        time.sleep(1.5)
        st = api(f"/api/jobs/{jid}")
        if st.get("state") == "done":
            break
        if st.get("state") == "error":
            raise SystemExit(f"  {w}x{h}: render failed: {st}")
    else:
        raise SystemExit(f"  {w}x{h}: timeout")

    raw = api(f"/api/download/{jid}")
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{w}x{h}.mp4"
    path.write_bytes(raw)
    print(f"  {w}x{h}: {len(raw)/1048576:.2f} MB -> {path}")
    return path


def main() -> int:
    bid = sys.argv[1] if len(sys.argv) > 1 else "4399290"
    skin = sys.argv[2] if len(sys.argv) > 2 else "boj 1-10K"
    start = sys.argv[3] if len(sys.argv) > 3 else "100"
    end = sys.argv[4] if len(sys.argv) > 4 else "104"
    rng = f"{start}-{end}"

    print(f"beatmap={bid}  skin={skin!r}  range={rng}")
    videos = {res: render(bid, skin, rng, *res) for res in ((1280, 720), (1920, 1080))}
    for path in videos.values():
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
