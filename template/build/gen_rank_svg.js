const R = require('D:/Cho Osu Bot/template/rank_theme.js');
const fs = require('fs');
const dir = 'D:/Cho Osu Bot/scratch/rank_svg/';
const page = (w,h,svg) => `<!doctype html><html><head><meta charset="utf-8"><style>html,body{margin:0;padding:0;width:${w}px;height:${h}px;background:transparent;overflow:hidden}svg{display:block}</style></head><body>${svg}</body></html>`;
for (const k of ['XH','SS','SH','S','A','B','C','D']){
  const g = R.renderBgGradient(k), gl = R.renderRankGlow(k);
  fs.writeFileSync(dir+'tint_'+k+'.html', page(g.width,g.height,g.svg));
  fs.writeFileSync(dir+'glow_'+k+'.html', page(gl.width,gl.height,gl.svg));
}
console.log('html for all 8');
