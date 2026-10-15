const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {chromium}=require('playwright');
const replayPath=process.argv[2];
const base=process.env.OM_TEST_BASE||'http://127.0.0.1:8773/';
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.OM_TEST_CHROME,args:['--no-proxy-server']});
 try{
  const page=await browser.newPage({viewport:{width:1280,height:800}});let parsed;
  await page.route('**/src/main.js',async route=>{
   const source=fs.readFileSync(path.resolve('renderer/mania-web/src/main.js'),'utf8').replace('window.__mania = {',`window.__mania = {
    diagnostic(){const time=flowTimeline().resultStart;return {rate:+document.getElementById('playSpeed').value,replayRate:replay.rate,mods:replay.mods,classic:replay.classic,notes:beatmap.hitObjects.length,holds:beatmap.hitObjects.filter(h=>h.isHold).length,chartEnd:beatmap.duration,firstNotes:beatmap.hitObjects.slice(0,8),firstPresses:replay.presses.slice(0,8),judgements:hitMatch.judgements.length,counts:getJudgeCounts(time),accuracy:getAccuracy(time),stableAccuracy:getAccuracyStable(time),bpm:getBPM(time),timeline:flowTimeline()};},`);
   await route.fulfill({contentType:'text/javascript',body:source});
  });
  page.on('response',async r=>{if(r.url().endsWith('/api/resolve_osr'))parsed=await r.json();});
  await page.goto(base);await page.waitForFunction(()=>window.__mania?.skinState().loadedKey);
  await page.locator('#fOsr').setInputFiles(replayPath);await page.locator('#btnLoad').click();
  await page.locator('#sourceScene').waitFor({state:'hidden',timeout:150000});
  const state=await page.evaluate(()=>window.__mania.diagnostic());
  console.log(JSON.stringify({parsed:{bid:parsed?.bid,mods:parsed?.mods,rate:parsed?.rate,counts:parsed?.counts},state},null,2));
  assert.equal(state.rate,1.5,'DT must select 1.5x playback');
  assert.equal(state.holds,0,'Recorded Hold Off mod converts every LN into a tap');
  assert.equal(state.judgements,6286,'HO must not add original LN tail judgements');
  const counts=parsed.counts,total=Object.values(counts).reduce((n,c)=>n+c,0);
  assert.deepEqual(state.counts,{max:counts.perfect,g300:counts.great,g200:counts.good,g100:counts.ok,g50:counts.meh,miss:counts.miss},'Final counters match actual OSR header');
  const expected=100*(305*counts.perfect+300*counts.great+200*counts.good+100*counts.ok+50*counts.meh)/(305*total);
  assert(Math.abs(state.accuracy-expected)<1e-9,'Lazer accuracy matches actual OSR');
  assert.equal(state.firstNotes[0].time,634,'Chart and replay timestamps remain in chart time');
  assert.equal(state.firstPresses[0].time,631);
  await page.waitForFunction(()=>window.__mania.sceneState().resultReady||window.__mania.sceneState().resultError);
  assert.equal(await page.evaluate(()=>window.__mania.sceneState().resultError),'','Website result card renders with the deployed shared template');
  await page.evaluate(()=>{
   const t=window.__mania.sceneState().timeline;
   const seek=document.getElementById('seek');seek.value=10000*(10000-t.start)/(t.end-t.start);seek.dispatchEvent(new Event('input'));
   document.getElementById('btnPlay').click();
  });
  await page.waitForFunction(()=>window.__mania.playback().audioTime>10.1&&!document.getElementById('audio').paused);
  const before=await page.evaluate(()=>({...window.__mania.playback(),wall:performance.now()}));
  await page.waitForTimeout(400);
  const after=await page.evaluate(()=>({...window.__mania.playback(),wall:performance.now(),audioRate:document.getElementById('audio').playbackRate}));
  const measuredRate=(after.timeMs-before.timeMs)/(after.wall-before.wall);
  console.log(JSON.stringify({before,after,measuredRate}));
  assert(measuredRate>1.25&&measuredRate<1.75,'DT advances chart clock at 1.5x wall time');
  assert.equal(after.audioRate,1.5);
  await page.evaluate(()=>document.getElementById('btnPlay').click());
  if(process.argv.includes('--export')){
    const folder=path.resolve('scratch/osu-dt-check');fs.mkdirSync(folder,{recursive:true});
    // Result generation is deliberately unavailable. Gameplay export must be independent.
    await page.route('**/api/result_card',route=>route.fulfill({status:500,contentType:'application/json',body:'{"error":"test: result unavailable"}'}));
    await page.evaluate(()=>document.getElementById('btnSource').click());
    await page.locator('#btnLoad').click();
    await page.locator('#sourceScene').waitFor({state:'hidden',timeout:120000});
    await page.waitForFunction(()=>window.__mania.sceneState().resultError);
    const scene=await page.evaluate(()=>window.__mania.sceneState());
    const downloadPromise=page.waitForEvent('download',{timeout:180000});
    await page.evaluate(()=>document.getElementById('btnExport').click());
    const download=await downloadPromise,target=path.join(folder,'jaafan-dt-ho.mp4');await download.saveAs(target);
    const video=await page.evaluate(async base64=>{
      const v=document.createElement('video');v.src='data:video/mp4;base64,'+base64;
      await new Promise((resolve,reject)=>{v.onloadedmetadata=resolve;v.onerror=reject;});
      return {duration:v.duration,width:v.videoWidth,height:v.videoHeight};
    },fs.readFileSync(target).toString('base64'));
    assert(Math.abs(video.duration-(scene.timeline.resultStart-scene.timeline.start)/1.5/1000)<.1,'Real DT export uses mod speed and excludes webpage results');
    assert(fs.readFileSync(target).includes(Buffer.from('soun')),'Real DT export has an audio track');
    console.log(JSON.stringify({exported:target,video,stats:await page.evaluate(()=>window.__mania.exportState())}));
  }
  console.log('PASS: actual DT replay playback rate and final judgement counts/accuracy');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
