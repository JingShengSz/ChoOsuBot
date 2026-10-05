"""Beatmap backgrounds and 30-second audio at the map's PreviewTime."""
import csv
import json
from io import BytesIO
from pathlib import Path
import shutil
import subprocess
import urllib.parse
import urllib.request
import zipfile

import osu_api


def map_media_info(text):
    info = {}
    section = ''
    for line in text.splitlines():
        line = line.strip()
        if line.startswith('['):
            section = line
        elif section in ('[General]', '[Metadata]') and ':' in line:
            key, value = line.split(':', 1)
            if key in ('AudioFilename', 'PreviewTime', 'BeatmapSetID'):
                info[key] = value.strip()
        elif section == '[Events]' and line and not line.startswith('//'):
            fields = next(csv.reader([line]))
            if len(fields) >= 3 and fields[0] in ('0', 'Background'):
                info.setdefault('background', fields[2])
    return info


class BeatmapMedia:
    def __init__(self, directory, proxy=''):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.proxy = proxy

    def download(self, url, limit=100 * 1024 * 1024):
        opener = urllib.request.build_opener(urllib.request.ProxyHandler(osu_api.effective_proxies(self.proxy)))
        with opener.open(urllib.request.Request(url, headers={'User-Agent': 'mania-render/0.1'}), timeout=25) as response:
            data = response.read(limit + 1)
        if len(data) > limit:
            raise RuntimeError('谱面媒体文件过大')
        if data.lstrip().startswith((b'<!DOCTYPE', b'<html')):
            raise RuntimeError('下载返回了网页')
        return data

    def info(self, bid):
        path = self.directory / f'{int(bid)}.json'
        if path.exists():
            return json.loads(path.read_text('utf-8'))
        info = map_media_info(osu_api.fetch_beatmap_file(bid, proxy=self.proxy))
        if not info.get('BeatmapSetID') or int(info['BeatmapSetID']) <= 0:
            raise RuntimeError('谱面没有有效的谱面集 ID')
        path.write_text(json.dumps(info, ensure_ascii=False), 'utf-8')
        return info

    def asset(self, info, filename):
        sid = int(info['BeatmapSetID'])
        name = urllib.parse.quote(filename, safe='')
        for url in (f'https://dl.sayobot.cn/beatmaps/files/{sid}/{name}',
                    f'https://api.nerinyan.moe/d/{sid}/{name}'):
            try:
                return self.download(url)
            except Exception:
                pass
        for url in (f'https://api.nerinyan.moe/d/{sid}?noVideo=1', f'https://catboy.best/d/{sid}'):
            try:
                with zipfile.ZipFile(BytesIO(self.download(url))) as archive:
                    match = next(n for n in archive.namelist() if n.replace('\\', '/').casefold() == filename.replace('\\', '/').casefold())
                    if archive.getinfo(match).file_size > 100 * 1024 * 1024:
                        raise RuntimeError('媒体文件过大')
                    return archive.read(match)
            except Exception:
                pass
        raise RuntimeError('暂时无法下载谱面媒体文件')

    def background(self, bid):
        info = self.info(bid)
        filename = info.get('background')
        if not filename:
            raise RuntimeError('谱面没有背景图片')
        path = self.directory / f'{int(bid)}_bg{Path(filename).suffix or ".jpg"}'
        if not path.exists():
            from PIL import Image
            data = self.asset(info, filename)
            Image.open(BytesIO(data)).verify()
            path.write_bytes(data)
        return path

    def song(self, bid):
        path = self.directory / f'{int(bid)}_preview.wav'
        if path.exists():
            return path
        ffmpeg = shutil.which('ffmpeg')
        if not ffmpeg:
            raise RuntimeError('服务器缺少 ffmpeg，无法生成语音预览')
        info = self.info(bid)
        filename = info.get('AudioFilename')
        if not filename:
            raise RuntimeError('谱面没有音乐文件')
        audio = self.directory / f'{int(bid)}_audio{Path(filename).suffix or ".mp3"}'
        if not audio.exists():
            audio.write_bytes(self.asset(info, filename))
        start = int(info.get('PreviewTime', -1)) / 1000
        probe = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', str(audio)], capture_output=True, text=True, timeout=20, check=True)
        duration = float(probe.stdout.strip())
        if start < 0 or start > duration:
            # osu! defaults an unspecified preview to 40% of track duration.
            start = duration * .4
        temporary = path.with_suffix('.tmp.wav')
        try:
            subprocess.run([ffmpeg, '-v', 'error', '-y', '-ss', str(start), '-i', str(audio), '-af', 'apad', '-t', '30', '-ac', '1', '-ar', '24000', str(temporary)], capture_output=True, timeout=60, check=True)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
        return path
