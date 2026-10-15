"""Exercise real FFmpeg server muxing with the scene export fixture."""
import json
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from mania_render.renderer import _find_ffmpeg
from mania_render.webgl_render import _mux_stream

work=ROOT.parent/'scratch'/'scene-flow'
t=json.loads((work/'timeline.json').read_text())
ffmpeg=_find_ffmpeg()
raw=work/'scene.h264'
subprocess.run([ffmpeg,'-y','-loglevel','error','-i',str(work/'scene-export.mp4'),'-map','0:v:0','-c:v','copy','-bsf:v','h264_mp4toannexb','-f','h264',str(raw)],check=True)
audio=work/'source.wav'
with zipfile.ZipFile(work/'scene-test.osz') as z:
    audio.write_bytes(z.read('audio.wav'))
out=work/'server-scene.mp4'
_mux_stream(ffmpeg,raw,audio,out,range_s=None,duration_s=(t['resultStart']-t['start'])/1000,audio_lead_s=-t['start']/1000,audio_end_s=t['resultStart']/1000)
assert out.stat().st_size>50000
probe=subprocess.run([ffmpeg,'-hide_banner','-i',str(out),'-f','null','-'],capture_output=True,text=True)
assert probe.returncode==0,probe.stderr[-1200:]
assert 'Audio:' in probe.stderr and 'Video:' in probe.stderr
print('PASS: server mux preserves pre-roll and music tail, excluding webpage results')
