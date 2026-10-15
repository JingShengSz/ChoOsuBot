import assert from 'node:assert/strict';
import {errorBarState, errorColour, ERROR_AVERAGE_EASE_MS} from '../mania-web/src/error-bar.js';
import {buildHitTraces} from '../mania-web/src/hit-traces.js';
import {matchMalodyReplay} from '../mania-web/src/malody-replay.js';

const hit=(time,offset,result='great',extra={})=>({time,objTime:time-offset,result,kind:'head',matched:true,...extra});
const traces=[hit(1000,-60),hit(6000,40),hit(6100,-80),hit(6110,0,'miss',{matched:false}),
  hit(6120,-90,'good',{kind:'tail'}),hit(6200,100)];
const recent=errorBarState(traces,6190,120);
assert.equal(recent.markers.length,2,'Future presses, old hits, ghost taps and releases are excluded');
assert.ok(recent.average<0,'Recent late/early input updates the arrow instead of using the song average');
assert.ok(errorBarState(traces,6050,120).average>0,'The triangle visibly crosses the centre');
assert.equal(errorBarState(traces,0,120).average,null);
assert.equal(errorBarState(traces,12000,120).average,null,'Idle meter ages out the average');
assert.deepEqual(errorBarState(traces,6050,120),errorBarState(traces,6050,120),'Seeking backward is deterministic');
const one=[hit(1000,25,'good')];
const start=errorBarState(one,1000,100).markers[0];
const half=errorBarState(one,3500,100).markers[0];
assert.equal(half.alpha,start.alpha/4,'Playback-time fade follows the quadratic envelope');
assert.equal(errorBarState(one,6000,100).markers.length,0);
const big=errorBarState(one,1000,100,2.5).markers[0];
assert.equal(big.w/start.w,2.5);assert.equal(big.h/start.h,2.5);
assert.equal(big.radius,big.w/2,'Both ends form a capsule');
assert.equal(big.position,start.position,'Size does not change the timing position');
assert.equal(new Set(['perfect','great','good','ok','meh','miss'].map(errorColour)).size,6);

const opposite=[hit(1000,-60),hit(2000,60)];
const before=errorBarState(opposite,1999,120).average;
const onset=errorBarState(opposite,2000,120).average;
const first=errorBarState(opposite,2001,120).average;
const midway=errorBarState(opposite,2000+ERROR_AVERAGE_EASE_MS/2,120).average;
const settled=errorBarState(opposite,2000+ERROR_AVERAGE_EASE_MS,120).average;
assert.equal(onset,before,'A new hit no longer jumps the arrow');
assert.ok(Math.abs(first-onset)<.001,'The transition begins gently');
assert.ok(onset<midway&&midway<settled,'The arrow eases toward the new mean');
for(const fps of [30,60,120]){
  for(let time=1000;time<2090;time+=1000/fps)errorBarState(opposite,time,120);
  assert.equal(errorBarState(opposite,2090,120).average,midway,'Frame rate does not alter the motion');
}
errorBarState(opposite,2300,120);
assert.equal(errorBarState(opposite,2090,120).average,midway,'Seeking back reconstructs the same eased position');

// Exercise the existing native matcher + shared hit index, not invented results.
const beatmap={keys:4,hitObjects:[0,1,2,3].map((column,i)=>({column,time:1000+i*500,isHold:false}))};
const replay={source:'malody',windows:[20,50,100,150],presses:[0,25,75,130].map((offset,i)=>({key:i,time:1000+i*500+offset})),releases:[]};
const match=matchMalodyReplay(beatmap,replay);
const native=errorBarState(buildHitTraces(match,replay,4),2700,150);
assert.deepEqual(native.markers.map(m=>m.colour),['perfect','great','good','miss'].map(errorColour));
assert.equal(native.markers.length,4,'Native Malody results reach the meter');
console.log('PASS: judgement colours, capsule scaling, deterministic fade and moving recent average, native Malody matching');
