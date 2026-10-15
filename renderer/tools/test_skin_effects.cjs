const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {chromium}=require('playwright');
const {spawnSync}=require('node:child_process');
const os=require('node:os');
const replayPath=process.argv[2];
assert.ok(replayPath,'Usage: node renderer/tools/test_skin_effects.cjs <replay.osr> [--all]');
const sourcePath=path.resolve('renderer/mania-web/src/main.js');
const output=path.resolve('scratch/skin-effects-regression');fs.mkdirSync(output,{recursive:true});
const instrumentation=`
window.__probeQuads=[];
const probeNames=new WeakMap(),probeUpload=Renderer.prototype.uploadTexture,probeDraw=Renderer.prototype.drawQuad;
Renderer.prototype.uploadTexture=function(key,...args){const tex=probeUpload.call(this,key,...args);if(tex)probeNames.set(tex,key);return tex;};
Renderer.prototype.drawQuad=function(tex,x,y,w,h,...args){window.__probeQuads.push({name:probeNames.get(tex)||'solid',x,y,w,h});return probeDraw.call(this,tex,x,y,w,h,...args);};
window.__probeEffectConfig=()=>({widths:geometry.colW,scale:geometry.scale,texScale:geometry.texScale,hitY:geometry.hitY,lightPosition:block.lightPosition,normalWidths:block.lightingNWidth,holdWidths:block.lightingLWidth});
window.__probeTextureSizes={};
const sizedUpload=Renderer.prototype.uploadTexture;
Renderer.prototype.uploadTexture=function(key,img,...args){window.__probeTextureSizes[key]={w:img.width,h:img.height};return sizedUpload.call(this,key,img,...args);};
`;
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.OM_TEST_CHROME,args:['--no-proxy-server']});
 try{
  const page=await browser.newPage({viewport:{width:1280,height:720}});let replayData;
  page.on('response',async response=>{if(response.url().endsWith('/api/resolve_osr'))replayData=await response.json();});
  await page.route('**/src/main.js',async route=>{
   let source=fs.readFileSync(sourcePath,'utf8');
   source=source.replace('const $ = (id)',instrumentation+'\nconst $ = (id)').replace('function drawFrame(nowMs) {','function drawFrame(nowMs) { window.__probeQuads=[];');
   await route.fulfill({contentType:'text/javascript',body:source});
  });
  await page.goto('http://127.0.0.1:8773/');
  await page.waitForFunction(()=>window.__mania?.skinState().loadedKey);
  await page.locator('#sourceSkinSel').selectOption('owc (default)');
  await page.waitForFunction(()=>window.__mania.skinState().loadedKey==='owc (default)'&&!window.__mania.skinState().loading);
  await page.locator('#bidInput').fill('4565844');
  await page.locator('#fOsr').setInputFiles(replayPath);await page.locator('#btnLoad').click();
  await page.locator('#sourceScene').waitFor({state:'hidden',timeout:120000});
  assert.ok(replayData?.presses.length,'Real replay presses must be loaded');
  const samples=[];
  for(const press of replayData.presses.slice(0,150)){
   const ms=press.time+40;
   const frame=await page.evaluate(ms=>{window.__mania.drawFrame(ms);return{columns:window.__mania.columns(),quads:window.__probeQuads};},ms);
   const beams=frame.quads.filter(q=>q.name==='slgt');
   const notes=frame.quads.filter(q=>/^n\d+$/.test(q.name));
   const lights=frame.quads.filter(q=>/^lf/.test(q.name));
   if(beams.length&&notes.length)samples.push({ms,columns:frame.columns,beams,lights,notes});
   if(beams.length>=2&&notes.length){await page.screenshot({path:path.join(output,'owc.png')});break;}
  }
  assert.ok(samples.length,'Repro must contain stage beams and visible notes');
  fs.writeFileSync(path.join(output,'owc.json'),JSON.stringify(samples,null,2));
  const frame=samples.at(-1),lane=frame.columns.colW;
  console.log(JSON.stringify({time:frame.ms,laneWidth:lane,beamWidths:frame.beams.map(q=>q.w),flashWidths:frame.lights.map(q=>q.w),noteWidths:frame.notes.map(q=>q.w)}));
  for(const sample of samples)for(const beam of sample.beams)assert.ok(beam.w<=sample.columns.colW+.001,`Beam width ${beam.w} crosses column width ${sample.columns.colW}`);
  console.log('PASS: stage beams remain inside their note columns');
  async function checkSkin(name){
    const snapshot=await page.evaluate(ms=>{window.__mania.drawFrame(ms);return{config:window.__probeEffectConfig(),columns:window.__mania.state,quads:window.__probeQuads,sizes:window.__probeTextureSizes};},frame.ms);
    const columns=snapshot.columns,cfg=snapshot.config;
    for(const quad of snapshot.quads){
      if(quad.name==='slgt'){
        const index=columns.colX.reduce((best,x,i)=>Math.abs(x+cfg.widths[i]/2-(quad.x+quad.w/2))<Math.abs(columns.colX[best]+cfg.widths[best]/2-(quad.x+quad.w/2))?i:best,0);
        assert.ok(Math.abs(quad.w-cfg.widths[index])<.02,name+': beam uses its own column width');
        assert.ok(Math.abs(quad.x-columns.colX[index])<.06,name+': beam aligns with note column');
        assert.ok(Math.abs(quad.h-Math.min(snapshot.sizes.slgt.h,768)*cfg.texScale)<.02,name+': beam height preserves the original sprite');
        assert.ok(Math.abs(quad.y+quad.h-(1080-(cfg.lightPosition??67)*cfg.scale))<.02,name+': beam follows LightPosition');
      }
      if(/^lf\d/.test(quad.name)){
        const col=Number(quad.name[2]),sprite=snapshot.sizes[quad.name];
        const normal=(cfg.normalWidths[col]>0?cfg.normalWidths[col]*cfg.scale:sprite.w*cfg.texScale);
        const hold=(cfg.holdWidths[col]>0?cfg.holdWidths[col]*cfg.scale:sprite.w*cfg.texScale);
        assert.ok(Math.abs(quad.w-normal)<.02||Math.abs(quad.w-hold)<.02,name+': flash respects configured width or original texture size');
        assert.ok(Math.abs(quad.x+quad.w/2-(columns.colX[col]+cfg.widths[col]/2))<.06,name+': flash centre uses note column');
        assert.ok(Math.abs(quad.y+quad.h/2-cfg.hitY)<.02,name+': flash uses the same HitPosition');
      }
      if(/^[nht]\d/.test(quad.name)){
        const col=Number(quad.name[1]);
        assert.ok(Math.abs(quad.x-columns.colX[col])<.06&&Math.abs(quad.w-cfg.widths[col])<.02,name+': note preserves skin column position/width');
      }
    }
    // Opening the UI drawer must not alter any gameplay drawing coordinates.
    await page.mouse.move(25,712);
    const open=await page.evaluate(ms=>{window.__mania.drawFrame(ms);return window.__probeQuads;},frame.ms);
    assert.deepEqual(open,snapshot.quads,name+': drawer must not change gameplay geometry');
    await page.mouse.move(25,100);
    console.log('PASS: '+name+' note/beam/flash geometry and drawer independence');
  }
  await checkSkin('owc');
  if(process.argv.includes('--all')){
    for(const key of ['R Skin','boj 1-10K',"Cho'"]){
      await page.locator('#sourceSkinSel').selectOption(key,{force:true});
      await page.waitForFunction(key=>window.__mania.skinState().loadedKey===key&&!window.__mania.skinState().loading,key,{timeout:90000});
      await checkSkin(key);
    }
    const dir=fs.mkdtempSync(path.join(os.tmpdir(),'mania-skin-effects-')),file=path.join(dir,'custom-spacing.osk');
    const build=spawnSync(process.env.OM_TEST_PYTHON||'python',['-c',`
import sys,zipfile,zlib,struct
def png(w,h):
 def chunk(t,p):return struct.pack('>I',len(p))+t+p+struct.pack('>I',zlib.crc32(t+p)&0xffffffff)
 raw=(b'\\0'+bytes([180,220,240,70])*w)*h
 return b'\\x89PNG\\r\\n\\x1a\\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',w,h,8,6,0,0,0))+chunk(b'IDAT',zlib.compress(raw))+chunk(b'IEND',b'')
with zipfile.ZipFile(sys.argv[1],'w') as z:
 z.writestr('skin.ini','[General]\\nName: Custom spacing regression\\nVersion: 2.7\\n[Mania]\\nKeys: 4\\nColumnWidth: 40,50,60,70\\nColumnSpacing: 3,5,7\\nHitPosition: 402\\nLightPosition: 413\\nLightingNWidth: 20,30,40,50\\nLightingLWidth: 0,0,0,0\\n')
 z.writestr('mania-stage-light.png',png(64,128))
 z.writestr('lightingN.png',png(36,18));z.writestr('lightingL.png',png(42,21))
 z.writestr('mania-note1.png',png(20,8));z.writestr('mania-note2.png',png(20,8))
`,file],{encoding:'utf8'});assert.equal(build.status,0,build.stderr);
    await page.locator('#fOsk').setInputFiles(file);
    await page.waitForFunction(()=>window.__mania.state.colW?.[0]===90);
    await checkSkin('new imported skin with unequal columns and spacing');
    assert.deepEqual(await page.evaluate(()=>window.__mania.state.colW),[90,112.5,135,157.5]);
  }
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
