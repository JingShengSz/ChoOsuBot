// Compare the saved baseline and current code with the same replay, skin and
// 15-second late-map window. Audio is excluded to isolate draw/encode throughput.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {spawnSync}=require('node:child_process');
const {chromium}=require('playwright');
const mode=process.argv[2]||'current',replayPath=process.argv[3];assert.ok(replayPath);
const root=path.resolve('scratch/export-fast-20261015'),baseline=path.join(root,'baseline');
fs.mkdirSync(root,{recursive:true});
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.OM_TEST_CHROME,args:['--no-proxy-server']});
 try{
  const page=await browser.newPage({viewport:{width:1280,height:800}});const errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/src/*.js',async route=>{
   const name=new URL(route.request().url()).pathname.split('/').at(-1);
   const saved=path.join(baseline,name),current=path.resolve('renderer/mania-web/src',name);
   const file=mode.startsWith('baseline')&&fs.existsSync(saved)?saved:current;
   if(!fs.existsSync(file)){await route.continue();return;}
   let source=fs.readFileSync(file,'utf8');
   if(name==='main.js'){
    source=source.replace('async function exportWebCodecs(jobId, total, onProgress, isCancelled) {','async function exportWebCodecs(jobId, total, onProgress, isCancelled) { window.__benchStart=performance.now();');
    source=source.replace('encoder.configure(encCfg);','window.__benchConfig=encCfg; encoder.configure(encCfg);');
    source=source.replace('await encoder.flush();','await encoder.flush(); window.__benchStats={frames:total,ms:performance.now()-window.__benchStart,config:window.__benchConfig};');
    source+=`
const savedFlow=flowTimeline;
flowTimeline=()=>({...savedFlow(),start:250000,end:265000});
encodeBeatmapAudio=async()=>null;
window.__benchSample=ms=>({combo:getCombo(ms),counts:getJudgeCounts(ms),ur:getUR(ms),cps:getCPS(ms)});
window.__benchGPU=()=>{const gl=renderer.gl,e=gl.getExtension('WEBGL_debug_renderer_info');return e?gl.getParameter(e.UNMASKED_RENDERER_WEBGL):'unavailable';};
`;
   }
   await route.fulfill({contentType:'text/javascript',body:source});
  });
  await page.goto('http://127.0.0.1:8773/');await page.waitForFunction(()=>window.__mania?.skinState().loadedKey);
  await page.locator('#sourceSkinSel').selectOption('owc (default)');
  await page.waitForFunction(()=>window.__mania.skinState().loadedKey==='owc (default)'&&!window.__mania.skinState().loading);
  await page.locator('#bidInput').fill('4565844');await page.locator('#fOsr').setInputFiles(replayPath);await page.locator('#btnLoad').click();
  await page.locator('#sourceScene').waitFor({state:'hidden',timeout:120000});
  await page.waitForFunction(()=>window.__mania.sceneState().resultReady||window.__mania.sceneState().resultError);
  assert.equal(await page.evaluate(()=>window.__mania.sceneState().resultError),'');
  const samples=await page.evaluate(()=>[250000,255000,264999,7904,50000].map(ms=>window.__benchSample(ms)));
  const downloadPromise=page.waitForEvent('download',{timeout:120000});
  await page.evaluate(()=>{window.__webglOutW=1280;window.__webglOutH=720;window.__webglBitrate=6000000;document.getElementById('btnExport').click();});
  const download=await downloadPromise;const output=path.join(root,mode+'.mp4');await download.saveAs(output);
  const metrics=await page.evaluate(()=>({...window.__benchStats,gpu:window.__benchGPU(),canvas:[document.getElementById('game').width,document.getElementById('game').height]}));
  metrics.fps=metrics.frames/(metrics.ms/1000);metrics.samples=samples;
  const encoded=fs.readFileSync(output);
  const frame=await page.evaluate(async b64=>{const v=document.createElement('video');v.src='data:video/mp4;base64,'+b64;await new Promise((r,j)=>{v.onloadedmetadata=r;v.onerror=j;});return {duration:v.duration};},encoded.toString('base64'));
  assert.ok(Math.abs(frame.duration-15)<.1);assert.deepEqual(errors,[]);
  const decoded=spawnSync(process.env.OM_TEST_PYTHON||'python',['-c',`import sys,subprocess;sys.path.insert(0,'renderer');from mania_render.renderer import _find_ffmpeg;subprocess.run([_find_ffmpeg(),'-y','-loglevel','error','-ss','5','-i',sys.argv[1],'-frames:v','1',sys.argv[2]],check=True)`,output,path.join(root,mode+'.png')],{encoding:'utf8'});
  assert.equal(decoded.status,0,decoded.stderr);
  fs.writeFileSync(path.join(root,mode+'.json'),JSON.stringify(metrics,null,2));
  console.log(JSON.stringify({mode,frames:metrics.frames,ms:metrics.ms,fps:metrics.fps,gpu:metrics.gpu,config:metrics.config}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
