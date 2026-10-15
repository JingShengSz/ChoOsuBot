import assert from 'node:assert/strict';
import {sceneTimeline,introArrow,resultTransition,INTRO_CYCLE_MS} from '../mania-web/src/scene-flow.js';
for(const entry of [-400,0,600,5000])for(const rate of [.5,1,1.5,2]){
  const t=sceneTimeline(entry,5000,rate);
  const end=t.start+INTRO_CYCLE_MS*2*rate;
  assert.ok(end<=entry-500*rate,'Both pulses finish half a second before the first visible note');
  for(const cycle of [0,1]){
    const start=introArrow(t.start+cycle*INTRO_CYCLE_MS*rate,t);
    const midway=introArrow(t.start+(cycle+.5)*INTRO_CYCLE_MS*rate,t);
    const finish=introArrow(t.start+(cycle+.99)*INTRO_CYCLE_MS*rate,t);
    assert.equal(start.cycle,cycle);assert.equal(start.offset,0);
    assert.ok(start.offset<midway.offset&&midway.offset<finish.offset);
    assert.ok(start.alpha>midway.alpha&&midway.alpha>finish.alpha);
  }
  assert.equal(introArrow(end,t),null);
  assert.equal(introArrow(t.start-1,t),null);
  assert.equal((t.resultStart-t.chartEnd)/rate,2000);
  assert.equal(resultTransition(t.resultStart,t),0);
  assert.ok(Math.abs(resultTransition((t.resultStart+t.resultEnd)/2,t)-.5)<1e-9);
  assert.equal(resultTransition(t.resultEnd,t),1);
}
console.log('PASS: two downward fading pulses, half-second deadline, short lead-ins/rates, two-second music tail and smooth deterministic results');
