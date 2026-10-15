// Public-site verification uses only generated fixtures, never private replays.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {spawnSync}=require('node:child_process'),{chromium}=require('playwright');
const base=process.env.OM_TEST_BASE||'http://127.0.0.1:8760/';
const folder=path.resolve('scratch/website-release-test');fs.mkdirSync(folder,{recursive:true});
const build=spawnSync(process.env.OM_TEST_PYTHON||'python',['-c',`
import io,sys,wave,zipfile,struct,lzma,json,hashlib
from pathlib import Path
folder=Path(sys.argv[1]);a=io.BytesIO()
with wave.open(a,'wb') as w:
 w.setnchannels(1);w.setsampwidth(2);w.setframerate(8000);w.writeframes(b'\\0'*96000)
chart='''osu file format v14
[General]
AudioFilename: audio.wav
Mode: 3
[Metadata]
Title: Generated Release Test
Artist: Generated Fixture
Creator: Test
Version: DT HO
[Difficulty]
CircleSize: 4
OverallDifficulty: 5
HPDrainRate: 5
[TimingPoints]
0,500,4,2,1,100,1,0
[HitObjects]
64,192,500,128,0,1600:0:0:0:0:
192,192,2000,1,0,0:0:0:0:
'''.encode()
with zipfile.ZipFile(folder/'generated.osz','w') as z:
 z.writestr('audio.wav',a.getvalue());z.writestr('generated.osu',chart)
def string(s):
 b=s.encode();return bytes([11,len(b)])+b
raw=bytes([3])+struct.pack('<i',30000016)
raw+=string(hashlib.md5(chart).hexdigest())+string('Generated Test')+string('0'*32)
raw+=struct.pack('<6H',1,0,0,1,0,0)+struct.pack('<iHBi',999000,2,0,64)+b'\\0'+struct.pack('<q',0)
frames=lzma.compress(b'0|256|-500|0,-1|256|-500|0,501|1|0|0,10|0|0|0,1490|2|0|0,10|0|0|0',format=lzma.FORMAT_ALONE)
extra=lzma.compress(json.dumps({'mods':[{'acronym':'DT'},{'acronym':'HO'}],'statistics':{'perfect':1,'great':1},'maximum_statistics':{'perfect':2}}).encode(),format=lzma.FORMAT_ALONE)
raw+=struct.pack('<i',len(frames))+frames+struct.pack('<qi',0,len(extra))+extra
(folder/'generated.osr').write_bytes(raw)
`,folder],{encoding:'utf8'});assert.equal(build.status,0,build.stderr);
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.OM_TEST_CHROME,args:['--no-proxy-server']});
 try{
  const page=await browser.newPage({viewport:{width:1280,height:800}});const errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.addInitScript(()=>{const fill=CanvasRenderingContext2D.prototype.fillText;CanvasRenderingContext2D.prototype.fillText=function(text,...args){if(String(text).includes('% Lazer'))window.__testAccuracy=text;return fill.call(this,text,...args);};});
  await page.goto(base);await page.waitForFunction(()=>window.__mania?.skinState().loadedKey,{},{timeout:60000});
  assert.equal(await page.locator('#sourceSkinSel option').count(),5,'All existing skins remain available');
  await page.locator('#fMap').setInputFiles(path.join(folder,'generated.osz'));
  await page.locator('#fOsr').setInputFiles(path.join(folder,'generated.osr'));
  await page.locator('#btnLoad').click();await page.locator('#sourceScene').waitFor({state:'hidden',timeout:60000});
  await page.waitForFunction(()=>window.__mania.sceneState().resultReady||window.__mania.sceneState().resultError,{},{timeout:60000});
  const scene=await page.evaluate(()=>window.__mania.sceneState());assert.equal(scene.resultError,'');assert.ok(scene.resultReady);
  assert.equal(scene.timeline.rate,1.5,'DT automatically sets 1.5x');
  assert.deepEqual(await page.evaluate(()=>window.__mania.holdsAt(1000).covering),[],'HO removes original LN graphics');
  await page.evaluate(()=>window.__mania.drawFrame(2500));
  assert.equal(await page.evaluate(()=>window.__testAccuracy),'99.18% Lazer · 100.00% Stable','Actual rendered ACC follows the generated OSR counters');
  const downloadPromise=page.waitForEvent('download',{timeout:120000});await page.evaluate(()=>document.getElementById('btnExport').click());
  const download=await downloadPromise,target=path.join(folder,'generated-export.mp4');await download.saveAs(target);
  const duration=await page.evaluate(async base64=>{const v=document.createElement('video');v.src='data:video/mp4;base64,'+base64;await new Promise((r,j)=>{v.onloadedmetadata=r;v.onerror=j;});return v.duration;},fs.readFileSync(target).toString('base64'));
  assert(Math.abs(duration-(scene.timeline.resultStart-scene.timeline.start)/1500)<.1,'Video includes two-second music tail and excludes webpage result card');
  assert(fs.readFileSync(target).includes(Buffer.from('soun')),'Export includes audio');
  await page.evaluate(()=>window.__mania.drawFrame(window.__mania.sceneState().timeline.end));
  await page.screenshot({path:path.join(folder,'website-result.png')});
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({status:'PASS',base,skins:5,mods:['DT','HO'],accuracy:'99.18%',rate:1.5,exportSeconds:duration,webResult:true,privateDataUploaded:false}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
