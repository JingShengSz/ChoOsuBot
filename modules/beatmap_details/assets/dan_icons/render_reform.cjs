const {chromium}=require('playwright');
const path=require('node:path');
(async()=>{
 const browser=await chromium.launch({headless:true,channel:'chrome'});
 try{
  const page=await browser.newPage({viewport:{width:1920,height:1080},deviceScaleFactor:1});
  for(let n=1;n<=10;n++){
   await page.goto('file:///'+path.join(__dirname,`reform${n}.svg`).replace(/\\/g,'/'));
   await page.screenshot({path:path.join(__dirname,`reform${n}.png`),omitBackground:true});
  }
 }finally{await browser.close();}
})();
