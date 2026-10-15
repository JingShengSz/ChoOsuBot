// Run against the local renderer server; creates a tiny two-difficulty chart package.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {spawnSync} = require('node:child_process');
const {chromium} = require('playwright');

const base=process.argv[2]||'http://127.0.0.1:8773/';
const artifacts=path.resolve(process.argv[3]||'scratch/om-source-ui');
fs.mkdirSync(artifacts,{recursive:true});
const fixtureDir=fs.mkdtempSync(path.join(os.tmpdir(),'om-source-ui-'));
const fixture=path.join(fixtureDir,'entry-test.osz');
const build=spawnSync(process.env.OM_TEST_PYTHON||'python',['-c',`
import io,sys,wave,zipfile
audio=io.BytesIO()
with wave.open(audio,'wb') as w:
 w.setnchannels(1);w.setsampwidth(2);w.setframerate(8000);w.writeframes(b'\\0' * 32000)
with zipfile.ZipFile(sys.argv[1],'w',zipfile.ZIP_DEFLATED) as z:
 z.writestr('audio.wav',audio.getvalue())
 for version in ['Easy','Hard']:
  z.writestr(version+'.osu',f'''osu file format v14
[General]
AudioFilename: audio.wav
Mode: 3
[Metadata]
Title: Entry UI Test
Artist: Local Fixture
Creator: Test
Version: {version}
[Difficulty]
HPDrainRate: 5
CircleSize: 4
OverallDifficulty: 5
ApproachRate: 5
SliderMultiplier: 1
SliderTickRate: 1
[TimingPoints]
0,500,4,2,1,100,1,0
[HitObjects]
64,192,500,1,0,0:0:0:0:
192,192,1000,1,0,0:0:0:0:
''')
`,fixture],{encoding:'utf8'});
assert.equal(build.status,0,build.stderr);

(async()=>{
  const browser=await chromium.launch({headless:true,
    ...(process.env.OM_TEST_CHROME?{executablePath:process.env.OM_TEST_CHROME}:{}),
    args:['--no-proxy-server']});
  try{
    const page=await browser.newPage({viewport:{width:1440,height:1000}});
    const errors=[];page.on('pageerror',error=>errors.push(error.message));
    let imports=0;page.on('request',r=>{if(r.url().includes('/api/import_osz'))imports++;});
    await page.goto(base);
    await page.waitForFunction(()=>window.__mania?.skinState().loadedKey,{},{timeout:45000});
    await page.screenshot({path:path.join(artifacts,'desktop.png')});
    assert.equal(await page.locator('#sourceScene').evaluate(el=>el.scrollWidth>innerWidth),false);

    await page.locator('#btnLoad').click();
    await page.locator('#sourceError').filter({hasText:'请输入谱面 ID'}).waitFor();
    await page.locator('#bidInput').fill('invalid');await page.locator('#bidInput').press('Enter');
    await page.locator('#sourceError').filter({hasText:'请填写数字'}).waitFor();
    assert.equal(await page.locator('#bidInput').getAttribute('aria-invalid'),'true');
    await page.locator('#bidInput').fill('');

    await page.locator('#fOsr').setInputFiles({name:'demo.mrv',mimeType:'application/octet-stream',buffer:Buffer.from('demo')});
    assert.equal(await page.locator('#replayFileName').innerText(),'demo.mrv');
    assert.equal(await page.locator('#sourcePairHint').getAttribute('class'),'source-help source-pair-hint needs-package');
    await page.locator('#btnLoad').click();
    await page.locator('#sourceError').filter({hasText:'Malody 回放需要上传对应谱面包'}).waitFor();
    await page.locator('#btnClearOsr').click();
    assert.equal(await page.locator('#fOsr').evaluate(el=>el.files.length),0);
    assert.equal(await page.locator('#replayFileName').innerText(),'选择或拖入回放');

    // Drop validation must leave an already selected valid file unchanged.
    await page.locator('#fOsr').setInputFiles({name:'keep.osr',mimeType:'application/octet-stream',buffer:Buffer.from('demo')});
    await page.locator('[data-input=fOsr]').evaluate(el=>{
      const dataTransfer=new DataTransfer();dataTransfer.items.add(new File(['bad'],'wrong.txt'));
      el.dispatchEvent(new DragEvent('drop',{dataTransfer,bubbles:true,cancelable:true}));
    });
    await page.locator('#replayFileError').filter({hasText:'请放入一个'}).waitFor();
    assert.equal(await page.locator('#fOsr').evaluate(el=>el.files[0].name),'keep.osr');
    await page.locator('#btnClearOsr').click();
    await page.locator('[data-input=fOsr]').evaluate(el=>{
      const dataTransfer=new DataTransfer();dataTransfer.items.add(new File(['demo'],'dropped.osr'));
      el.dispatchEvent(new DragEvent('drop',{dataTransfer,bubbles:true,cancelable:true}));
    });
    assert.equal(await page.locator('#replayFileName').innerText(),'dropped.osr');
    await page.locator('#btnClearOsr').click();

    // Real package import and rendering; delays expose the actual loading state.
    await page.route('**/api/import_osz',async route=>{
      await new Promise(resolve=>setTimeout(resolve,350));
      await route.continue();
    });
    await page.locator('#fMap').setInputFiles(fixture);await page.locator('#btnLoad').click();
    await page.locator('#sourceLoading').waitFor({state:'visible'});
    await page.screenshot({path:path.join(artifacts,'loading.png')});
    try {await page.locator('#packageChoice').waitFor({state:'visible'});} catch(error) {
      throw new Error('Package selection failed: '+await page.locator('#sourceError').innerText()+'; '+error.message);
    }
    assert.equal(await page.locator('#packageDifficulty option').count(),3);
    assert.equal(await page.locator('#sourceError').getAttribute('class'),'source-error is-notice');
    await page.locator('#packageDifficulty').selectOption({index:1});
    const original=await page.locator('#packageDifficulty').inputValue();
    await page.route('**/api/beatmap_osu/*',async route=>{
      await new Promise(resolve=>setTimeout(resolve,350));await route.continue();
    });
    await page.locator('#btnLoad').click();
    await page.locator('#sourceLoading[data-stage=chart]').waitFor({state:'visible'});
    await page.locator('#sourceScene').waitFor({state:'hidden',timeout:45000});
    assert.equal(imports,1,'Choosing a difficulty must reuse the imported package');
    assert.equal(await page.locator('#btnPlay').isEnabled(),true);
    await require('./check_drawer_ui.cjs')(page,artifacts,original,base);
    await page.mouse.move(25,page.viewportSize().height-8);
    await page.locator('#btnSource').click();
    assert.equal(await page.locator('#fMap').evaluate(el=>el.files[0].name),'entry-test.osz');
    await page.locator('#btnClearMap').click();
    assert.equal(await page.locator('#packageChoice').isVisible(),false);

    // Error recovery preserves uploaded files and enables a retry.
    await page.locator('#fMap').setInputFiles(fixture);
    await page.unroute('**/api/import_osz');
    await page.route('**/api/import_osz',r=>r.fulfill({status:400,json:{error:'测试：谱面包导入失败'}}));
    await page.locator('#btnLoad').click();
    await page.locator('#sourceError').filter({hasText:'测试：谱面包导入失败'}).waitFor();
    assert.equal(await page.locator('#fMap').evaluate(el=>el.files.length),1);
    assert.equal(await page.locator('#btnLoad').isEnabled(),true);
    await page.screenshot({path:path.join(artifacts,'error.png')});

    await page.setViewportSize({width:390,height:844});
    await page.emulateMedia({reducedMotion:'reduce'});
    assert.equal(await page.locator('#sourceScene').evaluate(el=>el.scrollWidth>innerWidth),false);
    await page.locator('#btnLoad').scrollIntoViewIfNeeded();
    assert.ok((await page.locator('#btnLoad').boundingBox()).width>=120);
    await page.screenshot({path:path.join(artifacts,'mobile.png'),fullPage:true});
    await page.locator('#sourceScene').evaluate(el=>{el.scrollTop=0;});
    await page.screenshot({path:path.join(artifacts,'mobile-top.png')});
    assert.equal(await page.locator('.source-loading-track i').evaluateAll(elements=>elements.every(el=>getComputedStyle(el,'::after').animationName==='none')),true);
    assert.deepEqual(errors,[]);
    console.log('PASS: desktop/mobile, form validation, file selection/drop/clear, Malody pairing, real package import, difficulty reuse, real playback, loading stages, retry preservation, reduced motion');
    console.log('Artifacts: '+artifacts+'; imported chart: '+original);
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
