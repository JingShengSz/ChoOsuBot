import assert from 'node:assert/strict';
import {stepDrawerSpring} from '../mania-web/src/drawer-ui.js';

function simulate(fps){let position=1,velocity=0;for(let i=0;i<fps/2;i++){const next=stepDrawerSpring(position,velocity,0,1/fps);assert.ok(next.position<=position&&next.position>=0,'Drawer opens monotonically without crossing its bottom anchor');({position,velocity}=next);}return {position,velocity};}
const a=simulate(30),b=simulate(60),c=simulate(120);
assert.ok(a.position<.001,'Drawer settles within half a second');
assert.ok(Math.abs(a.position-b.position)<1e-10&&Math.abs(b.position-c.position)<1e-10,'Motion must be independent of frame rate');
let state={position:1,velocity:0};
for(let i=0;i<5;i++)state=stepDrawerSpring(state.position,state.velocity,0,1/60);
const before=state.position;
state=stepDrawerSpring(state.position,state.velocity,1,1/60);
assert.ok(Math.abs(state.position-before)<.2,'Rapid retargeting keeps position continuous');
for(let i=0;i<60;i++)state=stepDrawerSpring(state.position,state.velocity,1,1/60);
assert.ok(Math.abs(state.position-1)<.001);
console.log('PASS: drawer settles, retains continuity and matches at 30/60/120 fps');
