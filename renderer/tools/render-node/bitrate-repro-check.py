#!/usr/bin/env python3
"""Repeat the boj@2000 case to decide whether the 4.78 Mbps overshoot is reproducible.

R2 (5415281 / boj 1-10K / 2000 kbps) came out at 4.78 Mbps while the SAME settings on
R Skin came out at 2.22 Mbps. If that is content-driven VBR overshoot it will reproduce;
if it was a one-off (encoder session/GPU state) it will not. The answer decides whether a
rate-control mode has to be forced.
"""
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:8760"
OUT = Path("/tmp/mania-ab")
OUT.mkdir(parents=True, exist_ok=True)

CASES = [
    ("C1-boj-2000-repeat", "5415281", "boj 1-10K", 2000),
    ("C2-boj-2000-repeat", "5415281", "boj 1-10K", 2000),
    ("C3-rskin-2000-repeat", "5415281", "R Skin", 2000),
    ("C4-boj-2000-repeat", "5415281", "boj 1-10K", 2000),
]


def post_json(path, payload):
    req = urllib.request.Request(BASE + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())


def get_json(path, timeout=60):
    with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
        return json.loads(r.read())


def probe_video_bps(job_id, dest):
    with urllib.request.urlopen(f"{BASE}/api/download/{job_id}", timeout=900) as r, \
            open(dest, "wb") as f:
        while True:
            c = r.read(1 << 20)
            if not c:
                break
            f.write(c)
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=bit_rate,width,height,r_frame_rate,nb_frames",
         "-show_entries", "format=duration,size", "-of", "json", str(dest)],
        capture_output=True, text=True, timeout=300)
    return json.loads(out.stdout or "{}")


def main():
    label_filter = sys.argv[1:] or None
    print(f"{'case':<22} {'req_kbps':>8} {'wall_s':>7} {'bytes':>11} {'video_bps':>10} {'pct_of_req':>10}",
          flush=True)
    for label, bid, skin, kbps in CASES:
        if label_filter and label not in label_filter:
            continue
        payload = {"bid": bid, "skin": skin, "scroll": "30", "fps": "60",
                   "width": "1920", "height": "1080", "bg_dim": "0.6",
                   "engine": "webgl", "bitrate_kbps": str(kbps)}
        t0 = time.monotonic()
        job = post_json("/api/render", payload)
        job_id = job["id"]
        while True:
            time.sleep(4)
            st = get_json(f"/api/jobs/{job_id}")
            if st.get("state") in ("done", "error"):
                break
        wall = time.monotonic() - t0
        if st.get("state") != "done":
            print(f"{label:<22} FAILED: {st.get('error')}", flush=True)
            continue
        dest = OUT / f"{label}.mp4"
        info = probe_video_bps(job_id, dest)
        v = (info.get("streams") or [{}])[0]
        size = int((info.get("format") or {}).get("size") or 0)
        vbps = int(v.get("bit_rate") or 0)
        print(f"{label:<22} {kbps:>8} {wall:>7.1f} {size:>11} {vbps:>10} "
              f"{100.0*vbps/(kbps*1000):>9.0f}%", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
