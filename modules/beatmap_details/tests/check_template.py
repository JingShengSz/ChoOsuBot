"""Render a saved analysis summary through the real Detail Pro HTML template."""
import sys
import shutil
import json
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'renderer'))
from mania_render.cdp import CDP

def check(source: Path, null_types=False):
    with tempfile.TemporaryDirectory() as directory:
        work = Path(directory)
        shutil.copy2(source, work / 'data.js')
        if null_types:
            data=json.loads(source.read_text(encoding='utf-8').removeprefix('window.BEATMAP_DETAILS = ').strip().removesuffix(';'))
            data['sunnyWindow']['typePercentageData']=None
            (work/'data.js').write_text('window.BEATMAP_DETAILS = '+json.dumps(data)+';',encoding='utf-8')
        shutil.copy2(ROOT / 'modules/beatmap_details/runtime/details.html', work / 'details.html')
        cdp = CDP(timeout=10).connect()
        try:
            session = cdp.attach_page()
            cdp.call('Page.enable', session=session)
            cdp.call('Page.addScriptToEvaluateOnNewDocument', {
                'source': "window.detailErrors=[];window.addEventListener('error',e=>detailErrors.push(e.message+' at '+e.lineno));"
            }, session=session)
            cdp.call('Emulation.setDeviceMetricsOverride', {
                'width':1580,'height':1200,'deviceScaleFactor':1,'mobile':False
            }, session=session)
            cdp.call('Page.navigate', {'url':(work / 'details.html').as_uri()}, session=session)
            deadline=time.monotonic()+5
            while time.monotonic() < deadline:
                status=cdp.evaluate("({url:location.href,ready:document.readyState,pages:document.querySelectorAll('.page').length,errors:window.detailErrors||[]})", session=session)
                if status['url']==(work / 'details.html').as_uri() and status['ready']=='complete':
                    break
                time.sleep(.05)
            print(status)
            assert not status['errors'], status['errors']
            assert status['pages']==3, 'Detail Pro must contain all three pages'
            if null_types:
                assert cdp.evaluate("document.getElementById('page2').textContent.includes('未返回 LN 分类数据')",session=session), 'Missing classification must be explained'
            assert not cdp.evaluate("Array.from(document.querySelectorAll('.page')).some(e=>e.scrollWidth>e.clientWidth)",session=session), 'Horizontal overflow'
        finally:
            cdp.close_last_target()
            cdp.close()

if __name__=='__main__':
    check(Path(sys.argv[1]), '--null-types' in sys.argv[2:])
