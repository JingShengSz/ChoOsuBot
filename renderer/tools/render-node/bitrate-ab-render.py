#!/usr/bin/env python3
"""Drive REAL renders through the VPS's tunnel to the Windows render node.

Measures, for each case: the job the service reports (skin/bitrate/engine/size), wall
clock, the downloaded byte size, and ffprobe of the delivered file. Every case is posted
from the VPS to 127.0.0.1:8760, which is the reverse-SSH tunnel to the render node -- the
same path the AstrBot plugin uses.

Cases run SEQUENTIALLY on purpose: one headless Chrome drives one page at a time, so
running two renders at once would make wall clock (and possibly encode rate) meaningless.
"""
import hashlib
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:8760"
OUT = Path("/tmp/mania-ab")
OUT.mkdir(parents=True, exist_ok=True)

# label, bid, skin, bitrate_kbps, note
CASES = [
    ("R1-old-6000-boj", "5415281", "boj 1-10K", 6000,
     "replays the OLD 6 Mbps default (86 s chart)"),
    ("R2-new-2000-boj", "5415281", "boj 1-10K", 2000,
     "new service default rate, same chart/skin as R1"),
    ("R3-new-2000-rskin", "5415281", "R Skin", 2000,
     "same as R2 but R Skin -> skin differential"),
    ("R4-long-4m11-rskin", "5366777", "R Skin", 2000,
     "LONG chart (250.6 s = 4:11), default rate"),
]


def post_json(path, payload):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(BASE + path, data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())


def get_json(path, timeout=60):
    with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
        return json.loads(r.read())


def download(job_id, dest):
    with urllib.request.urlopen(f"{BASE}/api/download/{job_id}", timeout=900) as r, \
            open(dest, "wb") as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
    return dest.stat().st_size


def ffprobe(path):
    cmd = ["ffprobe", "-v", "error",
           "-show_entries",
           "stream=index,codec_type,codec_name,width,height,r_frame_rate,avg_frame_rate,"
           "bit_rate,nb_frames,sample_rate,channels",
           "-show_entries", "format=duration,size,bit_rate",
           "-of", "json", str(path)]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if out.returncode != 0:
        return {"error": out.stderr[-400:]}
    return json.loads(out.stdout or "{}")


def summarise(probe):
    lines = []
    fmt = probe.get("format", {})
    lines.append("    format : duration=%ss size=%s bytes bit_rate=%s bps" % (
        fmt.get("duration"), fmt.get("size"), fmt.get("bit_rate")))
    for s in probe.get("streams", []):
        if s.get("codec_type") == "video":
            lines.append("    video  : %s %sx%s r_frame_rate=%s avg=%s bit_rate=%s nb_frames=%s"
                         % (s.get("codec_name"), s.get("width"), s.get("height"),
                            s.get("r_frame_rate"), s.get("avg_frame_rate"),
                            s.get("bit_rate"), s.get("nb_frames")))
        elif s.get("codec_type") == "audio":
            lines.append("    audio  : %s %s Hz %s ch bit_rate=%s"
                         % (s.get("codec_name"), s.get("sample_rate"),
                            s.get("channels"), s.get("bit_rate")))
    return "\n".join(lines)


def run_case(label, bid, skin, kbps, note):
    print("=" * 78, flush=True)
    print(f"CASE {label}: bid={bid} skin={skin!r} bitrate_kbps={kbps}", flush=True)
    print(f"  note: {note}", flush=True)
    payload = {"bid": bid, "skin": skin, "scroll": "30", "fps": "60",
               "width": "1920", "height": "1080", "bg_dim": "0.6",
               "engine": "webgl", "bitrate_kbps": str(kbps)}
    t0 = time.monotonic()
    job = post_json("/api/render", payload)
    job_id = job.get("id")
    print(f"  job id: {job_id}", flush=True)
    print(f"  submitted job record: {json.dumps(job.get('job'), ensure_ascii=False)}", flush=True)

    state = None
    while True:
        time.sleep(5)
        state = get_json(f"/api/jobs/{job_id}")
        if state.get("state") in ("done", "error"):
            break
        if time.monotonic() - t0 > 1800:
            print("  TIMEOUT waiting for job", flush=True)
            return None
    wall = time.monotonic() - t0
    print(f"  final state: {json.dumps(state, ensure_ascii=False)}", flush=True)
    if state.get("state") != "done":
        print(f"  JOB FAILED after {wall:.1f}s", flush=True)
        return None

    dest = OUT / f"{label}.mp4"
    nbytes = download(job_id, dest)
    probe = ffprobe(dest)
    digest = hashlib.sha256(dest.read_bytes()).hexdigest()
    print(f"  wall clock : {wall:.1f}s", flush=True)
    print(f"  bytes      : {nbytes}  ({nbytes/1048576:.2f} MiB)", flush=True)
    print(f"  sha256     : {digest}", flush=True)
    print(summarise(probe), flush=True)
    return {"label": label, "bid": bid, "skin": skin, "kbps": kbps, "job_id": job_id,
            "wall_s": round(wall, 1), "bytes": nbytes, "sha256": digest,
            "service_state": state, "ffprobe": probe}


def main():
    only = sys.argv[1:] or None
    results = []
    for label, bid, skin, kbps, note in CASES:
        if only and label not in only:
            continue
        try:
            r = run_case(label, bid, skin, kbps, note)
        except Exception as exc:
            print(f"  CASE ERROR: {type(exc).__name__}: {exc}", flush=True)
            r = None
        if r:
            results.append(r)
    (OUT / "results.json").write_text(json.dumps(results, indent=2))
    print("=" * 78, flush=True)
    print("SUMMARY", flush=True)
    for r in results:
        print(f"  {r['label']:<22} {r['bytes']:>10} bytes  {r['bytes']/1048576:8.2f} MiB  "
              f"{r['wall_s']:>7.1f}s  skin={r['skin']}", flush=True)
    print(f"  results written to {OUT/'results.json'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
