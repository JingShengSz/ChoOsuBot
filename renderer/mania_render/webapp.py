from __future__ import annotations

import json
import os
import re
import socket
import threading
import time
import traceback
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse, unquote

from .fetch import (fetch_audio, fetch_meta, fetch_osu_text, load_beatmap_by_id,
                    lookup_bid_by_md5, looks_like_audio, parse_range, audio_cache_path)
from .osr import parse_osr

# `build_geometry` / `Renderer` / `load_skin` / `cli._pick_skin` pull in Pillow and numpy and
# are only needed by the server-side render job, so they are imported inside `_run_job`.
# The static + API server — the deployment that matters on a 2 GB box — then needs nothing
# but the standard library, and does not carry numpy's per-thread OpenBLAS commit.

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "cache"
SKIN_PREFS = CACHE / "skin_prefs.json"
JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()


def skins_root() -> Path:
    """Where the `.osk` files live. Override with MANIA_SKINS_DIR on the target machine."""
    env = os.environ.get("MANIA_SKINS_DIR")
    return Path(env) if env else ROOT / "skins"


# Skin keys as originally registered, mapped to the FILE NAME only. Absolute paths are no
# longer baked in: each name is looked up under the skins directory first and only then in
# the legacy developer location, so the same registry works on Linux once the `.osk` files
# are copied over.
_REGISTERED: dict[str, str] = {
    "owc (default)": "owc Skin Remake v2 (RealTBNRKenny).osk",
    "Cho'": "Cho' Skin (F6A8AF) (1).osk",
    "R Skin": "R Skin v3.0 (4+6K).osk",
    "boj 1-10K": "# boj - pl0x Circles 1-10K (bojii 「 https) (1).osk",
}
_LEGACY_DIRS = (Path(r"D:\osu-lazer\exports"),)


def _discover_skins() -> dict[str, str]:
    """`skins_root()` contents, plus the registered keys resolved by file name.

    Only `skins_root()` is enumerated — the legacy developer directory is searched *by the
    registered names only*, so a machine that happens to have a folder full of skins does
    not dump all of them into the dropdown. A file in `skins_root()` that carries a
    registered name keeps its friendly registered key instead of appearing twice.

    `_REGISTERED` defines the display order; a root-level file that is not registered
    follows the registered entries rather than jumping to the front.
    """
    found: dict[str, str] = {}
    root = skins_root()
    key_by_name = {name: key for key, name in _REGISTERED.items()}
    if root.is_dir():
        for p in sorted(root.iterdir()):
            is_skin = p.suffix.lower() == ".osk" or (p.is_dir() and (p / "skin.ini").is_file())
            if is_skin:
                found.setdefault(key_by_name.get(p.name, p.stem), str(p))

    out: dict[str, str] = {}
    for key, name in _REGISTERED.items():
        if key in found:
            out[key] = found.pop(key)
            continue
        for d in (root, *_LEGACY_DIRS):
            cand = d / name
            if cand.is_file():
                out[key] = str(cand)
                break
    out.update(found)
    return out


SKINS: dict[str, str] = _discover_skins()

# Requested default: boj. `MANIA_DEFAULT_SKIN` names it explicitly; the fallbacks cover the
# case where the file was dropped into skins/ under a different name (say `boj.osk`).
DEFAULT_SKIN_KEY = os.environ.get("MANIA_DEFAULT_SKIN") or "boj 1-10K"

# Which renderer a job uses unless it asks otherwise.
#   webgl  — drive the page at `/` in headless Chromium over CDP. Same picture a human
#            sees in the browser, and the engine the visual conformance work was checked
#            against. Costs a real-time recording (a 150 s chart takes 150 s) and needs a
#            Chromium listening on CHROME_PORT.
#   python — the Pillow renderer: no browser, no display, ~1.3-1.5x real time.
ENGINES = ("webgl", "python")
DEFAULT_ENGINE = os.environ.get("MANIA_ENGINE", "webgl").strip().lower()
CHROME_HOST = os.environ.get("MANIA_CHROME_HOST", "127.0.0.1")
CHROME_PORT = int(os.environ.get("MANIA_CHROME_PORT", "9222"))

# What a job renders at when the request carries no `width`/`height`.
#
# 1920x1080 is the size the page itself is built at: `mania-web/index.html` declares both
# canvases as width="1920" height="1080", and the Pillow renderer's geometry is fixed
# there too. The pair used to be 1280x720, which made "say nothing" mean 720p on the WebGL
# engine while the Python engine still produced 1080p from the same request — the same job
# silently changing size with the engine. A caller that wants 720p still gets it by asking
# (`width=1280&height=720`, which is what the plugin sends for `default_resolution: 720`).
DEFAULT_WIDTH = int(os.environ.get("MANIA_WIDTH", "1920"))
DEFAULT_HEIGHT = int(os.environ.get("MANIA_HEIGHT", "1080"))

# What a job encodes at when the request carries no `bitrate_kbps`, in kbps.
#
# This is the knob that decides the finished file's size, and therefore whether the file
# can be delivered at all. Size is not a taste question here: the plugin hands the MP4 to
# the platform's protocol adapter, which pushes it over an upload channel that times out on
# a large body. Measured on this pipeline, same 86 s chart, webgl engine:
#
#   6000 kbps -> 74.8 MB. The video channel timed out mid-send, the plugin fell back to the
#                file channel, that timed out too, and the chat got a 「发送失败」 for a
#                video that had in fact already been delivered. A 4-minute chart at that
#                rate is ~200 MB, which never arrives at all.
#   2000 kbps -> ~24 MB (the default below). A 4-minute chart stays near 60 MB, inside the
#                plugin's 80 MB `video_file_threshold_mb`.
#
# `MANIA_BITRATE` overrides it, in kbps, exactly like `MANIA_WIDTH`/`MANIA_HEIGHT`. The
# page's OWN default (6000 kbps, `MANUAL_BITRATE` in mania-web/src/main.js) is deliberately
# unchanged: a human clicking 导出 writes a local file that never crosses an upload channel,
# so the manual export keeps the higher quality.
DEFAULT_BITRATE_KBPS = int(os.environ.get("MANIA_BITRATE", "2000"))


def default_skin_key() -> str:
    if DEFAULT_SKIN_KEY in SKINS:
        return DEFAULT_SKIN_KEY
    for k in SKINS:
        if k.lower().startswith("boj"):
            return k
    return next(iter(SKINS), "")


DEFAULT_SCROLL = 30.0


def load_skin_prefs() -> dict:
    try:
        return json.loads(SKIN_PREFS.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_skin_prefs(prefs: dict) -> None:
    SKIN_PREFS.parent.mkdir(parents=True, exist_ok=True)
    SKIN_PREFS.write_text(json.dumps(prefs, ensure_ascii=False, indent=2), encoding="utf-8")


def scroll_for_skin(skin_key: str) -> float:
    prefs = load_skin_prefs()
    try:
        return float(prefs.get(skin_key, prefs.get(SKINS.get(skin_key, skin_key), DEFAULT_SCROLL)))
    except (TypeError, ValueError):
        return DEFAULT_SCROLL


def set_scroll_for_skin(skin_key: str, scroll: float) -> None:
    prefs = load_skin_prefs()
    prefs[skin_key] = float(scroll)
    path = SKINS.get(skin_key)
    if path:
        prefs[path] = float(scroll)
    save_skin_prefs(prefs)


HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Mania Render</title>
<style>
  :root { --bg:#0f1115; --card:#181b22; --ink:#e8eaef; --dim:#8b93a7; --acc:#6ec1e4; --line:#2a2f3a; }
  * { box-sizing:border-box; }
  body { margin:0; font:14px/1.5 -apple-system,'Segoe UI','PingFang SC','Microsoft YaHei',sans-serif; background:var(--bg); color:var(--ink); }
  .wrap { max-width:860px; margin:32px auto; padding:0 16px; }
  h1 { font-size:22px; font-weight:600; margin:0 0 4px; }
  .sub { color:var(--dim); margin-bottom:24px; }
  .card { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:20px 22px; margin-bottom:16px; }
  label { display:block; font-size:12px; color:var(--dim); margin:14px 0 6px; }
  input, select { width:100%; padding:10px 12px; border-radius:8px; border:1px solid var(--line); background:#12151c; color:var(--ink); font-size:14px; }
  input:focus, select:focus { outline:1px solid var(--acc); }
  .row { display:grid; grid-template-columns:1fr 1fr 1fr; gap:12px; }
  .row2 { display:grid; grid-template-columns:1fr 1fr; gap:12px; }
  button { margin-top:18px; width:100%; padding:12px; border:0; border-radius:8px; background:var(--acc); color:#0b0d12; font-weight:600; font-size:15px; cursor:pointer; }
  button:disabled { opacity:.5; cursor:wait; }
  .status { margin-top:14px; padding:12px; border-radius:8px; background:#12151c; border:1px solid var(--line); min-height:44px; white-space:pre-wrap; }
  .ok { color:#8fd694; } .err { color:#e06c75; }
  .hint { color:var(--dim); font-size:12px; margin-top:8px; }
  video { width:100%; margin-top:14px; border-radius:8px; background:#000; }
  a.dl { display:inline-block; margin-top:10px; color:var(--acc); }
</style>
</head>
<body>
<div class="wrap">
  <h1>osu!mania 离线渲染</h1>
  <div class="sub">1920×1080 · skin.ini + Layout JSON · 对齐 osu 源码</div>

  <div class="card">
    <div class="row">
      <div>
        <label>谱面 ID (bid) — 可空，传 .osr 自动识别</label>
        <input id="bid" placeholder="例如 4764345"/>
      </div>
      <div>
        <label>皮肤（滚动速度按皮肤记忆）</label>
        <select id="skin"></select>
      </div>
      <div>
        <label>滚动速度（ScrollSpeed）</label>
        <input id="scroll" type="number" min="1" max="40" step="0.1" value="30"/>
      </div>
    </div>
    <div class="row2">
      <div>
        <label>Replay (.osr) 可选 — 选了可自动识别谱面</label>
        <input id="osr" type="file" accept=".osr"/>
      </div>
      <div>
        <label>片段 秒（闭区间，空=全曲）</label>
        <input id="range" placeholder="例如 30-60"/>
      </div>
    </div>
    <div class="row2">
      <div>
        <label>帧率</label>
        <select id="fps"><option>60</option><option selected>30</option><option>24</option></select>
      </div>
      <div>
        <label>片头 lead-in（秒，0/起始点为 0 时默认 1）</label>
        <input id="lead" type="number" min="0" max="5" step="0.5" placeholder="自动"/>
      </div>
    </div>
    <button id="go">开始渲染</button>
    <div class="hint">无 .osr 时走 FC Sim；有则 Combo/CPS/误差条/judgement 面板按回放。BarHitErrorMeter 仅 Replay 显示。</div>
    <div class="status" id="status">就绪。</div>
    <video id="player" controls hidden></video>
    <a class="dl" id="dl" hidden download>下载 MP4</a>
  </div>
</div>
<script>
const $ = (id) => document.getElementById(id);

async function loadSkins() {
  const r = await fetch('/api/skins');
  const data = await r.json();
  const sel = $('skin');
  sel.innerHTML = '';
  for (const s of data.skins) {
    const o = document.createElement('option');
    o.value = s.key;
    o.textContent = s.key;
    sel.appendChild(o);
  }
  // default first
  if (data.skins.length) {
    sel.value = data.skins[0].key;
    $('scroll').value = data.skins[0].scroll ?? 30;
  }
}

$('skin').addEventListener('change', async () => {
  const r = await fetch('/api/skins');
  const data = await r.json();
  const s = data.skins.find(x => x.key === $('skin').value);
  if (s) $('scroll').value = s.scroll ?? 30;
});

$('scroll').addEventListener('change', async () => {
  await fetch('/api/skin_scroll', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ skin: $('skin').value, scroll: parseFloat($('scroll').value) })
  });
});

// osr → 自动识别谱面 ID
$('osr').addEventListener('change', async () => {
  const f = $('osr').files[0];
  if (!f) return;
  const st = $('status');
  st.className = 'status';
  st.textContent = '从 .osr 识别谱面…';
  const fd = new FormData();
  fd.append('osr', f);
  try {
    const r = await fetch('/api/resolve_osr', { method: 'POST', body: fd });
    const j = await r.json();
    if (!r.ok) throw new Error(j.error || 'resolve failed');
    if (j.bid) {
      $('bid').value = j.bid;
      st.textContent = `已识别谱面 ${j.bid}（${j.username || 'replay'}，${j.presses} 次按键）`;
    } else {
      st.textContent = `读到 MD5 ${j.md5 || '?'}，但没查到谱面 ID — 请手动填写`;
    }
  } catch (e) {
    st.className = 'status err';
    st.textContent = '识别失败：' + e.message;
  }
});

$('go').addEventListener('click', async () => {
  const st = $('status');
  $('go').disabled = true;
  $('player').hidden = true; $('dl').hidden = true;
  st.className = 'status';
  st.textContent = '提交中…';
  const fd = new FormData();
  fd.append('bid', $('bid').value.trim());
  fd.append('skin', $('skin').value);
  fd.append('scroll', $('scroll').value);
  fd.append('fps', $('fps').value);
  if ($('range').value.trim()) fd.append('range', $('range').value.trim());
  if ($('lead').value !== '') fd.append('lead_in', $('lead').value);
  const f = $('osr').files[0];
  if (f) fd.append('osr', f);
  try {
    const r = await fetch('/api/render', { method: 'POST', body: fd });
    const j = await r.json();
    if (!r.ok) throw new Error(j.error || 'render failed');
    const id = j.id;
    st.textContent = '渲染中…';
    const timer = setInterval(async () => {
      const sr = await fetch('/api/jobs/' + id);
      const sj = await sr.json();
      if (sj.message) st.textContent = sj.message;
      if (sj.state === 'done') {
        clearInterval(timer); $('go').disabled = false;
        st.className = 'status ok'; st.textContent = '完成：' + sj.output;
        $('player').src = '/api/download/' + id; $('player').hidden = false;
        $('dl').href = '/api/download/' + id; $('dl').hidden = false;
      } else if (sj.state === 'error') {
        clearInterval(timer); $('go').disabled = false;
        st.className = 'status err'; st.textContent = '失败：' + (sj.error || 'unknown');
      }
    }, 800);
  } catch (e) {
    $('go').disabled = false;
    st.className = 'status err'; st.textContent = String(e);
  }
});

loadSkins();
</script>
</body>
</html>
"""


API_LOG_LOCK = threading.Lock()


class StreamGap(Exception):
    """The client asked to append past what is on disk: bytes it sent never arrived."""


def _append_stream(path: Path, offset: int, body: bytes) -> int:
    """Append one upload to the H.264 stream and return the new length.

    The page sends each ~1.5 MB batch as its own POST, ~50 of them for a 95 s chart and
    several hundred for a long one. Measured: one such POST in ~250 was lost mid-flight and
    the page's fetch rejected with `TypeError: Failed to fetch`, which killed the whole
    render at 49% (`导出失败: Failed to fetch`, 40 MB already uploaded). A blind retry is not
    a fix -- re-sending a batch whose *reply* was lost would append its bytes twice and
    splice a duplicate into the Annex-B stream, which muxes into a file that looks fine and
    plays broken. So every request carries the byte position it is writing at, and this is
    what makes the retry safe:

      * offset beyond what is stored -> bytes are missing. REFUSE: appending would leave a
        hole, and the page's retry at the same offset is the thing that can still fix it.
      * the batch is already stored in full -> a repeat after a lost reply. Write nothing.
      * part of the batch is stored -> a broken connection cut the previous attempt short.
        Everything past `offset` is that same batch's tail (the page only ever appends at
        the offset it last had confirmed), so drop it and rewrite the batch.
      * offset == stored length -> the ordinary case: append.
      * offset < 0 -> a client that sends no offset. Append, as this endpoint always did.
    """
    size = path.stat().st_size if path.is_file() else 0
    if offset < 0:
        if body:
            with open(path, "ab") as fh:
                fh.write(body)
        return path.stat().st_size if path.is_file() else 0
    if offset > size:
        raise StreamGap(f"offset={offset} but only {size} bytes are stored")
    if offset + len(body) <= size:
        return size
    if offset < size:
        with open(path, "r+b") as fh:
            fh.truncate(offset)
    if body:
        with open(path, "ab") as fh:
            fh.write(body)
    return path.stat().st_size if path.is_file() else 0


def _api_log(line: str) -> None:
    """Append one line to cache/api.log.

    `log_message` is deliberately silent and stdout is block-buffered, so a failed audio
    request left NO trace anywhere — which is exactly why a reported 「音频获取失败」 could
    not be tied to a request. This file is the trace.
    """
    try:
        CACHE.mkdir(parents=True, exist_ok=True)
        with API_LOG_LOCK:
            with open(CACHE / "api.log", "a", encoding="utf-8") as fh:
                fh.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {line}\n")
    except Exception:
        pass


def _serve_file(handler: BaseHTTPRequestHandler, path: Path, ctype: str,
                extra: dict | None = None) -> None:
    """Send a file with HTTP Range support, streamed from disk.

    Range is not only about resuming. A browser that is never offered 206/Accept-Ranges
    reports `video.seekable` as an empty range and refuses to move the playhead, so the
    progress bar cannot be dragged at all. Measured on one exported mp4, same bytes:
      * Range-less server   -> seekable "0.0..0.0",  currentTime stuck at 0 after seeking
      * Range-capable server -> seekable "0.0..481.4", seeking to 300 s landed on 300 s
    The file's own index was identical both times, which is what ruled the muxer out.

    Streaming also keeps a 100+ MB render out of memory, which matters on the 2 GB target.
    """
    try:
        total = path.stat().st_size
    except OSError:
        return _json(handler, 404, {"error": "missing file"})

    start, end, partial = 0, total - 1, False
    rng = (handler.headers.get("Range") or "").strip()
    if rng:
        m = re.fullmatch(r"bytes=(\d*)-(\d*)", rng)
        if m and (m.group(1) or m.group(2)):
            if m.group(1) == "":                       # suffix range: the LAST N bytes
                start = max(0, total - int(m.group(2)))
            else:
                start = int(m.group(1))
                end = int(m.group(2)) if m.group(2) else total - 1
            end = min(end, total - 1)
            if start > end or start >= total:
                handler.send_response(416)             # RFC 7233: unsatisfiable
                handler.send_header("Content-Range", f"bytes */{total}")
                handler.send_header("Content-Length", "0")
                handler.end_headers()
                return
            partial = True
        # A malformed Range is ignored and answered with 200, which the RFC allows.

    length = end - start + 1
    handler.send_response(206 if partial else 200)
    handler.send_header("Content-Type", ctype)
    handler.send_header("Accept-Ranges", "bytes")
    handler.send_header("Content-Length", str(length))
    if partial:
        handler.send_header("Content-Range", f"bytes {start}-{end}/{total}")
    for k, v in (extra or {}).items():
        handler.send_header(k, v)
    handler.end_headers()
    with open(path, "rb") as fh:
        fh.seek(start)
        left = length
        while left > 0:
            chunk = fh.read(min(1 << 20, left))
            if not chunk:
                break
            handler.wfile.write(chunk)
            left -= len(chunk)


def _json(handler: BaseHTTPRequestHandler, code: int, obj) -> None:
    raw = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(raw)))
    handler.end_headers()
    handler.wfile.write(raw)


def _multipart_fields(body: bytes, ctype: str) -> tuple[dict, dict]:
    m = re.search(r'boundary="?([^";]+)"?', ctype)
    if not m:
        return {}, {}
    boundary = m.group(1).encode()
    fields: dict[str, str] = {}
    files: dict[str, tuple[str, bytes]] = {}
    for part in body.split(b"--" + boundary):
        part = part.strip(b"\r\n")
        if not part or part == b"--":
            continue
        if b"\r\n\r\n" not in part:
            continue
        head, _, data = part.partition(b"\r\n\r\n")
        hs = head.decode("utf-8", "replace")
        name_m = re.search(r'name="([^"]+)"', hs)
        if not name_m:
            continue
        name = name_m.group(1)
        fn_m = re.search(r'filename="([^"]*)"', hs)
        if fn_m:
            files[name] = (fn_m.group(1), data)
        else:
            fields[name] = data.decode("utf-8", "replace")
    return fields, files


def _run_job_webgl(job_id: str, bid: str, skin_key: str, scroll: float, fps: int,
                   range_s: str | None, lead_in: float | None, osr_path: Path | None,
                   bg_dim: float = 0.6, width: int = 0, height: int = 0,
                   bitrate_kbps: int = 0) -> None:
    """Render by driving the WebGL page in headless Chromium.

    Same job contract as `_run_job`: progress goes into JOBS and the finished file
    lands in `CACHE/renders`, so `/api/jobs` and `/api/download` need no changes.
    """
    from .fetch import load_beatmap_by_id
    from .renderer import _find_ffmpeg
    from .webgl_render import WebGLRenderError, render as webgl_render

    def set_(state, **kw):
        with JOBS_LOCK:
            JOBS[job_id].update({"state": state, **kw})

    try:
        # The WebGL export carries no audio track at all, so the beatmap's audio has to be
        # muxed in afterwards; the cache already holds it after the first fetch.
        audio_path = None
        try:
            set_("running", message="拉取音频…", percent=1)
            _bm, audio_path, _bg = load_beatmap_by_id(bid, CACHE)
            # Surfaced in the job record, not just stdout: the service's stdout is block
            # buffered when it is not a tty, so a print here is invisible while debugging.
            set_("running", message=f"音频就绪 {Path(str(audio_path)).name}", percent=2)
        except Exception as exc:      # noqa: BLE001 - a silent video still beats no video
            set_("running", message=f"无音频：{exc}", percent=2)
            audio_path = None

        out = CACHE / "renders" / f"{job_id}_{bid}.mp4"
        out.parent.mkdir(parents=True, exist_ok=True)
        with JOBS_LOCK:
            limit = float(JOBS[job_id].get("timeout") or 3600)
        webgl_render(
            job_id, bid, skin_key, osr_path=osr_path, scroll=scroll, bg_dim=bg_dim,
            range_s=range_s, width=width, height=height, bitrate_kbps=bitrate_kbps,
            work_dir=CACHE / "webgl_work", out_path=out, ffmpeg=_find_ffmpeg(),
            progress=lambda pct, msg: set_("running", message=msg, percent=pct),
            chrome_host=CHROME_HOST, chrome_port=CHROME_PORT, timeout=limit,
            audio_path=audio_path,
        )
        # The bitrate is echoed into the job record so a caller can prove which rate a file
        # was actually encoded at without reading the page's console.
        set_("done", message="完成", output=str(out), percent=100,
             width=width or 1920, height=height or 1080,
             bitrate_kbps=bitrate_kbps, size_bytes=out.stat().st_size)
    except WebGLRenderError as exc:
        set_("error", error=str(exc), message="失败")
    except Exception as exc:
        traceback.print_exc()
        set_("error", error=str(exc), message="失败")


def _dispatch_job(engine: str, *args) -> None:
    """Route a job to the requested renderer."""
    # Name the engine in BOTH traces. The two engines produce different pictures, so
    # "which one actually ran" is not a detail: without this line a job that fell through
    # to the other renderer looks exactly like a job that ran the one that was asked for.
    # stdout is block-buffered when the service has no tty (the supervisor redirects it to
    # a file), hence flush, and api.log is a second, always-flushed trace.
    job_id = args[0] if args else "?"
    print(f"[engine] job={job_id} engine={engine}", flush=True)
    _api_log(f"engine job={job_id} engine={engine}")
    if engine == "python":
        _run_job(*args)
    else:
        _run_job_webgl(*args)


def _run_job(job_id: str, bid: str, skin_key: str, scroll: float, fps: int,             range_s: str | None, lead_in: float | None, osr_path: Path | None,
             bg_dim: float = 0.6, width: int = 0, height: int = 0,
             bitrate_kbps: int = 0) -> None:
    # `bitrate_kbps` is accepted for signature parity with `_run_job_webgl` — both are
    # called through `_dispatch_job(*args)`. It is unused here on purpose: the Pillow
    # renderer encodes with a fixed CRF, not a target bitrate, and it must keep working as
    # the selectable fallback engine.
    del bitrate_kbps
    # Render-stack imports live here so the static/API server never loads Pillow or numpy.
    from .cli import _pick_skin
    from .playfield import build_geometry
    from .renderer import Renderer
    from .skin import load_skin

    def set_(state, **kw):
        with JOBS_LOCK:
            JOBS[job_id].update({"state": state, **kw})

    try:
        set_("running", message="拉取谱面…", percent=0)
        cache = CACHE
        cache.mkdir(parents=True, exist_ok=True)
        bm, audio_path, bg_path = load_beatmap_by_id(bid, cache)
        if bm.mode != 3:
            raise RuntimeError("非 mania 谱面")
        keys = bm.keys
        if keys > 10:
            raise RuntimeError("暂不支持：键数 > 10")

        set_("running", message="加载皮肤…")
        skin_path = Path(SKINS.get(skin_key, skin_key))
        if not skin_path.exists():
            skin_path = Path(_pick_skin(keys, str(skin_path) if skin_path.exists() else None))
        skin = load_skin(skin_path)
        block = skin.block_for_keys(keys)
        if block is None:
            raise RuntimeError(f"皮肤无 {keys}K [Mania]")
        block.keys = keys

        dur = bm.duration_s
        if range_s:
            start, end = parse_range(range_s)
            if end > dur + 0.05:
                raise RuntimeError(f"片段 {range_s} 超过时长 {dur:.1f}s")
        else:
            start, end = 0.0, dur

        replay = None
        if osr_path and osr_path.is_file():
            set_("running", message="解析回放…")
            head, replay = parse_osr(osr_path)
            # The replay's own mod field is the only record that the play was mirrored.
            if head.mirror:
                bm.apply_mirror()
                set_("running", message="回放为 Mirror 镜像谱面", percent=1)

        set_("running", message="渲染帧 0%…", percent=0)
        geom = build_geometry(block, scroll_speed=scroll)
        out = CACHE / "renders" / f"{job_id}_{bid}.mp4"
        r = Renderer(bm, audio_path, skin, geom, scroll_speed=scroll, fps=fps,
                     background=True, bg_path=bg_path, replay=replay, bg_dim=bg_dim)
        r.star_text = f"{bm.title} [{bm.version}]"
        lead = lead_in if lead_in is not None else (1.0 if start <= 1e-6 else 0.0)

        def on_prog(i, n, reused):
            pct = int(100 * (i + 1) / max(1, n))
            set_("running", message=f"渲染帧 {pct}%（{i+1}/{n}）", percent=pct)

        # The renderer's own geometry is fixed at 1920x1080; a different output size is a
        # scale in ffmpeg, which also doubles as a clean supersample down to 720p.
        scale_to = (width, height) if width and height else None
        path = r.render_mp4(out, start, end, lead_in_s=lead, progress_cb=on_prog,
                            scale_to=scale_to)
        set_("done", message="完成", output=str(path), percent=100,
             width=width or 1920, height=height or 1080)
    except Exception as exc:
        traceback.print_exc()
        set_("error", error=str(exc), message="失败")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # quiet
        pass

    def _static_headers(self, ctype: str, length: int) -> None:
        """No-store for every file served out of mania-web.

        A plain reload must always pick up the current build. Without any Cache-Control
        (and with no Last-Modified/ETag either) the browser falls back to heuristic
        caching, so `/src/main.js` can keep running for a long time after it changed —
        which makes every UI fix look like it did not land.
        """
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")

    def do_GET(self):
        u = urlparse(self.path)
        # ── mania-web static files ──
        web_root = ROOT / "mania-web"
        if u.path == "/" or u.path == "/index.html":
            index = web_root / "index.html"
            if index.is_file():
                raw = index.read_bytes()
                self.send_response(200)
                self._static_headers("text/html; charset=utf-8", len(raw))
                self.end_headers()
                self.wfile.write(raw)
                return
            raw = HTML.encode("utf-8")
            self.send_response(200)
            self._static_headers("text/html; charset=utf-8", len(raw))
            self.end_headers()
            self.wfile.write(raw)
            return
        if u.path.startswith("/src/") or u.path.startswith("/assets/"):
            rel = u.path.lstrip("/")
            fpath = web_root / rel
            if fpath.is_file():
                ctype = "application/javascript" if fpath.suffix == ".js" else "text/css" if fpath.suffix == ".css" else "application/octet-stream"
                raw = fpath.read_bytes()
                self.send_response(200)
                self._static_headers(ctype, len(raw))
                self.end_headers()
                self.wfile.write(raw)
                return
            return _json(self, 404, {"error": "not found"})

        if u.path in ("/diag", "/diag.html"):
            f = web_root / "diag.html"
            if f.is_file():
                raw = f.read_bytes()
                self.send_response(200)
                self._static_headers("text/html; charset=utf-8", len(raw))
                self.end_headers()
                self.wfile.write(raw)
                return
            return _json(self, 404, {"error": "diag.html missing"})

        if u.path.startswith("/api/media/"):
            # The SAME bytes as /api/audio, under a neutral path and content type. A
            # client-side blocker (extension, security suite) that aborts a media-typed
            # response leaves everything else alone; comparing this with /api/audio in the
            # browser is how that is told apart from a plain size limit. See /diag.
            rest = u.path[len("/api/media/"):]
            parts = rest.split("/", 1)
            if len(parts) != 2:
                return _json(self, 400, {"error": "need /api/media/{sid}/{filename}"})
            sid, filename = parts
            filename = unquote(filename)
            cached = audio_cache_path(CACHE, sid, filename)
            if not cached.is_file() or not looks_like_audio(cached):
                return _json(self, 404, {"error": f"no cached audio for sid={sid}"})
            _api_log(f"media 200 sid={sid} bytes={cached.stat().st_size} "
                     f"range={self.headers.get('Range')!r} client={self.client_address[0]}")
            _serve_file(self, cached, "application/octet-stream")
            return

        if u.path.startswith("/api/blob/"):
            # N bytes of inert filler, to find the SIZE at which a response stops arriving.
            try:
                n = max(0, min(int(u.path[len("/api/blob/"):]), 16 * 1024 * 1024))
            except ValueError:
                return _json(self, 400, {"error": "need /api/blob/{bytes}"})
            data = (b"MANIA-DIAG-BLOB-" * (n // 16 + 1))[:n]
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            _api_log(f"blob 200 bytes={len(data)} client={self.client_address[0]}")
            return

        # ── API ──
        if u.path == "/api/skins":
            prefs = load_skin_prefs()
            skins = []
            for key, path in SKINS.items():
                try:
                    sc = float(prefs.get(key, prefs.get(path, DEFAULT_SCROLL)))
                except Exception:
                    sc = DEFAULT_SCROLL
                skins.append({"key": key, "path": path, "scroll": sc})
            return _json(self, 200, {"skins": skins, "default": default_skin_key()})

        if u.path.startswith("/api/skin_file/"):
            key = unquote(u.path[len("/api/skin_file/"):])
            path = SKINS.get(key)
            if not path or not Path(path).is_file():
                return _json(self, 404, {"error": "skin not found"})
            data = Path(path).read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            # HTTP headers are latin-1: a skin whose filename holds CJK or 「 」 makes
            # send_header raise UnicodeEncodeError and kills the request ("Failed to
            # fetch" for Suisei / boj). The client reads the bytes and never uses the
            # name, so send an ASCII-safe one.
            safe_name = re.sub(r"[^A-Za-z0-9._ -]", "_", Path(path).name) or "skin.osk"
            self.send_header("Content-Disposition", f'attachment; filename="{safe_name}"')
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        if u.path.startswith("/api/beatmap_meta"):
            qs = parse_qs(u.query)
            md5 = (qs.get("md5") or [""])[0]
            bid = (qs.get("bid") or [""])[0]
            try:
                if md5:
                    rows = fetch_meta(md5=md5)
                elif bid:
                    rows = fetch_meta(bid=bid)
                else:
                    return _json(self, 400, {"error": "need md5 or bid"})
                if rows:
                    row = rows[0]
                    # ensure background_filename is available
                    if 'background_filename' not in row:
                        # try to get from .osu
                        try:
                            osu_text = fetch_osu_text(bid or row.get('beatmap_id', ''))
                            for line in osu_text.splitlines():
                                if line.startswith('0,0,'):
                                    row['background_filename'] = line.split(',')[2].replace('"', '').strip()
                                    break
                        except Exception:
                            pass
                    return _json(self, 200, row)
                return _json(self, 404, {"error": "not found"})
            except Exception as exc:
                return _json(self, 502, {"error": str(exc)})

        if u.path.startswith("/api/beatmap_osu/"):
            bid = u.path[len("/api/beatmap_osu/"):]
            cache_osu = CACHE / "osu" / f"{bid}.osu"
            try:
                if cache_osu.is_file():
                    text = cache_osu.read_text(encoding="utf-8", errors="replace")
                else:
                    text = fetch_osu_text(bid)
                    cache_osu.parent.mkdir(parents=True, exist_ok=True)
                    cache_osu.write_text(text, encoding="utf-8")
                raw = text.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
                return
            except Exception as exc:
                return _json(self, 502, {"error": str(exc)})

        if u.path.startswith("/api/audio/"):
            rest = u.path[len("/api/audio/"):]
            parts = rest.split("/", 1)
            if len(parts) != 2:
                return _json(self, 400, {"error": "need /api/audio/{sid}/{filename}"})
            sid, filename = parts
            # Log on ARRIVAL, before any work: a request that never reaches here leaves no
            # trace at all, and telling "the browser never connected" apart from "the handler
            # failed" is the whole question when a client reports `Failed to fetch`.
            _api_log(f"audio -> sid={sid} name={filename!r} client={self.client_address[0]} "
                     f"ua={self.headers.get('User-Agent','')[:40]!r}")
            filename = unquote(filename)
            cached = audio_cache_path(CACHE, sid, filename)
            if cached.is_file() and not looks_like_audio(cached):
                cached.unlink()
            # Fetch (if needed) inside the try, then serve OUTSIDE it: once _serve_file has
            # sent a status line a later exception must not try to send a 502 on top of it.
            try:
                if not cached.is_file():
                    fetch_audio(sid, filename, cached)
                    src = "fetched"
                else:
                    src = f"cache:{cached.name}"
            except Exception as exc:
                _api_log(f"audio 502 sid={sid} name={filename!r} client={self.client_address[0]} err={exc!r}")
                return _json(self, 502, {"error": str(exc)})
            ctype = "audio/mpeg" if filename.endswith(".mp3") else "audio/ogg" if filename.endswith(".ogg") else "audio/wav"
            _api_log(f"audio 200 sid={sid} name={filename!r} bytes={cached.stat().st_size} from={src} "
                     f"range={self.headers.get('Range')!r} client={self.client_address[0]}")
            _serve_file(self, cached, ctype)
            return

        if u.path.startswith("/api/bg/"):
            rest = u.path[len("/api/bg/"):]
            parts = rest.split("/", 1)
            if len(parts) != 2:
                return _json(self, 400, {"error": "need /api/bg/{sid}/{filename}"})
            sid, filename = parts
            filename = unquote(filename)
            try:
                from .fetch import get_background
                cached = get_background(sid, filename, CACHE)
            except Exception as exc:
                return _json(self, 502, {"error": str(exc)})
            import mimetypes
            ctype = mimetypes.guess_type(cached.name)[0] or "application/octet-stream"
            _serve_file(self, cached, ctype)
            return

        if u.path == "/api/jobs":
            with JOBS_LOCK:
                items = [{k: v for k, v in j.items() if k != "osr_path"} for j in JOBS.values()]
            return _json(self, 200, {"jobs": items})
        if u.path.startswith("/api/jobs/"):
            jid = u.path.rsplit("/", 1)[-1]
            with JOBS_LOCK:
                job = JOBS.get(jid)
            if not job:
                return _json(self, 404, {"error": "no job"})
            return _json(self, 200, {k: v for k, v in job.items() if k != "osr_path"})
        if u.path.startswith("/api/download/"):
            jid = u.path.rsplit("/", 1)[-1]
            with JOBS_LOCK:
                job = JOBS.get(jid)
            if not job or job.get("state") != "done":
                return _json(self, 404, {"error": "not ready"})
            p = Path(job["output"])
            if not p.is_file():
                return _json(self, 404, {"error": "missing file"})
            # Range-capable and streamed: the page's own preview player cannot seek without
            # it, and a QQ/OneBot client that resumes needs it too.
            _serve_file(self, p, "video/mp4",
                        {"Content-Disposition": f'attachment; filename="{p.name}"'})
            return
        _json(self, 404, {"error": "not found"})

    def do_POST(self):
        u = urlparse(self.path)
        if u.path.startswith("/api/webgl-stream/"):
            # The page's WebCodecs export streams Annex-B H.264 here as it is encoded,
            # instead of holding ~200 MB in the tab and handing over one blob at the end.
            # Appending is safe because the page serialises its own requests -- and because
            # each request now carries the byte offset it is writing at (see _append_stream).
            job_id = u.path.rsplit("/", 1)[-1]
            if not re.fullmatch(r"[0-9a-zA-Z_-]{1,64}", job_id):
                return _json(self, 400, {"error": "bad job id"})
            n = int(self.headers.get("Content-Length") or 0)
            qs = parse_qs(u.query)
            done = qs.get("done", ["0"])[0] == "1"
            try:
                offset = int(qs.get("offset", ["-1"])[0])
            except ValueError:
                offset = -1
            # Traced on arrival AND on completion. The page's side of a failure here is the
            # browser's opaque `TypeError: Failed to fetch`, which says nothing about
            # whether the request reached the server, how much of the body arrived, or how
            # far the file got -- and those are the only three things that tell a client
            # failure apart from a server one.
            _api_log(f"stream -> job={job_id} len={n} offset={offset} done={int(done)}")
            try:
                body = self.rfile.read(n) if n else b""
            except OSError as exc:
                # Whatever did arrive is still on disk; the page's retry at the same offset
                # truncates it and rewrites the batch.
                _api_log(f"stream read-failed job={job_id} err={exc!r}")
                body = b""
            out = CACHE / "renders" / f"{job_id}.h264"
            out.parent.mkdir(parents=True, exist_ok=True)
            try:
                total = _append_stream(out, offset, body)
            except StreamGap as exc:
                _api_log(f"stream 409 job={job_id} {exc}")
                return _json(self, 409, {"error": f"offset gap: {exc}"})
            except OSError as exc:
                # An unhandled OSError here closes the socket with no status line, which the
                # page reports as the opaque `Failed to fetch`.
                _api_log(f"stream 500 job={job_id} got={len(body)}/{n} offset={offset} err={exc!r}")
                return _json(self, 500, {"error": f"写流失败: {exc}"})
            _api_log(f"stream ok  job={job_id} got={len(body)}/{n} offset={offset} "
                     f"total={total} done={int(done)}")
            if done:
                with JOBS_LOCK:
                    job = JOBS.setdefault(job_id, {"id": job_id})
                    job["stream_done"] = True
                    job["stream_path"] = str(out)
            return _json(self, 200, {"received": len(body), "offset": total, "done": done})
        if u.path == "/api/skin_scroll":
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}")
            try:
                set_scroll_for_skin(str(body["skin"]), float(body["scroll"]))
            except Exception as exc:
                return _json(self, 400, {"error": str(exc)})
            return _json(self, 200, {"ok": True})
        if u.path == "/api/resolve_osr":
            n = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(n)
            fields, files = _multipart_fields(body, self.headers.get("Content-Type") or "")
            if "osr" not in files:
                return _json(self, 400, {"error": "缺少 osr 文件"})
            fn, data = files["osr"]
            tmp = CACHE / "osr" / f"resolve_{uuid.uuid4().hex}.osr"
            tmp.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_bytes(data)
            try:
                head, replay = parse_osr(tmp)
                bid = lookup_bid_by_md5(head.beatmap_md5 or "", CACHE)
                # return full replay data for web renderer
                return _json(self, 200, {
                    "bid": bid or "",
                    "md5": head.beatmap_md5 or "",
                    "username": head.username or "",
                    "presses": [{"time": p.time_ms, "key": p.column} for p in replay.presses],
                    "releases": [{"time": p.time_ms, "key": p.column} for p in replay.releases],
                    "press_count": len(replay.presses),
                    # Mirror is a play-time transform: the beatmap file is unmirrored, so
                    # the page has to flip its hit objects to line the presses up.
                    "mirror": head.mirror,
                    "mods": head.mods,
                    # The score's own judgement counts (lazer's names), and which
                    # client wrote the replay.  Together they decide the object
                    # model — osu!stable counts a hold once, osu!lazer twice — and
                    # pin the HUD's final accuracy to the game's rather than to an
                    # approximation of it.  See mania_render/judge.py.
                    "counts": head.counts,
                    "classic": replay.classic,
                    "found": bool(bid),
                })
            except Exception as exc:
                return _json(self, 400, {"error": str(exc)})
            finally:
                try:
                    tmp.unlink()
                except Exception:
                    pass
        if u.path == "/api/render":
            n = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(n)
            ctype = self.headers.get("Content-Type") or ""
            # Accept all three shapes. `aiohttp.FormData` with no file field is NOT
            # multipart (is_multipart is False), so an API client sending a plain
            # bid/skin/... form arrives as x-www-form-urlencoded — parsing only multipart
            # made every text-only request fail with "需要谱面 ID".
            if "multipart/form-data" in ctype:
                fields, files = _multipart_fields(body, ctype)
            elif "application/x-www-form-urlencoded" in ctype:
                fields = {k: v[0] for k, v in parse_qs(body.decode("utf-8", "replace")).items()}
                files = {}
            elif "application/json" in ctype:
                try:
                    raw = json.loads(body or b"{}") or {}
                except Exception as exc:
                    return _json(self, 400, {"error": f"JSON 解析失败: {exc}"})
                fields = {k: str(v) for k, v in raw.items() if v is not None}
                files = {}
            else:
                return _json(self, 415, {
                    "error": "Content-Type 需要 multipart/form-data、"
                             "application/x-www-form-urlencoded 或 application/json"
                })
            bid = (fields.get("bid") or "").strip()
            skin_key = fields.get("skin") or default_skin_key() or next(iter(SKINS))
            scroll = float(fields.get("scroll") or DEFAULT_SCROLL)
            # 60 fps is the default the page encodes at (WC_FPS in mania-web/src/main.js).
            fps = int(fields.get("fps") or 60)
            width = int(fields.get("width") or DEFAULT_WIDTH)
            height = int(fields.get("height") or DEFAULT_HEIGHT)
            # Video bitrate in kbps. Like width/height: a request field, a server-side
            # default (MANIA_BITRATE), and the page told explicitly what to encode at.
            bitrate_kbps = int(fields.get("bitrate_kbps") or DEFAULT_BITRATE_KBPS)
            dim = fields.get("bg_dim")
            bg_dim = float(dim) if dim not in (None, "") else 0.6
            bg_dim = min(1.0, max(0.0, bg_dim))
            range_s = (fields.get("range") or "").strip() or None
            lead = fields.get("lead_in")
            lead_in = float(lead) if lead not in (None, "") else None
            osr_path = None
            if "osr" in files:
                fn, data = files["osr"]
                if data:
                    osr_dir = CACHE / "osr"
                    osr_dir.mkdir(parents=True, exist_ok=True)
                    osr_path = osr_dir / f"{uuid.uuid4().hex}_{Path(fn).name}"
                    osr_path.write_bytes(data)
            # osr 自带谱面 MD5 — 未填 bid 时自动反查
            if not bid and osr_path:
                try:
                    head, _ = parse_osr(osr_path)
                    resolved = lookup_bid_by_md5(head.beatmap_md5 or "", CACHE)
                    if resolved:
                        bid = resolved
                except Exception:
                    pass
            if not bid or not bid.isdigit():
                return _json(self, 400, {"error": "需要谱面 ID（或上传 .osr 自动识别）"})
            engine = (fields.get("engine") or DEFAULT_ENGINE).strip().lower()
            if engine not in ENGINES:
                return _json(self, 400, {"error": f"engine 只能是 {' / '.join(ENGINES)}"})
            set_scroll_for_skin(skin_key, scroll)
            job_id = uuid.uuid4().hex[:12]
            with JOBS_LOCK:
                JOBS[job_id] = {
                    "id": job_id, "state": "queued", "message": "排队中", "percent": 0,
                    "bid": bid, "skin": skin_key, "scroll": scroll, "fps": fps,
                    "width": width, "height": height, "bg_dim": bg_dim,
                    "bitrate_kbps": bitrate_kbps,
                    "range": range_s, "replay": bool(osr_path), "engine": engine,
                }
            threading.Thread(
                target=_dispatch_job, daemon=True,
                args=(engine, job_id, bid, skin_key, scroll, fps, range_s, lead_in, osr_path,
                      bg_dim, width, height, bitrate_kbps),
            ).start()
            return _json(self, 200, {"id": job_id, "job": JOBS[job_id]})
        _json(self, 404, {"error": "not found"})


def main(host: str = "127.0.0.1", port: int = 8760) -> int:
    CACHE.mkdir(parents=True, exist_ok=True)
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"mania-render web: http://{host}:{port}")

    # Also answer on the IPv6 loopback. `localhost` resolves to ::1 FIRST on Windows, while
    # this server used to bind only the IPv4 loopback — so a browser opening
    # http://localhost:8760 had to fail on ::1 and fall back on every single request. The
    # fallback is what a large body (an 11 MB audio file) does not survive, and a failed
    # connection never reaches a handler, so nothing appeared in any log: the page just
    # reported the browser's opaque `TypeError: Failed to fetch`. Both binds stay on
    # loopback, so this still exposes nothing off-machine.
    httpd6 = None
    if host in ("127.0.0.1", "localhost"):
        try:
            class _ThreadingHTTPServerV6(ThreadingHTTPServer):
                address_family = socket.AF_INET6
            httpd6 = _ThreadingHTTPServerV6(("::1", port), Handler)
            threading.Thread(target=httpd6.serve_forever, daemon=True).start()
            print(f"  also            : http://[::1]:{port}")
        except OSError as exc:
            print(f"  (ipv6 loopback not bound: {exc})")
    print(f"  skins      : {skins_root()}  ({len(SKINS)} registered, default {default_skin_key()!r})")
    print(f"  cache      : {CACHE}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
