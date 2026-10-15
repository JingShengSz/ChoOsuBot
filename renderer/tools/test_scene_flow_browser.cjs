const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {spawnSync}=require('node:child_process');const {chromium}=require('playwright');
const output=path.resolve('scratch/scene-flow');fs.mkdirSync(output,{recursive:true});
const exportQuality=process.env.OM_TEST_EXPORT_QUALITY||'720';
const base=process.env.OM_TEST_BASE||'http://127.0.0.1:8773/';
const fixture=path.join(output,'scene-test.osz');
const build=spawnSync(process.env.OM_TEST_PYTHON||'python',['-c',`
import io,sys,wave,zipfile,math,struct
a=io.BytesIO()
with wave.open(a,'wb') as w:
 w.setnchannels(1);w.setsampwidth(2);w.setframerate(8000)
 w.writeframes(b''.join(struct.pack('<h',int(1000*math.sin(i*math.pi/20))) for i in range(48000)))
with zipfile.ZipFile(sys.argv[1],'w') as z:
 z.writestr('audio.wav',a.getvalue())
 z.writestr('scene.osu','''osu file format v14
[General]
AudioFilename: audio.wav
Mode: 3
[Metadata]
Title: Scene Flow Test
Artist: Test
Creator: Local
Version: Short intro
[Difficulty]
CircleSize: 4
OverallDifficulty: 8
HPDrainRate: 5
[TimingPoints]
0,500,4,2,1,100,1,0
[HitObjects]
64,192,500,1,0,0:0:0:0:
192,192,2000,1,0,0:0:0:0:
''')
`,fixture],{encoding:'utf8'});assert.equal(build.status,0,build.stderr);
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.OM_TEST_CHROME,args:['--no-proxy-server']});
 try{
  const page=await browser.newPage({viewport:{width:1280,height:800}});const errors=[];
  page.on('pageerror',e=>{errors.push(e.message);console.error('Browser error:',e.message);});
  await page.goto(base);await page.waitForFunction(()=>window.__mania?.skinState().loadedKey,{},{timeout:60000});
  await page.locator('#sourceSkinSel').selectOption('owc (default)');
  await page.waitForFunction(()=>window.__mania.skinState().loadedKey==='owc (default)'&&!window.__mania.skinState().loading);
  await page.locator('#fMap').setInputFiles(fixture);await page.locator('#btnLoad').click();
  await page.locator('#sourceScene').waitFor({state:'hidden',timeout:60000});
  await page.waitForFunction(()=>window.__mania.sceneState().resultReady||window.__mania.sceneState().resultError);
  const scene=await page.evaluate(()=>window.__mania.sceneState());assert.equal(scene.resultError,'');assert.ok(scene.resultReady);
  const t=scene.timeline;assert.ok(t.start<0,'Short chart receives pre-roll');
  for(const [name,ms] of [['intro-first',t.start+250],['intro-second',t.start+900],['music-tail',t.chartEnd+1000],['transition',t.resultStart+325],['result',t.resultEnd+100]]){
   await page.evaluate(ms=>window.__mania.drawFrame(ms),ms);await page.screenshot({path:path.join(output,name+'.png')});
  }
  await page.evaluate(()=>{document.getElementById('seek').value=10000*(2000-window.__mania.sceneState().timeline.start)/(window.__mania.sceneState().timeline.end-window.__mania.sceneState().timeline.start);document.getElementById('seek').dispatchEvent(new Event('input'));document.getElementById('btnPlay').click();});
  await page.waitForTimeout(1200);
  assert.ok(await page.evaluate(()=>window.__mania.playback().playing&&window.__mania.playback().audioTime>2.9),'Music continues past the last note');
  await page.waitForTimeout(1500);
  assert.ok(await page.evaluate(()=>window.__mania.sceneState().transition>0&&document.getElementById('audio').paused),'Music ends before result transition');
  await page.evaluate(()=>document.getElementById('btnPlay').click());
  await page.locator('#exportQuality').selectOption(exportQuality,{force:true});
  const downloadPromise=page.waitForEvent('download',{timeout:120000});
  await page.evaluate(()=>document.getElementById('btnExport').click());
  const download=await downloadPromise;await download.saveAs(path.join(output,'scene-export.mp4'));
  await page.waitForFunction(()=>document.getElementById('btnExport').textContent==='导出');
  const exportedState=await page.evaluate(()=>window.__mania.exportState());
  assert.equal(exportedState.width,exportQuality==='1080'?1920:1280);assert.equal(exportedState.height,Number(exportQuality));
  assert.ok(exportedState.fps>0);
  assert.deepEqual(await page.evaluate(()=>[document.getElementById('game').width,document.getElementById('game').height,document.getElementById('hud').width,document.getElementById('hud').height]),[1920,1080,1920,1080],'Preview resolution restores after export');
  assert.ok(fs.statSync(path.join(output,'scene-export.mp4')).size>50000);
  const exported=fs.readFileSync(path.join(output,'scene-export.mp4'));
  assert.ok(exported.includes(Buffer.from('soun')),'MP4 contains an audio track');
  const video=await page.evaluate(async base64=>{
   const v=document.createElement('video');v.muted=true;v.src='data:video/mp4;base64,'+base64;
   await new Promise((resolve,reject)=>{v.onloadedmetadata=resolve;v.onerror=reject;});
   return {duration:v.duration};
  },exported.toString('base64'));
  assert.ok(Math.abs(video.duration-(t.resultStart-t.start)/t.rate/1000)<.15,'Export stops after the music tail and excludes the result transition/hold');
  const ffmpeg=spawnSync(process.env.OM_TEST_PYTHON||'python',['-c',"import sys;sys.path.insert(0,'renderer');from mania_render.renderer import _find_ffmpeg;print(_find_ffmpeg())"],{encoding:'utf8'});
  assert.equal(ffmpeg.status,0,ffmpeg.stderr);
  const decoded=spawnSync(ffmpeg.stdout.trim(),['-y','-loglevel','error','-ss',String(video.duration-.2),'-i',path.join(output,'scene-export.mp4'),'-frames:v','1',path.join(output,'export-final.png')],{encoding:'utf8'});
  assert.equal(decoded.status,0,decoded.stderr);
  const levels=await page.evaluate(async({base64,lead,musicEnd})=>{
   const raw=Uint8Array.from(atob(base64),c=>c.charCodeAt(0));const context=new AudioContext();
   try{
    const audio=await context.decodeAudioData(raw.buffer),data=audio.getChannelData(0);
    const rms=(start,end)=>{let sum=0,n=0;for(let i=Math.ceil(start*audio.sampleRate);i<Math.min(data.length,end*audio.sampleRate);i++){sum+=data[i]**2;n++;}return Math.sqrt(sum/Math.max(1,n));};
    return {intro:rms(.1,lead-.1),tail:rms(lead+2.5,lead+3.5),duration:audio.duration};
   }finally{await context.close();}
  },{base64:exported.toString('base64'),lead:-t.start/1000,musicEnd:(t.resultStart-t.start)/1000});
  assert.ok(levels.intro<.001&&levels.tail>.005&&Math.abs(levels.duration-video.duration)<.15,'Audio is delayed through pre-roll, plays two seconds after notes and matches the gameplay-only video duration');
  if(process.argv[2]){
   const real=await browser.newPage({viewport:{width:1440,height:900}});let summary;
   real.on('request',r=>{if(r.url().endsWith('/api/result_card'))summary=r.postDataJSON();});
   await real.goto(base);await real.waitForFunction(()=>window.__mania?.skinState().loadedKey);
   await real.locator('#sourceSkinSel').selectOption('owc (default)');
   await real.locator('#bidInput').fill('4565844');await real.locator('#fOsr').setInputFiles(process.argv[2]);await real.locator('#btnLoad').click();
   await real.locator('#sourceScene').waitFor({state:'hidden',timeout:120000});
   await real.waitForFunction(()=>window.__mania.sceneState().resultReady||window.__mania.sceneState().resultError);
   assert.equal(await real.evaluate(()=>window.__mania.sceneState().resultError),'');
   assert.equal(summary.score.user.username,'F6A8AF');assert.ok(summary.score.total_score>0&&summary.score.max_combo>0);
   assert.ok(Number.isInteger(summary.beatmap.bpm),'BPM is formatted without floating-point overflow');
   assert.equal(summary.score.display_date,'2026-09-29','Replay date uses the client timezone');
   await real.evaluate(()=>window.__mania.drawFrame(window.__mania.sceneState().timeline.end));
   await real.screenshot({path:path.join(output,'real-osr-result.png')});
   await real.close();
  }
  assert.deepEqual(errors,[]);
  fs.writeFileSync(path.join(output,'timeline.json'),JSON.stringify(t,null,2));
  console.log('PASS: short chart pre-roll, two-second music tail, webpage result crossfade, gameplay-only MP4 export, no browser errors');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
