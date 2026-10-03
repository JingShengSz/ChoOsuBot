/* 色阶自检：确认点亮的星星永远比未点亮的空星亮。
 *
 * 出问题的那版 STAR_RAMP 尾部压到了 #040410 / #000000，
 * 比空星（#5A6684 @ 0.75）还暗，等于"点亮"看起来比"没点亮"更黑。
 *
 * 跑法：node tools/check_ramps.js
 * 退出码 0 = 通过，1 = 有颜色低于下限。
 */
const S = require('../star_strip.js');

function srgb(v){ v /= 255; return v <= 0.04045 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }
function lum(hex){
  const r = parseInt(hex.substr(1,2),16), g = parseInt(hex.substr(3,2),16), b = parseInt(hex.substr(5,2),16);
  return 0.2126*srgb(r) + 0.7152*srgb(g) + 0.0722*srgb(b);
}
/* 空星在深色底板上的合成亮度：emptyColor 以 emptyOpacity 叠在底板色上 */
function emptyLum(bgHex){
  const e = S.DEFAULTS.emptyColor, a = S.DEFAULTS.emptyOpacity;
  const bg = bgHex || '#0B0F18';
  const mix = [1,3,5].map(i => a*parseInt(e.substr(i,2),16) + (1-a)*parseInt(bg.substr(i,2),16));
  return lum('#' + mix.map(v => Math.round(v).toString(16).padStart(2,'0')).join(''));
}

const BG = '#0B0F18';
const eLum = emptyLum(BG);
const floor = S.STAR_RAMP_MIN_LUM;

console.log(`空星(未点亮) 合成亮度      = ${eLum.toFixed(4)}`);
console.log(`STAR_RAMP 下限要求          = ${floor.toFixed(4)}`);
const margin = floor - eLum;
console.log(`余量 = ${margin >= 0 ? '+' : ''}${margin.toFixed(4)}（正数才安全）`);
console.log('');
console.log(' 星数    颜色       相对亮度   对比度(对空星)  判定');
console.log(' ' + '-'.repeat(58));

let bad = 0;
for (const [v, hex] of S.STAR_RAMP){
  const L = lum(hex);
  const hi = Math.max(L, eLum), lo = Math.min(L, eLum);
  const ratio = (hi + 0.05) / (lo + 0.05);
  const ok = L >= floor;
  if (!ok) bad++;
  console.log(` ${String(v).padStart(4)}   ${hex}   ${L.toFixed(4)}   ${ratio.toFixed(2).padStart(8)}:1      ${ok ? 'ok' : 'LOW'}`);
}

console.log('');
console.log(`最低的一档 = ${Math.min(...S.STAR_RAMP.map(([,h]) => lum(h))).toFixed(4)}`);
if (bad){ console.log(`\n失败：${bad} 个颜色低于下限 ${floor}。点亮的星会比没点亮的还暗。`); process.exit(1); }
console.log('\n通过：所有星星色都亮过空星。');
