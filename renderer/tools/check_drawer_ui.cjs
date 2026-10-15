const assert=require('node:assert/strict');
const path=require('node:path');

module.exports=async function checkDrawer(page,artifacts,localId,base){
  await page.setViewportSize({width:979,height:884});
  await page.mouse.move(100,100);
  await page.waitForFunction(()=>!document.getElementById('drawer').classList.contains('open'));
  assert.equal(await page.locator('#drawer').evaluate(el=>el.inert),true);
  await page.mouse.move(25,page.viewportSize().height-8);
  await page.waitForFunction(()=>Math.abs(new DOMMatrix(getComputedStyle(document.getElementById('drawer')).transform).m42)<.5);
  assert.equal(await page.locator('#drawerToggle').getAttribute('aria-expanded'),'true');
  assert.equal(await page.locator('#drawer').evaluate(el=>el.scrollWidth>innerWidth),false);
  await page.screenshot({path:path.join(artifacts,'drawer-desktop.png')});
  await page.locator('#playSpeed').selectOption('1.5');
  assert.equal(await page.locator('#audio').evaluate(el=>el.playbackRate),1.5);
  await page.locator('#bgDim').evaluate(el=>{el.value=60;el.dispatchEvent(new Event('input',{bubbles:true}));});
  assert.equal(await page.locator('#bgDimVal').innerText(),'60%');
  assert.equal(await page.locator('#bgDim').evaluate(el=>el.style.getPropertyValue('--range-fill')),'60%');
  await page.locator('#bgBlur').evaluate(el=>{el.value=5;el.dispatchEvent(new Event('input',{bubbles:true}));});
  assert.equal(await page.locator('#bgBlurVal').innerText(),'5');
  await page.locator('#volCircle').focus();await page.keyboard.press('ArrowLeft');
  assert.equal(await page.locator('#volCircle').getAttribute('aria-valuenow'),'95');
  await page.locator('#seek').focus();await page.keyboard.press('End');
  assert.ok((await page.evaluate(()=>window.__mania.playback().timeMs))>0);
  await page.locator('#btnReset').click();
  assert.equal(await page.evaluate(()=>window.__mania.playback().timeMs),await page.evaluate(()=>window.__mania.sceneState().timeline.start));
  await page.locator('#btnPlay').click();
  await page.waitForFunction(()=>window.__mania.playback().playing);
  await page.locator('#btnPlay').click();
  assert.equal(await page.evaluate(()=>window.__mania.playback().playing),false);
  await page.locator('#stage').click({position:{x:100,y:100}});
  await page.waitForFunction(()=>!document.getElementById('drawer').classList.contains('open'));

  // Keyboard entry remains available without pointer proximity.
  await page.locator('#drawerToggle').focus();await page.keyboard.press('Enter');
  await page.waitForFunction(()=>document.getElementById('drawer').classList.contains('open'));
  await page.keyboard.press('Escape');
  await page.waitForFunction(()=>!document.getElementById('drawer').classList.contains('open'));
  assert.equal(await page.locator('#drawerToggle').evaluate(el=>document.activeElement===el),true);

  // Same local-ID entry as the renderer's automation, plus touch and reduced motion.
  const context=await page.context().browser().newContext({viewport:{width:390,height:844},hasTouch:true,isMobile:true,reducedMotion:'reduce'});
  try{
    await context.addInitScript(()=>{window.__maniaAutomation=true;});
    const touch=await context.newPage();await touch.goto(base);
    await touch.locator('#bidInput').fill(localId);await touch.locator('#btnLoad').click();
    await touch.locator('#sourceScene').waitFor({state:'hidden',timeout:45000});
    await touch.locator('#drawerToggle').tap();
    assert.equal(await touch.locator('#drawer').evaluate(el=>el.inert),false);
    assert.equal(await touch.locator('#drawer').evaluate(el=>new DOMMatrix(getComputedStyle(el).transform).m42),0);
    assert.equal(await touch.locator('#drawer').evaluate(el=>el.scrollWidth>innerWidth),false);
    await touch.screenshot({path:path.join(artifacts,'drawer-mobile.png')});
    await touch.locator('#btnDrawerClose').tap();
    assert.equal(await touch.locator('#drawer').evaluate(el=>el.inert),true);
  }finally{await context.close();}
  console.log('PASS: hover-open/auto-close, playback controls, sliders/volume/seek, keyboard, touch, reduced motion and local-ID automation');
};
