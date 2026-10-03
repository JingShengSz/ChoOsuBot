const fs=require('fs'),path=require('path');
const sharp=require(process.env.CODEX_NODE_MODULES+'/sharp');
const base=path.resolve(__dirname,'../assets/mods/line_v1');
(async()=>{
 fs.mkdirSync(path.join(base,'placed'),{recursive:true});
 for(const [i,key] of ['hd','dt','hr','fl','ez','nf'].entries()){
  const label=Buffer.from(`<svg xmlns="http://www.w3.org/2000/svg" width="100" height="48"><text x="47" y="33" font-family="Segoe UI,Arial,sans-serif" font-size="25" fill="#A8B2C4">${key.toUpperCase()}</text></svg>`);
  const badge=await sharp(label).composite([{input:path.join(base,`mod_${key}_40.png`),left:3,top:4}]).png().toBuffer();
  await sharp({create:{width:1920,height:1080,channels:4,background:{r:0,g:0,b:0,alpha:0}}}).composite([{input:badge,left:65+i*110,top:842}]).png().toFile(path.join(base,'placed',`mod_${i+1}.png`));
 }
})();
