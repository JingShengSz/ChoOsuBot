"""End-to-end check of the API contract the AstrBot plugin relies on.

Mirrors exactly what `astrbot_plugin_mania_render/main.py` does — multipart POST to
/api/render with skin/scroll/fps/width/height/bg_dim, poll /api/jobs/{id}, fetch
/api/download/{id} — but with the standard library so it runs without aiohttp.

    python tools/plugin_api_contract.py [base_url] [bid]
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
import uuid
from pathlib import Path

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8760"
BID = sys.argv[2] if len(sys.argv) > 2 else "2467450"
# A 10-second excerpt keeps the check quick; the plugin offers the same range option.
RANGE_FROM, RANGE_TO = 60, 70


def multipart(fields: dict[str, str]) -> tuple[bytes, str]:
    boundary = "----mania" + uuid.uuid4().hex
    out = bytearray()
    for k, v in fields.items():
        out += f"--{boundary}\r\n".encode()
        out += f'Content-Disposition: form-data; name="{k}"\r\n\r\n'.encode()
        out += f"{v}\r\n".encode()
    out += f"--{boundary}--\r\n".encode()
    return bytes(out), f"multipart/form-data; boundary={boundary}"


def get(path: str) -> bytes:
    with urllib.request.urlopen(f"{BASE}{path}", timeout=60) as r:
        return r.read()


def main() -> int:
    skins = json.loads(get("/api/skins"))
    print(f"GET /api/skins       -> {len(skins['skins'])} skins, default={skins['default']!r}")
    for s in skins["skins"]:
        print(f"     · {s['key']:<16} scroll={s['scroll']}")

    default_skin = skins.get("default") or skins["skins"][0]["key"]
    payload = {
        "bid": BID,
        "skin": default_skin,
        "scroll": "30",
        "fps": "60",          # plugin default
        "width": "1280",      # plugin default
        "height": "720",      # plugin default
        "bg_dim": "0.3",      # user asked for a dimmer background than the 0.6 default
        "range": f"{RANGE_FROM}-{RANGE_TO}",
    }
    body, ctype = multipart(payload)
    req = urllib.request.Request(f"{BASE}/api/render", data=body,
                                 headers={"Content-Type": ctype}, method="POST")
    with urllib.request.urlopen(req, timeout=60) as r:
        job = json.loads(r.read())
    job_id = job.get("id") or job.get("job", {}).get("id")
    print(f"POST /api/render     -> id={job_id}")
    print(f"     echoed back     : {json.dumps({k: v for k, v in job.get('job', {}).items() if k != 'osr_path'}, ensure_ascii=False)}")

    t0 = time.monotonic()
    state = {}
    while True:
        if time.monotonic() - t0 > 900:
            print("TIMEOUT waiting for the job")
            return 1
        time.sleep(3)
        state = json.loads(get(f"/api/jobs/{job_id}"))
        print(f"     [{time.monotonic() - t0:5.1f}s] {state.get('state'):<8} "
              f"{state.get('percent', 0):3d}%  {state.get('message', '')}")
        if state.get("state") in ("done", "error"):
            break

    if state.get("state") != "done":
        print(f"JOB FAILED: {state.get('error')}")
        return 1
    print(f"     finished in {time.monotonic() - t0:.1f}s, "
          f"{state.get('width')}x{state.get('height')}")

    raw = get(f"/api/download/{job_id}")
    out = Path("cache/renders") / f"_contract_{job_id}.mp4"
    out.write_bytes(raw)
    print(f"GET /api/download    -> {len(raw) / 1048576:.2f} MB -> {out}")
    print("CONTRACT OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
