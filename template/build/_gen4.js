const S = require("D:/Cho Osu Bot/template/star_strip.js");
const fs = require("fs");
const W = 600, base = { showTier:false, bg:null };
const mk = (v, ex) => S.renderStarStripFit(v, W, Object.assign({}, base, ex||{})).svg;
const rows = [
  ["12.66 · 只有 A（空星灰）", "点亮星仍是 #04040e，只比背景深一点", mk(12.66, { starStroke:null })],
  ["12.66 · A + B（空星灰 + 描边）", "描边让 13 颗星形浮出来", mk(12.66, {})],
  ["9.87 · A + B", "星星 #1c1c4e，描边 #9999af", mk(9.87, {})],
  ["7.32 · A + B", "亮度 0.48 > 0.30 → 不加描边，视觉与之前完全一致", mk(7.32, {})],
];
let h = `<!doctype html><html><head><meta charset="utf-8"><style>
body{margin:0;background:#0B0D11;font:13px "Segoe UI","Microsoft YaHei",sans-serif;padding:20px 24px}
.r{margin-bottom:22px}.cap{color:#8C97A9;margin-bottom:8px}
.cap b{color:#EAEEF6;font-weight:700}.cap i{color:#5F6878;font-style:normal}
</style></head><body>`;
for (const [t,s,svg] of rows) h += `<div class="r"><div class="cap"><b>${t}</b> &nbsp;<i>${s}</i></div>${svg}</div>`;
fs.writeFileSync("D:/Cho Osu Bot/template/build/compare3.html", h + "</body></html>");
console.log("rows:", rows.length);
