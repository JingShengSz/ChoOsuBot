"""Render the failed .r regression through the real Pillow renderer (no network)."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from card import build_card
from render import PilScoreCardRenderer
from PIL import Image

ap = argparse.ArgumentParser()
ap.add_argument('--template', type=Path, required=True)
ap.add_argument('--out', type=Path, required=True)
args = ap.parse_args()
score = {'id':7618912197, 'rank':'F', 'passed':False, 'accuracy':.469151,
         'total_score':5047, 'max_combo':13, 'ended_at':'2026-10-03T12:49:00Z',
         'user':{'username':'F6A8AF'},
         'statistics':{'ok':9,'meh':5,'good':11,'miss':15,'great':11,'perfect':4}}
data = build_card(score, {'id':4166972}, {'title':'Fail regression - score 7618912197'})
assert data.grade == 'F', data.grade
renderer = PilScoreCardRenderer(args.template / 'layer_mapping.json',
                               args.template / 'assets', args.out.parent / 'work')
jobs = [{'name':name, 'value':value, 'font':None, 'accent':None}
        for name,value in data.to_layers().items()]
result = renderer.render(jobs, [], renderer.signboard_chain(data.grade), args.out)
# Check the actually loaded asset, not just the first candidate in the chain.
assert 'signboard_f' in result['used'], result
assert not any(n in result['used'] for n in ('signboard_c','signboard_b')), result
with Image.open(args.out) as im:
    assert im.size == (1920,1080), im.size
print(f"PASS score={score['id']} grade={data.grade} loaded=signboard_f output={args.out}")
