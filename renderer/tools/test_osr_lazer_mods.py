"""Complete lazer mods/settings must survive the legacy OSR envelope."""
import json
import lzma
from pathlib import Path
import struct
import sys
import tempfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mania_render.osr import parse_osr
from test_osr_sentinel import build_osr

with tempfile.TemporaryDirectory() as directory:
    target=Path(directory)/'mods.osr'
    for acronym, expected in [('DT',1.5),('NC',1.5),('HT',.75),('DC',.75)]:
        for custom in [None,1.2,.5]:
            mods=[{'acronym':acronym,'settings':{} if custom is None else {'speed_change':custom}}, {'acronym':'HO'}]
            extra=lzma.compress(json.dumps({'mods':mods,'statistics':{'perfect':70000,'great':123},'maximum_statistics':{'perfect':70123}}).encode(),format=lzma.FORMAT_ALONE)
            data=bytearray(build_osr('0|256|-500|0,-1|256|-500|0,10|1|0|0,10|0|0|0',64))
            struct.pack_into('<i',data,1,30000016)
            data+=struct.pack('<qi',1,len(extra))+extra
            target.write_bytes(data)
            head,replay=parse_osr(target)
            assert head.clock_rate==(expected if custom is None else custom)
            assert head.counts['perfect']==70000,'Extended counters override UInt16 legacy fields'
            assert len(replay.presses)==1 and replay.presses[0].time_ms==9
            assert not replay.classic and head.mods_detail==mods
    for bits,expected in [(0,1),(64,1.5),(512,1.5),(256,.75)]:
        target.write_bytes(build_osr('0|1|0|0,10|0|0|0',bits))
        head,replay=parse_osr(target)
        assert head.clock_rate==expected and replay.classic
print('PASS: lazer extended DT/NC/HT/DC custom speed, HO, full statistics, unchanged replay timestamps, legacy fallback')
