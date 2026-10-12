"""Generate the three Detail Pro pages on the local OM render node."""
from __future__ import annotations
import base64
import io
import json
import math
import re
import shutil
import subprocess
import sys
import threading
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RUNTIME = ROOT / 'runtime'
CACHE = ROOT / 'cache'
LOCK = threading.Lock()
VERSION = 'dtlp-v5-rate'

def detail_bundle(bid: str, speed_rate: float=1.0) -> bytes:
    from mania_render.osz import is_local
    if not re.fullmatch(r'[1-9][0-9]{0,9}', str(bid)) and not is_local(bid):
        raise ValueError('请输入有效谱面 ID')
    if not math.isfinite(speed_rate) or not .1<=speed_rate<=3:
        raise ValueError('倍速范围为 0.1～3.0')
    speed_rate=round(speed_rate,6)
    with LOCK:
        work = CACHE / VERSION / str(bid) / f'rate-{speed_rate:g}'
        bundle = work / 'details.zip'
        if bundle.is_file():
            return bundle.read_bytes()
        work.mkdir(parents=True, exist_ok=True)
        from mania_render.fetch import fetch_osu_text
        text = fetch_osu_text(str(bid))
        if not re.search(r'^Mode\s*:\s*3\s*$', text, re.M):
            raise ValueError('dtlp 只支持 osu!mania 谱面')
        osu = work / 'map.osu'
        osu.write_text(text, encoding='utf-8')
        node = shutil.which('node')
        if not node:
            raise RuntimeError('详情分析服务缺少 Node.js')
        output = work / 'analysis.json'
        subprocess.run([node, '--loader', (RUNTIME / 'loader.mjs').as_uri(),
                        str(RUNTIME / 'analyze.mjs'), str(osu), str(output), str(bid), str(speed_rate)],
                       check=True, timeout=150, capture_output=True)
        subprocess.run([sys.executable, str(RUNTIME / 'build_data.py'), str(output), str(work)],
                       check=True, timeout=30, capture_output=True)
        shutil.copy2(RUNTIME / 'details.html', work / 'details.html')
        pages = render_pages(work)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_STORED) as archive:
            for page in pages:
                archive.write(page, page.name)
        temp = bundle.with_suffix('.tmp')
        temp.write_bytes(buf.getvalue())
        temp.replace(bundle)
        return buf.getvalue()

def render_pages(work: Path) -> list[Path]:
    from mania_render.cdp import CDP
    cdp = CDP(timeout=60).connect()
    try:
        session = cdp.attach_page((work / 'details.html').as_uri())
        cdp.call('Emulation.setDeviceMetricsOverride',
                 {'width':1580,'height':1200,'deviceScaleFactor':1,'mobile':False},session=session)
        deadline = time.monotonic() + 30
        while not cdp.evaluate('!!document.getElementById("page3")',session=session):
            if time.monotonic() > deadline:
                raise RuntimeError('详情图模板加载失败')
            time.sleep(.1)
        cdp.evaluate('document.fonts.ready',session=session,await_promise=True)
        overflow = cdp.evaluate('Array.from(document.querySelectorAll(".page")).some(e=>e.scrollWidth>e.clientWidth)',session=session)
        if overflow:
            raise RuntimeError('详情图内容超出页面宽度')
        pages=[]
        for index in range(1,4):
            clip = cdp.evaluate(f'(()=>{{const r=document.getElementById("page{index}").getBoundingClientRect();return {{x:r.x+scrollX,y:r.y+scrollY,width:r.width,height:r.height,scale:1}};}})()',session=session)
            shot=cdp.call('Page.captureScreenshot',{'format':'png','captureBeyondViewport':True,'clip':clip},session=session)
            target=work/f'detail_{index}.png'
            target.write_bytes(base64.b64decode(shot['data']))
            pages.append(target)
        return pages
    finally:
        cdp.close_last_target()
        cdp.close()
