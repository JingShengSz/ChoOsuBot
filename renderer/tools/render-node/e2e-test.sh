#!/bin/bash
# End-to-end proof, run ON THE VPS.
#
# Everything below talks to http://127.0.0.1:8760 -- which on the VPS is NOT a local
# process any more. mania-render.service is inactive+disabled there; that loopback port
# is an sshd reverse-forward listener that lands on the Windows machine's own
# 127.0.0.1:8760. So this script never leaves the VPS, yet the render happens on Windows.
#
# Usage: bash /tmp/e2e.sh [bid] [range]

set -u
BASE=http://127.0.0.1:8760
BID="${1:-5366777}"
RANGE="${2:-0-8}"
OUT=/tmp/mania-e2e

rm -rf "$OUT"; mkdir -p "$OUT"

echo "############ 0. VPS baseline ############"
echo "--- no mania_render process may be running here:"
pgrep -af "mania_render" || echo "    (none)"
echo "--- unit state:"
echo "    mania-render: $(systemctl is-active mania-render) / $(systemctl is-enabled mania-render)"
echo "--- who owns 127.0.0.1:8760 on the VPS:"
ss -lntp | grep 8760 | sed 's/^/    /'
echo "--- /opt/mania-render render cache, newest file before the test:"
find /opt/mania-render/cache -type f -printf '%T+ %p\n' 2>/dev/null | sort | tail -3 | sed 's/^/    /'
echo "--- load: $(uptime)"

echo
echo "############ 1. POST /api/render (through the tunnel) ############"
START=$(date +%s.%N)
RESP=$(curl -s -m 60 -X POST "$BASE/api/render" \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode "bid=$BID" \
  --data-urlencode "skin=boj 1-10K" \
  --data-urlencode "scroll=30" \
  --data-urlencode "fps=60" \
  --data-urlencode "width=1280" \
  --data-urlencode "height=720" \
  --data-urlencode "bg_dim=0.6" \
  --data-urlencode "range=$RANGE" \
  --data-urlencode "engine=python")
echo "response: $RESP"
JOB=$(printf '%s' "$RESP" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("id",""))')
if [ -z "$JOB" ]; then echo "!! no job id -- aborting"; exit 1; fi
echo "job_id = $JOB"

echo
echo "############ 2. poll to completion ############"
while :; do
  S=$(curl -s -m 10 "$BASE/api/jobs/$JOB")
  ST=$(printf '%s' "$S"  | python3 -c 'import json,sys; print(json.load(sys.stdin).get("state",""))' 2>/dev/null)
  PCT=$(printf '%s' "$S" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("percent",0))' 2>/dev/null)
  MSG=$(printf '%s' "$S" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("message",""))' 2>/dev/null)
  echo "    state=$ST pct=$PCT msg=$MSG"
  [ "$ST" = "done" ]  && break
  [ "$ST" = "error" ] && { echo "!! render error: $S"; exit 1; }
  sleep 5
done
END=$(date +%s.%N)
echo "WALL CLOCK (submit -> done): $(python3 -c "print(f'{$END-$START:.1f}s')")"

echo
echo "############ 3. download the result ############"
curl -s -m 600 -o "$OUT/out.mp4" "$BASE/api/download/$JOB"
ls -l "$OUT/out.mp4" | sed 's/^/    /'
echo "    sha256: $(sha256sum "$OUT/out.mp4" | cut -d' ' -f1)"

echo
echo "############ 4. ffprobe (must show a video AND an audio stream) ############"
ffprobe -v error \
  -show_entries format=duration,size,format_name \
  -show_entries stream=index,codec_type,codec_name,width,height,r_frame_rate,sample_rate,channels \
  -of default=noprint_wrappers=1 "$OUT/out.mp4" | sed 's/^/    /'

echo
echo "--- stream count by type:"
echo "    video streams: $(ffprobe -v error -select_streams v -show_entries stream=index -of csv=p=0 "$OUT/out.mp4" | grep -c .)"
echo "    audio streams: $(ffprobe -v error -select_streams a -show_entries stream=index -of csv=p=0 "$OUT/out.mp4" | grep -c .)"

echo
echo "############ 5. the VPS did no rendering ############"
echo "--- load after: $(uptime)"
echo "--- mania_render processes here: $(pgrep -cf mania_render || echo 0)"
echo "--- /opt/mania-render render cache, newest file after the test:"
find /opt/mania-render/cache -type f -printf '%T+ %p\n' 2>/dev/null | sort | tail -3 | sed 's/^/    /'
echo "--- files under /opt/mania-render modified in the last 10 min (expect none):"
find /opt/mania-render -newermt '-10 minutes' -type f 2>/dev/null | sed 's/^/    /' || true
echo "    (end)"
