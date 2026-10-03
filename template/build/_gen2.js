const S = require("D:/Cho Osu Bot/template/star_strip.js");
const fs = require("fs");
const W = 600, base = { showTier:false, bg:null };
function svg(v, extra){ return S.renderStarStripFit(v, W, Object.assign({}, base, extra||{})).svg; }
const rows = [
  ["现状 · 12.66", "空星=星星色×20%  →  点亮与未点亮都近黑", svg(12.66, { emptyColor:null, emptyOpacity:0.20 })],
  ["A修法 · 12.66", "空星=固定灰 #5A6684×75%  →  能数出亮了几颗", svg(12.66, {})],
  ["A修法 · 7.32（严格对应）", "徽章金色 / 星星紫蓝  ← 你指出的不一致", svg(7.32, {})],
  ["A修法 · 7.32（同色模式）", "徽章与星星同色", svg(7.32, { colorMode:"starOnly" })],
];
let h = `<!doctype html><html><head><meta charset="utf-8"><style>
body{margin:0;background:#0B0D11;font:13px "Segoe UI","Microsoft YaHei",sans-serif;padding:20px 24px}
.r{margin-bottom:22px}.cap{color:#8C97A9;margin-bottom:8px}
.cap b{color:#EAEEF6;font-weight:700}.cap i{color:#5F6878;font-style:normal}
</style></head><body>`;
for (const [t, sub, s] of rows) h += `<div class="r"><div class="cap"><b>${t}</b> &nbsp;<i>${sub}</i></div>${s}</div>`;
h += "</body></html>";
fs.writeFileSync("D:/Cho Osu Bot/template/build/compare2.html", h);
console.log("rows:", rows.length);
