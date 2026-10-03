#!/usr/bin/env python3
"""Final verification renders against the FINAL code (CBR rate control + audio-aware cap).

V1/V2 are the same chart+settings as the earlier R1/R2/R3 so the old-vs-new table is a
like-for-like comparison; V3/V4 are the long chart (250.6 s = 4:11) on both skins, which is
the worst case for delivered size.

Also records the sha256 of every output, so the skin differential is measurable rather
than asserted.
"""
import hashlib
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:8760"
OUT = Path("/tmp/mania-verify")
OUT.mkdir(parents=True, exist_ok=True)

# label, bid, skin, bitrate_kbps, note
CASES = [
    ("V1-86s-boj-2000", "5415281", "boj 1-10K", 2000,
     "the rate that overshot to 4.78 Mbps under VBR"),
    ("V2-86s-rskin-2000", "5415281", "R Skin", 2000, "what the bot actually sends"),
    ("V3-4m11-boj-2000", "5366777", "boj 1-10K", 2000,
     "LONG chart, busiest skin = worst case"),
    ("V4-4m11-rskin-2000", "5366777", "R Skin", 2000, "LONG chart, bot's skin"),
]


def post_json(path, payload):
    req = urllib.request.Request(BASE + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())


def get_json(path, timeout=60):
    with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
        return json.loads(r.read())


def fetch(job_id, dest):
    with urllib.request.urlopen(f"{BASE}/api/download/{job_id}", timeout=900) as r, \
            open(dest, "wb") as f:
        while True:
            c = r.read(1 << 20)
            if not c:
                break
            f.write(c)
    return dest.stat().st_size


def probe(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error",
         "-show_entries",
         "stream=index,codec_type,codec_name,width,height,r_frame_rate,avg_frame_rate,"
         "bit_rate,nb_frames,sample_rate,channels",
         "-show_entries", "format=duration,size,bit_rate", "-of", "json", str(path)],
        capture_output=True, text=True, timeout=300)
    return json.loads(out.stdout or "{}")


def run(label, bid, skin, kbps, note):
    print("=" * 78, flush=True)
    print(f"CASE {label}: bid={bid} skin={skin!r} bitrate_kbps={kbps}", flush=True)
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
        if time.monotonic() - t0 > 1800:
            print("  TIMEOUT", flush=True)
            return None
    wall = time.monotonic() - t0
    if st.get("state") != "done":
        print(f"  FAILED: {st.get('error')}", flush=True)
        return None
    dest = OUT / f"{label}.mp4"
    nbytes = fetch(job_id, dest)
    info = probe(dest)
    digest = hashlib.sha256(dest.read_bytes()).hexdigest()
    fmt = info.get("format", {})
    print(f"  job={job_id} engine={st.get('engine')} skin={st.get('skin')!r} "
          f"bitrate_kbps={st.get('bitrate_kbps')}", flush=True)
    print(f"  service size_bytes={st.get('size_bytes')}  downloaded={nbytes}", flush=True)
    print(f"  wall={wall:.1f}s  bytes={nbytes} ({nbytes/1048576:.2f} MiB)", flush=True)
    print(f"  sha256={digest}", flush=True)
    print(f"  ffprobe format: duration={fmt.get('duration')} size={fmt.get('size')} "
          f"bit_rate={fmt.get('bit_rate')}", flush=True)
    for s in info.get("streams", []):
        print(f"  ffprobe stream{s.get('index')}: {json.dumps(s)}", flush=True)
    return {"label": label, "bid": bid, "skin": skin, "kbps": kbps, "note": note,
            "job_id": job_id, "wall_s": round(wall, 1), "bytes": nbytes,
            "sha256": digest, "service_state": st, "ffprobe": info}


def main():
    only = sys.argv[1:] or None
    out = []
    for label, bid, skin, kbps, note in CASES:
        if only and label not in only:
            continue
        try:
            r = run(label, bid, skin, kbps, note)
        except Exception as exc:
            print(f"  ERROR {type(exc).__name__}: {exc}", flush=True)
            r = None
        if r:
            out.append(r)
    (OUT / "verify.json").write_text(json.dumps(out, indent=2))
    print("=" * 78, flush=True)
    print(f"{'case':<22} {'bytes':>10} {'MiB':>7} {'wall_s':>7}  skin", flush=True)
    for r in out:
        print(f"{r['label']:<22} {r['bytes']:>10} {r['bytes']/1048576:>7.2f} "
              f"{r['wall_s']:>7.1f}  {r['skin']}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
