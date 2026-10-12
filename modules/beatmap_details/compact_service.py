"""Render the single DTL card, using the same node and Chrome as OM."""
from __future__ import annotations

import base64
import os
import math
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from .service import LOCK

ROOT = Path(__file__).resolve().parent
RUNTIME = ROOT / 'runtime'
VERSION = 'dtl-green-v2-rate'


def compact_card(bid: str, speed_rate: float=1.0) -> bytes:
    from mania_render.osz import is_local
    from mania_render.fetch import fetch_osu_text
    if not re.fullmatch(r'[1-9][0-9]{0,9}', str(bid)) and not is_local(bid):
        raise ValueError('请输入有效谱面 ID')
    if not math.isfinite(speed_rate) or not .1<=speed_rate<=3:
        raise ValueError('倍速范围为 0.1～3.0')
    speed_rate=round(speed_rate,6)
    with LOCK:
        work = ROOT / 'cache' / VERSION / str(bid) / f'rate-{speed_rate:g}'
        result = work / 'compact.png'
        if result.is_file():
            return result.read_bytes()
        work.mkdir(parents=True, exist_ok=True)
        text = fetch_osu_text(str(bid))
        if not re.search(r'^Mode\s*:\s*3\s*$', text, re.M):
            raise ValueError('dtl 只支持 osu!mania 谱面')
        osu = work / 'map.osu'
        osu.write_text(text, encoding='utf-8')
        bundled = Path.home() / '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe'
        node = os.environ.get('BEATMAP_DETAIL_NODE') or (str(bundled) if bundled.is_file() else shutil.which('node'))
        if not node:
            raise RuntimeError('详情分析服务缺少 Node.js')
        analysis = work / 'analysis.json'
        subprocess.run([node, '--loader', (RUNTIME/'loader.mjs').as_uri(), str(RUNTIME/'analyze.mjs'),
                        str(osu),str(analysis),str(bid),str(speed_rate)],check=True,timeout=150,capture_output=True)
        subprocess.run([node,'--loader',(RUNTIME/'loader.mjs').as_uri(),str(RUNTIME/'pattern_segments.mjs'),
                        str(osu),str(work/'pattern_segments.json'),'10',str(speed_rate)],check=True,timeout=150,capture_output=True)
        subprocess.run([sys.executable,str(RUNTIME/'build_data.py'),str(analysis),str(work)],
                       check=True,timeout=30,capture_output=True)
        assets = work / 'assets'
        (assets/'dan_icons').mkdir(parents=True,exist_ok=True)
        (assets/'characters').mkdir(exist_ok=True)
        for name in ('detail_green.css','detail_ranks.js'):
            shutil.copy2(ROOT/'assets'/name,assets/name)
        for source in (ROOT/'assets/dan_icons').glob('*.webp'):
            shutil.copy2(source,assets/'dan_icons'/source.name)
        shutil.copy2(ROOT/'assets/dan_icons/icon_manifest.js',assets/'dan_icons/icon_manifest.js')
        shutil.copy2(ROOT/'assets/characters/detail_green.png',assets/'characters/detail_green.png')
        html = (RUNTIME/'compact.html').read_text(encoding='utf-8').replace('../../assets/','assets/')
        fonts = (ROOT/'upstream/ManiaMapAnalyser by Leo_Black/styles/fonts').as_uri()
        html = html.replace('../../upstream/ManiaMapAnalyser%20by%20Leo_Black/styles/fonts',fonts)
        (work/'compact.html').write_text(html,encoding='utf-8')
        raw = render_card(work)
        temp = result.with_suffix('.tmp')
        temp.write_bytes(raw)
        temp.replace(result)
        return raw


def render_card(work: Path) -> bytes:
    from mania_render.cdp import CDP
    cdp = CDP(timeout=60).connect()
    try:
        session = cdp.attach_page((work/'compact.html').as_uri())
        cdp.call('Emulation.setDeviceMetricsOverride',{'width':1920,'height':1080,
                 'deviceScaleFactor':1,'mobile':False},session=session)
        deadline = time.monotonic()+30
        while not cdp.evaluate('!!document.querySelector("#density-chart path")',session=session):
            if time.monotonic()>deadline:
                raise RuntimeError('DTL 卡片模板加载失败')
            time.sleep(.1)
        cdp.evaluate('document.fonts.ready',session=session,await_promise=True)
        status = cdp.evaluate('(()=>{const c=document.getElementById("card");return {width:c.scrollWidth-c.clientWidth,height:c.scrollHeight-c.clientHeight,images:[...document.images].every(i=>i.complete&&i.naturalWidth>0)};})()',session=session)
        if status['width'] or status['height'] or not status['images']:
            raise RuntimeError('DTL 卡片越界或素材加载失败')
        clip = cdp.evaluate('(()=>{const r=document.getElementById("card").getBoundingClientRect();return {x:r.x+scrollX,y:r.y+scrollY,width:r.width,height:r.height,scale:1};})()',session=session)
        shot = cdp.call('Page.captureScreenshot',{'format':'png','captureBeyondViewport':True,'clip':clip},session=session)
        return base64.b64decode(shot['data'])
    finally:
        cdp.close_last_target()
        cdp.close()
