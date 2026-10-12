"""Integration check against the installed official JVM renderer (OSR and MR)."""
import hashlib
import json
import lzma
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from mania_render import osz, webapp
from mania_render.mrm_render import render
from mania_render.renderer import _find_ffmpeg
from test_malody_input import mc, mr, package


def osr(md5):
    def string(value):
        raw = value.encode()
        return b'\x0b' + bytes([len(raw)]) + raw
    actions = '0|0|0|0,1000|1|0|0,100|0|0|0,400|2|0|0,750|10|0|0,50|2|0|0,200|0|0|0,100|0|0|0,-12345|0|0|0,'
    blob = lzma.compress(actions.encode(), format=lzma.FORMAT_ALONE)
    return (struct.pack('<Bi',3,20240101) + string(md5) + string('Tester') + string('hash')
            + struct.pack('<6HiHBi',0,0,0,3,0,0,1000000,3,1,0) + b'\0'
            + struct.pack('<qi',0,len(blob)) + blob + struct.pack('<q',0))


class MRMTests(unittest.TestCase):
    def test_dispatch_selects_actual_mrm_and_preserves_om_engines(self):
        with (patch.object(webapp,'_run_job_mrm') as mrm,
              patch.object(webapp,'_run_job_webgl') as webgl,
              patch.object(webapp,'_run_job') as pillow):
            webapp._dispatch_job('mrm','test')
            mrm.assert_called_once_with('test')
            webgl.assert_not_called()
            webapp._dispatch_job('webgl','om')
            webgl.assert_called_once_with('om')
            webapp._dispatch_job('python','fallback')
            pillow.assert_called_once_with('fallback')

    def test_native_mr_and_osr_render_with_upstream_judger(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            wav = root/'song.wav'
            with wave.open(str(wav),'wb') as audio:
                audio.setnchannels(1)
                audio.setsampwidth(2)
                audio.setframerate(22050)
                audio.writeframes(b'\0\0'*22050*5)
            chart = mc(offset=0)
            with patch.object(osz,'ROOT',root/'packages'):
                maps,_ = osz.import_package(package([('map.mc',chart),('song.wav',wav.read_bytes())]))
                bid=maps[0]['beatmap_id']
                path=root/'play.mr'
                path.write_bytes(mr(hashlib.md5(chart).hexdigest(),mods=16))
                summary=render(bid,path,root,root/'mr-work',root/'mr.mp4',_find_ffmpeg(),width=270,height=480)
                self.assertEqual(summary['rate'],1.2)
                self.assertEqual(summary['counts'],[3,0,0,0,0,0])
                chart_bytes=osz.asset(bid,'map.osu').read_bytes()
                path=root/'play.osr'
                path.write_bytes(osr(hashlib.md5(chart_bytes).hexdigest()))
                # Import a real osu package so MD5 lookup uses the osu source hash.
                maps,_=osz.import_package(package([('map.osu',chart_bytes),('song.wav',wav.read_bytes())]))
                summary=render(maps[0]['beatmap_id'],path,root,root/'osr-work',root/'osr.mp4',
                               _find_ffmpeg(),width=270,height=480,range_s='1-2')
                self.assertEqual(summary['rate'],1)
                self.assertEqual(summary['counts'],[3,0,0,0,0,0])
                for kind in ('mr','osr'):
                    self.assertGreater((root/f'{kind}.mp4').stat().st_size,1000)
                    audit=json.loads((root/f'{kind}-work/summary.json').read_text())
                    self.assertEqual(audit['engine'],'Mania-Replay-Master v2.4.0')


if __name__ == '__main__':
    unittest.main()
