import assert from 'node:assert/strict';
import {NoteIndex,ReplayIndex,upperBound,timeWindow} from '../mania-web/src/frame-index.js';
import {selectVideoConfig,resizeExportCanvas} from '../mania-web/src/export-fast.js';

const notes=Array.from({length:5000},(_,i)=>({time:i*20,column:i%4,isHold:i%13===0,endTime:i*20+(i%13===0?3500:0)}));
notes[0].endTime=90000;
const index=new NoteIndex(notes);
for(const start of [-100,0,850,12500,80000,100000])for(const span of [0,450,2000]){
  assert.deepEqual([...index.visible(start,start+span)],notes.filter(n=>n.time<=start+span&&(n.isHold?n.endTime:n.time)>=start),'Visible selection preserves long holds and chart order');
}
const results=['perfect','great','good','ok','meh','miss'];
const objs=notes.map((n,i)=>({time:n.time,col:n.column,isHold:n.isHold,matched:i%7!==0,error:(i%101)-50}));
const judgements=notes.map((n,i)=>({time:n.time+80,result:results[i%6]}));
const replay={source:'malody',rate:1.5,presses:notes.map(n=>({time:n.time,key:n.column})),releases:notes.map(n=>({time:n.time+5,key:n.column}))};
const match={objs,judgements,comboTrail:notes.map((n,i)=>({time:n.time,combo:i%100}))};
const fast=new ReplayIndex({hitObjects:notes},match,replay,4);
for(const time of [90000,1000,50,-1,0,100001,43210,1000]){
  const counts={max:0,g300:0,g200:0,g100:0,g50:0,miss:0};
  for(const j of judgements)if(j.time<=time)counts[['max','g300','g200','g100','g50','miss'][results.indexOf(j.result)]]++;
  assert.deepEqual(fast.counts(time),counts);
  assert.equal(fast.combo(time),match.comboTrail.filter(j=>j.time<=time).at(-1)?.combo||0);
  assert.equal(fast.cps(time),replay.presses.filter(p=>p.time<=time&&p.time>time-1500).length);
  let n=0,mean=0,m2=0;
  for(const o of objs){if(o.time>time)break;if(!o.matched)continue;const x=o.error/1.5,d=x-mean;mean+=d/++n;m2+=d*(x-mean);}
  assert.equal(fast.ur(time),n<2?'—':(10*Math.sqrt(m2/n)).toFixed(1));
  fast.lastKeys(time).forEach((s,col)=>{assert.equal(s.down,replay.presses.filter(p=>p.key===col&&p.time<=time).at(-1)?.time);assert.equal(s.up,replay.releases.filter(p=>p.key===col&&p.time<=time).at(-1)?.time);});
}
assert.equal(upperBound([{time:1},{time:1},{time:2}],1),2);
assert.deepEqual(timeWindow([{time:1},{time:1},{time:2}],1,1),[{time:1},{time:1}]);
const base={codec:'avc1.640028',width:1280,height:720,framerate:60};
let configs=[];
const hardware=await selectVideoConfig(base,{isConfigSupported:async config=>{configs.push(config);return {supported:true,config};}});
assert.equal(hardware.hardwareAcceleration,'prefer-hardware');
assert.equal(configs.length,1);
const fallback=await selectVideoConfig(base,{isConfigSupported:async config=>({supported:config.hardwareAcceleration==='no-preference',config})});
assert.equal(fallback.hardwareAcceleration,'no-preference');
await assert.rejects(selectVideoConfig(base,{isConfigSupported:async config=>({supported:false,config})}));
const canvas={width:1920,height:1080},hud={width:1920,height:1080,getContext:()=>({setTransform(){}})},renderer={logicalWidth:1920,logicalHeight:1080};
const restore=resizeExportCanvas(canvas,hud,renderer,1280,720);
assert.equal(canvas.width,1280);assert.equal(hud.height,720);assert.equal(renderer.logicalWidth,1920);
restore();assert.equal(canvas.width,1920);assert.equal(hud.height,1080);
console.log('PASS: indexed windows/long holds, exact counts/combo/CPS/UR and reverse seeks, hardware fallback and canvas restoration');
