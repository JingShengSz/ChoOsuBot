"""MRM job adapter: invoke the official JVM renderer, never the OM/WebGL page."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
RELEASE_URL = 'https://github.com/Mania-Visualization-Project/Mania-Replay-Master/releases/download/v2.4.0/ManiaReplayMaster.v2.4.0.zip'
RELEASE_SHA256 = '55728dffca585bbba1c23e9da6de034f3464baa40a43bc51827c6f98529f250b'
JAR_SHA256 = '605b546d1b385431b278386ebb5c22fdd429f34ca10ede6ef530a17801ae3e1d'


def java_tool(name='java') -> str:
    executable = name + ('.exe' if os.name == 'nt' else '')
    candidates = [Path(os.environ.get('JAVA_HOME', '')) / 'bin' / executable]
    if shutil.which(name):
        candidates.append(Path(shutil.which(name)))
    if os.name == 'nt':
        candidates += sorted(Path('C:/Program Files/Eclipse Adoptium').glob(f'jdk-*/bin/{executable}'), reverse=True)
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    raise RuntimeError('MRM 需要 Java JDK，请安装 JDK 后运行 tools/setup_mrm.py')


def runtime() -> tuple[Path, Path]:
    home = Path(os.environ.get('MANIA_MRM_HOME') or ROOT / 'vendor/mania-replay-master')
    jar = home / 'ManiaReplayMaster.jar'
    source = ROOT / 'mrm_bridge/Bridge.java'
    stamp = home / 'bridge.sha256'
    if not jar.is_file() or hashlib.sha256(jar.read_bytes()).hexdigest() != JAR_SHA256:
        raise RuntimeError('MRM 官方运行库未安装或校验不符，请运行 tools/setup_mrm.py')
    if not stamp.is_file() or stamp.read_text().strip() != hashlib.sha256(source.read_bytes()).hexdigest():
        raise RuntimeError('MRM 适配器需要编译，请运行 tools/setup_mrm.py')
    if not (home / 'classes/cho/mrm/Bridge.class').is_file():
        raise RuntimeError('MRM 适配器未安装，请运行 tools/setup_mrm.py')
    return jar, home / 'classes'


def _run(command, work: Path, timeout: float, progress):
    # One process per job isolates upstream Config.INSTANCE and temporary strips.
    # Kill the JVM's FFmpeg child too on timeout, otherwise it keeps consuming resources.
    with (work / 'process.log').open('ab') as log:
        process = subprocess.Popen(command, cwd=work, stdout=log, stderr=log,
                                   start_new_session=os.name != 'nt')
        started = time.monotonic()
        previous = None
        try:
            while process.poll() is None:
                if time.monotonic() - started > timeout:
                    raise TimeoutError('MRM 渲染超时')
                try:
                    percent = float((work / 'progress.txt').read_text())
                    if percent != previous:
                        progress(min(94, 5 + percent * .89), 'Mania-Replay-Master 渲染中')
                        previous = percent
                except (OSError, ValueError):
                    pass
                time.sleep(.5)
            if process.returncode:
                tail = (work / 'process.log').read_text(encoding='utf-8', errors='replace')[-2500:]
                raise RuntimeError(f'MRM 渲染失败（{process.returncode}）：{tail}')
        finally:
            if process.poll() is None:
                if os.name == 'nt':
                    subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True)
                else:
                    import signal
                    os.killpg(process.pid, signal.SIGKILL)
                process.wait()


def render(bid: str, replay_path: Path, cache: Path, work: Path, out: Path,
           ffmpeg: str, *, scroll=20, fps=60, width=540, height=960,
           range_s=None, timeout=1800, progress=lambda pct, message: None) -> dict:
    from . import osz
    from .fetch import load_beatmap_by_id, parse_range
    from .replay_input import resolve_replay

    if not replay_path:
        raise ValueError('Mania-Replay-Master 需要回放文件')
    if not (64 <= width <= 1920 and 64 <= height <= 1920 and width % 2 == height % 2 == 0):
        raise ValueError('MRM 分辨率需为 64–1920 之间的偶数')
    if not (10 <= fps <= 120 and 1 <= scroll <= 100):
        raise ValueError('MRM 帧率需为 10–120，滚动速度需为 1–100')
    jar, classes = runtime()
    data = resolve_replay(replay_path, cache, bid)
    bm, audio, _ = load_beatmap_by_id(bid, cache)
    if bm.mode != 3:
        raise ValueError('v 只支持 mania 谱面')
    chart = osz.asset(bid, 'map.osu') if osz.is_local(bid) else cache / 'osu' / f'{bid}.osu'
    if replay_path.suffix == '.osr':
        if osz.is_local(bid):
            hashes = {osz.manifest(bid)['meta']['chart_md5']}
        else:
            raw = chart.read_bytes()
            lf = raw.replace(b'\r\n', b'\n')
            # The fetch cache is text; Windows newline conversion changes raw bytes.
            hashes = {hashlib.md5(body).hexdigest() for body in (raw, lf, lf.replace(b'\n', b'\r\n'))}
        if data['md5'] not in hashes:
            raise ValueError('指定谱面与 OSR 的 MD5 不一致，请提供对应谱面包')
    work.mkdir(parents=True, exist_ok=False)
    out.parent.mkdir(parents=True, exist_ok=True)
    # MRM 2.4.0 parses blank/comment lines inside HitObjects as notes. Strip only
    # these lines in a job-local copy, after checking the original file's MD5.
    staged_chart = work / 'chart.osu'
    staged_chart.write_text('\n'.join(line for line in chart.read_text(encoding='utf-8-sig').splitlines()
                                      if line.strip() and not line.lstrip().startswith('//')) + '\n', encoding='utf-8')
    payload = dict(map=str(staged_chart.resolve()), audio=str(audio.resolve()),
                   replay=str(replay_path.resolve()), work=str(work.resolve()),
                   ffmpeg=ffmpeg, width=width, height=height, scroll=round(scroll), fps=fps,
                   platform=data.get('platform', 'pc'), format=replay_path.suffix[1:],
                   shift_ms=osz.manifest(bid)['meta'].get('replay_shift_ms', 0) if osz.is_local(bid) else 0,
                   resolved=data if replay_path.suffix == '.mrv' else {})
    request = work / 'input.json'
    request.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
    started = time.monotonic()
    progress(5, '调用 Mania-Replay-Master 官方 JVM 渲染器')
    _run([java_tool(), '-Xmx1g', '-Djava.awt.headless=true', '-Dfile.encoding=UTF-8',
          '-cp', os.pathsep.join((str(classes), str(jar))), 'cho.mrm.Bridge', str(request.resolve())],
         work, timeout, progress)
    summary = json.loads((work / 'summary.json').read_text())
    start, end = parse_range(range_s) if range_s else (0, summary['duration'])
    end = min(end, summary['duration'])
    if end <= start:
        raise ValueError('片段范围超出回放时间')
    progress(95, '裁剪 MRM 视频并整理音频')
    # Upstream encodes complete image-strip batches; cap their trailing black padding.
    _run([ffmpeg, '-y', '-ss', str(start + 1), '-i', str(work / 'mrm.mp4'), '-t', str(end-start),
          '-c:v', 'libx264', '-preset', 'fast', '-crf', '23', '-pix_fmt', 'yuv420p',
          '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart', str(out.resolve())],
         work, max(1, timeout - (time.monotonic()-started)), lambda pct, msg: None)
    if not out.is_file() or out.stat().st_size == 0:
        raise RuntimeError('MRM 没有生成可用视频')
    # Retain the small audit summary/log, discard private replay payload and large strips.
    request.unlink(missing_ok=True)
    for path in work.glob('strips_*'):
        path.unlink()
    (work / 'mrm.mp4').unlink(missing_ok=True)
    return summary
