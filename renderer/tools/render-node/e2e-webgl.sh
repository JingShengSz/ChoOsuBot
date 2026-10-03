#!/bin/bash
# End-to-end proof of the WebGL engine, run ON THE VPS.
#
# Same shape as e2e-test.sh, with the differences that matter for the engine switch:
#   * the engine field is optional (see Usage): omitted it exercises the service's own
#     configured default (MANIA_ENGINE in render-node.ps1, now 'webgl'); set to webgl it is
#     byte-for-byte what the AstrBot plugin sends now that its config says engine=webgl.
#   * the size is the plugin's `default_resolution: 1080` -> 1920x1080, sent as two fields
#     exactly as the plugin does (it never omits them).
#   * multipart/form-data (-F), which is the encoding aiohttp's FormData actually produces.
#
# Everything below talks to http://127.0.0.1:8760 -- on the VPS that is NOT a local process.
# mania-render.service is inactive+disabled here; the loopback port is an sshd
# reverse-forward listener that lands on the Windows machine.
#
# Usage: bash e2e-webgl.sh [bid] [range] [engine]
#   engine omitted/empty -> the request carries NO engine field, so the service's own
#                           configured default is what runs.
#   engine=webgl         -> exactly what the AstrBot plugin sends once its config says webgl
#                           (it only adds the field when its own `engine` is set).

set -u
BASE=http://127.0.0.1:8760
BID="${1:-3841899}"
RANGE="${2:-0-10}"
ENGINE="${3:-}"
OUT=/tmp/mania-e2e-webgl

rm -rf "$OUT"; mkdir -p "$OUT"

echo "############ 0. VPS baseline ############"
echo "--- mania_render processes here (expect none):"
pgrep -af "mania_render" || echo "    (none)"
echo "--- unit state (expect inactive / disabled):"
echo "    mania-render: $(systemctl is-active mania-render) / $(systemctl is-enabled mania-render)"
echo "--- who owns 127.0.0.1:8760 on the VPS (expect sshd, NOT python):"
ss -lntp | grep 8760 | sed 's/^/    /'
echo "--- load: $(uptime)"

echo
echo "############ 1. POST /api/render through the tunnel ############"
echo "    engine field: ${ENGINE:-<not sent>}   size: 1920x1080   range: $RANGE"
START=$(date +%s.%N)
FORM=(-F "bid=$BID" -F "skin=boj 1-10K" -F "scroll=30" -F "fps=60"
      -F "width=1920" -F "height=1080" -F "bg_dim=0.6" -F "range=$RANGE")
[ -n "$ENGINE" ] && FORM+=(-F "engine=$ENGINE")
RESP=$(curl -s -m 60 -X POST "$BASE/api/render" "${FORM[@]}")
echo "response: $RESP"
JOB=$(printf '%s' "$RESP" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("id",""))')
[ -z "$JOB" ] && { echo "!! no job id -- aborting"; exit 1; }
echo "job_id = $JOB"

echo
echo "############ 2. poll to completion ############"
while :; do
  S=$(curl -s -m 10 "$BASE/api/jobs/$JOB")
  ST=$(printf '%s' "$S"  | python3 -c 'import json,sys; print(json.load(sys.stdin).get("state",""))' 2>/dev/null)
  PCT=$(printf '%s' "$S" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("percent",0))' 2>/dev/null)
  MSG=$(printf '%s' "$S" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("message",""))' 2>/dev/null)
  echo "    $(date +%H:%M:%S) state=$ST pct=$PCT msg=$MSG"
  [ "$ST" = "done" ]  && break
  [ "$ST" = "error" ] && { echo "!! render error: $S"; exit 1; }
  sleep 3
done
END=$(date +%s.%N)
echo "WALL CLOCK (submit -> done): $(python3 -c "print(f'{$END-$START:.1f}s')")"
echo "--- job record as the service reported it:"
curl -s -m 10 "$BASE/api/jobs/$JOB" | python3 -m json.tool | sed 's/^/    /'

echo
echo "############ 3. download the result ############"
DL0=$(date +%s.%N)
curl -s -m 600 -o "$OUT/out.mp4" "$BASE/api/download/$JOB"
DL1=$(date +%s.%N)
ls -l "$OUT/out.mp4" | sed 's/^/    /'
echo "    download time: $(python3 -c "print(f'{$DL1-$DL0:.1f}s')")"
echo "    sha256: $(sha256sum "$OUT/out.mp4" | cut -d' ' -f1)"

echo
echo "############ 4. ffprobe ############"
ffprobe -v error \
  -show_entries format=duration,size,format_name,bit_rate \
  -show_entries stream=index,codec_type,codec_name,profile,width,height,r_frame_rate,avg_frame_rate,nb_frames,sample_rate,channels \
  -of default=noprint_wrappers=1 "$OUT/out.mp4" | sed 's/^/    /'
V=$(ffprobe -v error -select_streams v -show_entries stream=index -of csv=p=0 "$OUT/out.mp4" | grep -c .)
A=$(ffprobe -v error -select_streams a -show_entries stream=index -of csv=p=0 "$OUT/out.mp4" | grep -c .)
echo "    video streams: $V   audio streams: $A"
ffprobe -v error -select_streams a -show_entries stream=codec_name -of csv=p=0 "$OUT/out.mp4" \
  | grep -qx aac && echo "    audio codec is aac: YES" || echo "    audio codec is aac: NO"

echo
echo "############ 5. the VPS still did no rendering ############"
echo "--- load after: $(uptime)"
echo "--- mania_render processes here: $(pgrep -cf mania_render || echo 0)"
echo "--- /opt/mania-render files modified in the last 10 min (expect none):"
find /opt/mania-render -newermt '-10 minutes' -type f 2>/dev/null | sed 's/^/    /' || true
echo "    (end)"

echo
echo "############ 6. tunnel still healthy after the render ############"
ss -lntp | grep 8760 | sed 's/^/    /'
echo "--- /api/skins default (D:\\ paths prove this is the Windows box):"
curl -s -m 15 "$BASE/api/skins" | python3 -c 'import json,sys; d=json.load(sys.stdin); print("    default:", d.get("default")); [print("    ", s["key"], "->", s["path"]) for s in d.get("skins",[])]'
