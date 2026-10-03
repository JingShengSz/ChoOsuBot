"""Render a mania replay with the WebGL page instead of the Pillow renderer.

The page at `/` is the validated renderer: it is the one the project's visual
conformance work was checked against, and it is what a human sees in the browser.
This module drives it headlessly so a bot job can produce the same picture.

How it works
------------
1. Chromium runs with `--remote-debugging-port`; we attach over CDP.
2. A tab loads the page, picks the skin, loads the beatmap (or uploads the .osr).
3. `#btnExport` is clicked: the page encodes its own canvas with WebCodecs
   `VideoEncoder` and muxes the samples into an MP4 in-page, then hands the result to the
   download machinery. `MediaRecorder` survives only as the fallback for browsers without
   `VideoEncoder`.
4. `Browser.setDownloadBehavior` points that download at a directory we watch.

Three consequences of the export path are worth stating plainly, because they cannot be
engineered away:

* **the whole chart is encoded** — the page always exports from 0 to the end of the chart,
  so a `range` is an ffmpeg trim applied to a full-length encode, not a shorter recording;
* **the size is passed through, never rescaled here** — `window.__webglOutW`/`__webglOutH`
  make the page encode at exactly the requested size (a GPU blit from its 1920x1080
  canvases), so the mux below never has to scale. A request that carries no size at all is
  resolved by the caller (`webapp.DEFAULT_WIDTH`/`DEFAULT_HEIGHT`), not guessed here; when
  it arrives as 0x0 the page's own canvas size is what gets encoded.
* **the bitrate is set here too** — `window.__webglBitrate` is the page's encoding rate, and
  it is the only thing that decides the finished file's size. It is set from the caller's
  `bitrate_kbps` (resolved by `webapp`), never left to the page's own default, because that
  default is tuned for a human's local export rather than for a file that has to be
  uploaded to a chat platform.
"""
from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path
from typing import Callable

from .cdp import CDP, CDPError

ProgressFn = Callable[[int, str], None]

# The page is served by this same service; a job always drives its own localhost copy.
APP_URL = "http://127.0.0.1:8760/"
READY_RE = r"/就绪|错误|失败|请输入|没有|不支持/"


class WebGLRenderError(RuntimeError):
    pass


def _wait(cdp: CDP, sid: str, expr: str, *, timeout: float, what: str,
          interval: float = 0.25) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if cdp.evaluate(expr, session=sid):
            return
        time.sleep(interval)
    raise WebGLRenderError(f"等待超时：{what}")


def _set_input(cdp: CDP, sid: str, elem: str, value, event: str) -> None:
    """Set a control's value and fire the event the page listens for."""
    cdp.evaluate(
        f"(() => {{ const el = document.getElementById({elem!r});"
        f" if (!el) return false; el.value = {value!r};"
        f" el.dispatchEvent(new Event({event!r}, {{bubbles: true}})); return true; }})()",
        session=sid,
    )


def _pick_download(folder: Path, *, want: tuple[str, ...] = (".mp4", ".webm"),
                   settle: float = 1.5, timeout: float = 60.0) -> Path:
    """The finished download in `folder`, once its size has stopped changing.

    Chrome writes through a `.crdownload` temp name, so a file with a real
    extension is already complete — but `allowAndName` behaviour differs between
    builds, hence the stability check.
    """
    deadline = time.monotonic() + timeout
    last: tuple[Path, int, float] | None = None
    while time.monotonic() < deadline:
        files = [p for p in folder.iterdir()
                 if p.is_file() and p.suffix.lower() in want and not p.name.endswith(".crdownload")]
        if files:
            newest = max(files, key=lambda p: p.stat().st_mtime)
            size = newest.stat().st_size
            # Only restart the clock when the file actually changes — resetting it on every
            # poll means the "has it stopped growing" test can never come true.
            if last is None or last[0] != newest or last[1] != size:
                last = (newest, size, time.monotonic())
            elif size > 0 and time.monotonic() - last[2] >= settle:
                return newest
        time.sleep(0.25)
    raise WebGLRenderError("导出结束但下载目录里没有出现视频文件")


def render(job_id: str, bid: str, skin_key: str, *, osr_path: Path | None,
           scroll: float, bg_dim: float, range_s: str | None,
           width: int, height: int, work_dir: Path, out_path: Path,
           ffmpeg: str, progress: ProgressFn, audio_path: Path | None = None,
           bitrate_kbps: int = 0,
           chrome_host: str = "127.0.0.1", chrome_port: int = 9222,
           timeout: float = 1800.0) -> Path:
    """Render via the page and return the finished file path."""
    work_dir.mkdir(parents=True, exist_ok=True)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # A private download dir per job: the browser writes here and nothing else does.
    dl = work_dir / job_id
    if dl.exists():
        shutil.rmtree(dl, ignore_errors=True)
    dl.mkdir(parents=True, exist_ok=True)

    cdp = CDP(chrome_host, chrome_port, timeout=min(timeout, 300))
    try:
        cdp.connect()
    except Exception as exc:
        raise WebGLRenderError(
            f"连不上无头 Chrome（{chrome_host}:{chrome_port}）：{exc}。"
            "请先启动 Chrome；有 GPU 时用这条：\n"
            "  chrome --headless=new --remote-debugging-port=9222 "
            "--user-data-dir=<空目录> --enable-gpu --use-angle=d3d11 "
            "--ignore-gpu-blocklist --enable-gpu-rasterization\n"
            "这不是可选项：同一台机器（RTX 5060）实测绘制速度 GPU 是 259 fps，"
            "--use-angle=swiftshader 只有 35 fps，差一个数量级；软件渲染在 2 核 VPS 上"
            "基本不可用。只有确实没有 GPU 时才退到 "
            "--use-gl=angle --use-angle=swiftshader --enable-unsafe-swiftshader。"
            "另：本机 avc1.42001E(Baseline) 不可用，可用档位是 avc1.640028(High)。"
        ) from exc

    sid = None
    try:
        sid = cdp.attach_page("about:blank")
        cdp.call("Page.enable", session=sid)
        cdp.call("Runtime.enable", session=sid)
        cdp.call("DOM.enable", session=sid)
        # Must go to the browser, not the page, for the download to be redirected.
        cdp.call("Browser.setDownloadBehavior", {
            "behavior": "allow", "downloadPath": str(dl.resolve()), "eventsEnabled": True,
        })

        progress(2, "打开渲染页面…")
        cdp.call("Page.navigate", {"url": APP_URL}, session=sid)
        _wait(cdp, sid, "typeof window.__mania !== 'undefined'", timeout=60, what="页面加载")

        # The HUD draws with `bold 56px system-ui`. In headless Chromium that generic
        # family resolves to something without usable digits, so combo/accuracy/BPM came
        # out as tofu boxes — visible only in the export, never in a normal browser. Pin
        # an explicit stack before anything is drawn.
        cdp.evaluate(
            "(() => {"
            "  const d = Object.getOwnPropertyDescriptor(CanvasRenderingContext2D.prototype, 'font');"
            "  if (!d || !d.set) return false;"
            "  Object.defineProperty(CanvasRenderingContext2D.prototype, 'font', {"
            "    configurable: true,"
            "    get() { return d.get.call(this); },"
            "    set(v) {"
            "      const fixed = String(v).replace(/system-ui/g,"
            "        \"'Segoe UI', Roboto, 'Noto Sans', 'DejaVu Sans', Arial, sans-serif\");"
            "      d.set.call(this, fixed);"
            "    },"
            "  });"
            "  return true;"
            "})()",
            session=sid,
        )

        # The page auto-loads the server's default skin on start; wait that out before
        # switching, otherwise the two loads race (the page guards with a token, but we
        # would still be measuring the wrong skin).
        _wait(cdp, sid, "document.getElementById('skinSel').options.length > 0",
              timeout=60, what="皮肤列表")
        _wait(cdp, sid, f"!{READY_RE}.test(document.getElementById('info').textContent)",
              timeout=300, what="默认皮肤加载")

        have = cdp.evaluate("document.getElementById('skinSel').value", session=sid)
        if skin_key and skin_key != have:
            progress(5, f"加载皮肤 {skin_key}…")
            _set_input(cdp, sid, "skinSel", skin_key, "change")
            _wait(cdp, sid,
                  f"document.getElementById('skinSel').value === {skin_key!r} && "
                  f"!{READY_RE}.test(document.getElementById('info').textContent)",
                  timeout=600, what=f"皮肤 {skin_key} 加载")

        if scroll:
            _set_input(cdp, sid, "scrollSpeed", str(scroll), "change")
        if bg_dim is not None:
            _set_input(cdp, sid, "bgDim", str(int(round(bg_dim * 100))), "input")

        progress(8, "加载谱面…")
        if osr_path is not None:
            node = cdp.call("DOM.querySelector", {
                "nodeId": cdp.call("DOM.getDocument", session=sid)["root"]["nodeId"],
                "selector": "#fOsr",
            }, session=sid).get("nodeId")
            if not node:
                raise WebGLRenderError("页面里找不到 .osr 上传控件")
            # `DOM.setFileInputFiles` fires the page's change handler, which loads the
            # replay immediately (passing the bid as the fallback id).
            if bid:
                _set_input(cdp, sid, "bidInput", bid, "input")
            cdp.call("DOM.setFileInputFiles", {"files": [str(osr_path)], "nodeId": node},
                     session=sid)
        else:
            _set_input(cdp, sid, "bidInput", bid, "input")
            cdp.evaluate("document.getElementById('btnLoad').click()", session=sid)

        _wait(cdp, sid, f"{READY_RE}.test(document.getElementById('info').textContent)",
              timeout=600, what="谱面加载")
        info = cdp.evaluate("document.getElementById('info').textContent", session=sid)
        if "错误" in info or "失败" in info or "没有" in info or "不支持" in info:
            raise WebGLRenderError(f"页面报错：{info}")
        _wait(cdp, sid, "!document.getElementById('btnExport').disabled",
              timeout=120, what="导出按钮可用")

        progress(10, "导出中…")
        # The page only takes the WebCodecs path when a job id is present; without it it
        # keeps MediaRecorder for interactive use, which needs no server involvement.
        # Size goes in through the same door: the page encodes at the FINAL size, so the
        # mux below never has to rescale (which would be a second full encode).
        if width and height:
            cdp.evaluate(f"window.__webglOutW = {int(width)}; window.__webglOutH = {int(height)}",
                         session=sid)
        # The bitrate rides the same door. It is what decides the delivered file's size,
        # and the size is what decides whether the upload channel carries it at all — the
        # page's own default (6 Mbps) is for a human exporting a local file, and produced
        # 74.8 MB for an 86 s chart here, which the adapter's channel timed out on. The
        # service resolves the rate (request `bitrate_kbps`, else MANIA_BITRATE, else
        # DEFAULT_BITRATE_KBPS); 0 means "leave the page alone", which is only reachable if
        # a caller passes nothing.
        if bitrate_kbps and int(bitrate_kbps) > 0:
            cdp.evaluate(f"window.__webglBitrate = {int(bitrate_kbps) * 1000}", session=sid)
        cdp.evaluate(f"window.__webglJobId = {job_id!r}", session=sid)
        cdp.evaluate("document.getElementById('btnExport').click()", session=sid)

        started = time.monotonic()
        last_pct = -1
        while time.monotonic() - started < timeout:
            label = cdp.evaluate(
                "document.getElementById('btnExport').textContent", session=sid) or ""
            if not label.startswith("导出中"):
                break
            digits = "".join(ch for ch in label if ch.isdigit())
            pct = int(digits) if digits else 0
            if pct != last_pct:
                last_pct = pct
                progress(10 + int(pct * 0.8), f"导出中 {pct}%")
            time.sleep(0.5)
        else:
            raise WebGLRenderError("导出超时")
        note = cdp.evaluate("document.getElementById('info').textContent", session=sid) or ""
        if note.startswith("导出失败"):
            raise WebGLRenderError(f"页面导出失败：{note}")

        # The page streams the encoded stream to the service as it goes; wait for the
        # writer to be told it is finished before handing the file to ffmpeg.
        stream = Path(out_path).parent / f"{job_id}.h264"
        _wait_for_stream(stream, timeout=180)

        progress(93, "封装视频…")
        _mux_stream(ffmpeg, stream, audio_path, out_path, range_s=range_s)
        stream.unlink(missing_ok=True)
        progress(100, "完成")
        return out_path
    finally:
        if sid:
            cdp.close_last_target()
        cdp.close()


def _range_args(range_s: str | None) -> list[str]:
    """`--from/--to` as ffmpeg arguments. The page always records the whole chart."""
    if not range_s:
        return []
    parts = str(range_s).split("-")
    try:
        start = float(parts[0] or 0)
        end = float(parts[1]) if len(parts) > 1 and parts[1] else None
    except ValueError:
        return []
    args: list[str] = []
    if start > 0:
        args += ["-ss", f"{start:.3f}"]
    if end is not None:
        args += ["-t", f"{max(0.0, end - start):.3f}"]
    return args


def _wait_for_stream(path: Path, *, timeout: float = 180.0) -> None:
    """Wait until the page has finished streaming and ffmpeg can open the file.

    The page closes the stream with a `?done=1` request; the file appearing is enough to
    mux, but the last bytes may still be in flight, so require it to stop growing.
    """
    deadline = time.monotonic() + timeout
    last = -1
    stable = 0
    while time.monotonic() < deadline:
        if path.is_file():
            size = path.stat().st_size
            stable = stable + 1 if size == last and size > 0 else 0
            last = size
            if stable >= 4:                     # ~1s without growth
                return
        time.sleep(0.25)
    raise WebGLRenderError(f"等待编码流超时（{path.name}）")


def _mux_stream(ffmpeg: str, stream: Path, audio: Path | None, dest: Path, *,
                range_s: str | None, scale: tuple[int, int] | None = None) -> None:
    """Wrap the Annex-B H.264 stream in MP4 and add the beatmap audio.

    The WebGL export carries no audio track at all (verified: the page records a canvas
    stream), so without this step every WebGL video would be silent. Video is stream-copied
    whenever nothing else is asked for, which keeps this cheap.
    """
    if not stream.is_file() or stream.stat().st_size == 0:
        raise WebGLRenderError("页面没有产出任何编码数据")
    trim = _range_args(range_s)
    # An LLBot-built ffmpeg has no `-movflags`, and a ComfyUI one does; record what was
    # actually run so a missing audio track can be traced without guessing.
    (dest.parent / f"{dest.stem}.ffmpeg.txt").write_text(
        f"audio={audio!r} exists={audio is not None and Path(audio).is_file()}\n"
        + " ".join(args_preview := [ffmpeg, "-y", "-r", "60", "-i", str(stream)]
                    + ([str(audio)] if audio is not None and Path(audio).is_file() else [])),
        encoding="utf-8")
    has_audio = audio is not None and Path(audio).is_file()
    args = [ffmpeg, "-y", "-loglevel", "error", "-r", "60", "-i", str(stream)]
    if has_audio:
        args += ["-i", str(audio), "-map", "0:v:0", "-map", "1:a:0"]
    if trim or scale:
        # A cut or a resize has to re-encode; a plain export never does.
        args += trim
        if scale:
            args += ["-vf", f"scale={scale[0]}:{scale[1]}:flags=bicubic"]
        args += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                 "-pix_fmt", "yuv420p"]
    else:
        args += ["-c:v", "copy"]
    if has_audio:
        # No `-shortest`: the video input is a raw Annex-B elementary stream with no
        # duration metadata, and asking ffmpeg to stop at the shortest input made it drop
        # the audio track entirely. The audio is the beatmap's own track and is trimmed by
        # the muxer anyway.
        args += ["-c:a", "aac", "-b:a", "192k"]
    args += ["-movflags", "+faststart", str(dest)]
    proc = subprocess.run(args, capture_output=True)
    if proc.returncode != 0 or not dest.exists():
        tail = (proc.stderr or b"")[-500:].decode("utf-8", "replace")
        raise WebGLRenderError(f"封装失败（ffmpeg rc={proc.returncode}）：{tail}")


def _post_process(ffmpeg: str, src: Path, dest: Path, *,
                  scale: tuple[int, int] | None, trim: list[str]) -> None:
    """Trim and/or rescale an already-encoded file, stream-copying what is untouched."""
    args = [ffmpeg, "-y", "-loglevel", "error"]
    args += trim
    args += ["-i", str(src)]
    if scale:
        args += ["-vf", f"scale={scale[0]}:{scale[1]}:flags=bicubic"]
        args += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                 "-pix_fmt", "yuv420p", "-c:a", "copy"]
    else:
        args += ["-c", "copy", "-avoid_negative_ts", "make_zero"]
    args += [str(dest)]
    proc = subprocess.run(args, capture_output=True)
    if proc.returncode != 0 or not dest.exists():
        tail = (proc.stderr or b"")[-400:].decode("utf-8", "replace")
        raise WebGLRenderError(f"后处理失败（ffmpeg rc={proc.returncode}）：{tail}")
    src.unlink(missing_ok=True)
