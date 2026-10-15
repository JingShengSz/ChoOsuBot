import assert from 'node:assert/strict';
import {buildHitTraces, hitTraceRects, HIT_COLOURS, noteHasEnded} from '../mania-web/src/hit-traces.js';
import {matchMalodyReplay} from '../mania-web/src/malody-replay.js';

const chart={keys:2,hitObjects:[{time:1000,column:0}, {time:1000,column:1},
  {time:2000,column:1,endTime:3000,isHold:true}, {time:4000,column:0}]};
const replay={windows:[52,92,126,150], presses:[{key:0,time:1010},
  {key:1,time:1070}, {key:1,time:2020}, {key:0,time:2500}],releases:[{key:1,time:3010}]};
const match=matchMalodyReplay(chart,replay);
const traces=buildHitTraces(match,replay,2);
assert.deepEqual(traces.map(t=>t.result),['perfect','great','perfect','miss','perfect']);
assert.equal(traces.filter(t=>t.kind==='head').length,replay.presses.length,'Do not invent a press for an auto miss');
assert.equal(traces[3].matched,false);
// Stable folds the release result/time onto its head; the actual head remains 2020.
match.judgements.find(j=>j.objTime===2000).time=3001;
assert.equal(buildHitTraces(match,replay,2)[2].time,2020);
const g={keys:2,colX:[600,760],colW:[80,120],hitY:900,timeRange:1000,scale:2.25};
const rects=hitTraceRects(traces,g,900);
const cap=rects.find(r=>r.part==='cap'&&r.col===1);
assert.equal(cap.x+cap.w/2,820,'Use skin column centre, including gaps and uneven widths');
assert.equal(cap.w,60);
assert.equal(cap.y+cap.h/2,747,'Use the same time-to-Y projection as notes');
const faster=hitTraceRects(traces,{...g,timeRange:500},900).find(r=>r.part==='cap'&&r.col===1);
assert.equal(900-(faster.y+faster.h/2),2*(900-(cap.y+cap.h/2)));
assert.deepEqual(cap.rgb,HIT_COLOURS.great.map(v=>v/255));
assert.ok(rects.every(r=>r.y>=0&&r.y+r.h<=g.hitY));
assert.deepEqual(hitTraceRects(traces,g,10000),[],'Seeking does not retain old marks');
const recorded=matchMalodyReplay(chart,{...replay,recordedJudgements:[
  {key:0,time:1010,obj_time:1000,result:'great',combo:1},
  {key:1,time:1070,obj_time:1000,result:'perfect',combo:2},
]});
assert.deepEqual(buildHitTraces(recorded,replay,2).slice(0,2).map(t=>t.result),['great','perfect']);
console.log('PASS: raw/empty presses, simultaneous lanes, stable holds, recorded MRV colours, scroll, gaps and seek');

const held = hitTraceRects(traces,g,2500);
assert.ok(held.some(r=>r.part==='hold'),'LN body remains visible after its head leaves the viewport');
assert.ok(held.some(r=>r.part==='held'&&Math.abs(r.y+r.h-g.hitY)<1e-6));
const released = hitTraceRects(traces,g,3020);
assert.ok(!released.some(r=>r.part==='held'),'Release turns off the held marker');
assert.ok(hitTraceRects(traces,g,2990).some(r=>r.kind==='tail'&&r.part==='cap'),'Tail T exists before the chart tail is consumed');
assert.deepEqual(released,[],'LN overlay disappears together with its chart tail, even for a late release');
const tailMatch={...match,judgements:[...match.judgements,
  {kind:'tail',col:1,objTime:3000,result:'good',time:3010}]};
assert.equal(buildHitTraces(tailMatch,replay,2).at(-1).result,'good','Separate tail colour is authoritative');
const broken={...replay,presses:[...replay.presses,{key:1,time:2800}],releases:[{key:1,time:2900}]};
assert.ok(!buildHitTraces(match,broken,2).some(t=>t.kind==='tail'),
  'A release belonging to the next key cycle cannot finish the old LN');
console.log('PASS: sustained LN, release cap/colour, held indicator and interrupted key cycles');

for (const pressTime of [990,1010]) {
  const tap=[{col:0,time:pressTime,objTime:1000,kind:'head',matched:true,result:'perfect'}];
  assert.ok(hitTraceRects(tap,g,980).length,'Early/late tap is visible with its note');
  assert.deepEqual(hitTraceRects(tap,g,1000),[],'Tap vanishes at the same boundary as its note');
  assert.deepEqual(hitTraceRects(tap,g,1001),[]);
  assert.ok(noteHasEnded({time:1000},1000,true));
}
const stuck=buildHitTraces(match,{...replay,releases:[]},2);
assert.ok(hitTraceRects(stuck,g,2500).some(r=>r.part==='held'));
assert.deepEqual(hitTraceRects(stuck,g,3100),[],'Missing release cannot leave a permanent LN line');
for (const now of [1990,2000,2020,2500,2999,3000,3100]) {
  assert.ok(hitTraceRects(traces,g,now).every(r=>r.y>=0&&r.y+r.h<=g.hitY),
    'No trace survives below the judgment line');
}
const early=buildHitTraces(match,{...replay,releases:[{key:1,time:2900}]},2);
assert.ok(hitTraceRects(early,g,2950).some(r=>r.kind==='tail'&&r.part==='stem'));
assert.deepEqual(hitTraceRects(early,g,3000),[]);
console.log('PASS: shared tap/LN lifetime, early/late release, missing release and judgment-line clipping');

for (const releaseTime of [2900,3000,3100]) {
  const tail=[{col:1,kind:'tail',time:releaseTime,objTime:3000,
    noteTime:2000,noteIsHold:true,endTime:3000,result:'great'}];
  const marks=hitTraceRects(tail,g,2800);
  const bar=marks.find(r=>r.part==='cap'),stem=marks.find(r=>r.part==='stem');
  const expectedTop=Math.min(g.hitY-(releaseTime-2800)/g.timeRange*g.hitY,
    g.hitY-(3000-2800)/g.timeRange*g.hitY);
  assert.equal(bar.y+bar.h/2,expectedTop,'Tail bar uses the upper timing endpoint');
  assert.equal(stem.y,expectedTop,'Tail stem extends down from the bar for early/on-time/late releases');
  assert.ok(stem.y+stem.h>bar.y+bar.h/2);
  assert.deepEqual(bar.rgb,HIT_COLOURS.great.map(v=>v/255));
  assert.deepEqual(hitTraceRects(tail,g,3000),[],'Direction correction preserves note disappearance');
}
console.log('PASS: upright LN tail T for early/on-time/late releases, colours and lifetime');
