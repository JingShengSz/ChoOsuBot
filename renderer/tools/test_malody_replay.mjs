import assert from 'node:assert/strict';
import { matchMalodyReplay } from '../mania-web/src/malody-replay.js';
import { applyMalodyMods } from '../mania-web/src/malody-mods.js';

const chart = { keys: 4, hitObjects: [
  {time:1000,column:0,isHold:false},
  {time:2000,endTime:3000,column:1,isHold:true},
  {time:4000,column:2,isHold:false},
] };
const replay = { windows:[52,92,126,150], presses:[{time:1010,key:0},{time:2070,key:1}],
  releases:[{time:1100,key:0},{time:2100,key:1}] };
const result = matchMalodyReplay(chart,replay);
assert.deepEqual(result.judgements.map(j=>j.result),['perfect','great','miss']);
assert.equal(result.judgements.length,3,'Malody holds get one head judgement');
assert.deepEqual(result.comboTrail.map(j=>j.combo),[1,2,0]);
assert.equal(replay.presses[1].hold,true);
assert.equal(result.objs[1].error,70);
const late = matchMalodyReplay({keys:1,hitObjects:[{time:1000,column:0}]},
  {windows:[52,92,126,150],presses:[{time:1150,key:0}]});
assert.equal(late.judgements[0].result,'miss');
console.log('Malody head matching, windows, hold, combo and missed notes passed');
const recorded = matchMalodyReplay(chart, {...replay, recordedJudgements:[
  {time:1010,key:0,result:'great',combo:1},
  {time:2070,key:1,result:'perfect',combo:2},
  {time:4150,key:2,result:'miss',combo:0},
]});
assert.deepEqual(recorded.judgements.map(j=>j.result),['great','perfect','miss']);
assert.deepEqual(recorded.comboTrail.map(j=>j.combo),[1,2,0]);
console.log('MRV recorded results and combo override inferred 4.x judgements');
const modChart={hitObjects:[{time:100,endTime:500,isHold:true}],duration:500,
  timings:[{time:0,bpm:120,isRed:true},{time:200,isRed:false}]};
applyMalodyMods(modChart,{holdsToNotes:true,constantScroll:true});
assert.equal(modChart.hitObjects[0].isHold,false);
assert.equal(modChart.hitObjects[0].endTime,100);
assert.equal(modChart.duration,100);
assert.deepEqual(modChart.timings,[{time:0,bpm:120,isRed:true}]);
console.log('MRV LN-to-note, duration and Const applied before matching');
