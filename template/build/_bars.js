const S = require("D:/Cho Osu Bot/template/star_strip.js");
const fs = require("fs");
const W = 600, H = 12;

const rows = [];
function add(title, sub, opts){
  const r = S.renderStatBar(Object.assign({ width: W, height: H, idPrefix: 'b' + rows.length }, opts));
  rows.push([title, sub + "   →  色 " + r.color + " · 填充 " + Math.round(r.fillFraction*100) + "% · 量程 " + r.scale, r.svg]);
}

// A/B/C：同一数值 OD 9.0，三种颜色映射
add("OD 9.0 · 普通量程 0..10", "【A】NUM_RAMP 按数值", { value: 9.0, min: 0, max: 10, ramp: 'num',  mapTo: 'value' });
add("OD 9.0 · 普通量程 0..10", "【B】STAR_RAMP 按数值（会偏暗）", { value: 9.0, min: 0, max: 10, ramp: 'star', mapTo: 'value' });
add("OD 9.0 · 普通量程 0..10", "【C】NUM_RAMP 按填充比例", { value: 9.0, min: 0, max: 10, ramp: 'num',  mapTo: 'fraction' });

// DA 扩展量程
add("OD -5.0 · DA 量程 -15..15", "0 在正中，向左填充", { value: -5.0, min: -15, max: 15, ramp: 'num', mapTo: 'value' });
add("OD 14.0 · DA 量程 -15..15", "接近右端", { value: 14.0, min: -15, max: 15, ramp: 'num', mapTo: 'value' });
add("HP 6.0 · 普通量程 0..10", "", { value: 6.0, min: 0, max: 10, ramp: 'num', mapTo: 'value' });
add("HP 11.0 · DA 量程 0..11", "尾部 11", { value: 11.0, min: 0, max: 11, ramp: 'num', mapTo: 'value' });

let h = `<!doctype html><html><head><meta charset="utf-8"><style>
body{margin:0;background:#0B0D11;font:13px "Segoe UI","Microsoft YaHei",sans-serif;padding:20px 24px;color:#8C97A9}
.r{margin-bottom:20px}
.cap{margin-bottom:7px}.cap b{color:#EAEEF6;font-weight:700}.cap i{color:#5F6878;font-style:normal}
</style></head><body>`;
for (const [t, s, svg] of rows)
  h += `<div class="r"><div class="cap"><b>${t}</b> &nbsp;<i>${s}</i></div>${svg}</div>`;
h += "</body></html>";
fs.writeFileSync("D:/Cho Osu Bot/template/build/bars.html", h);
console.log("rows:", rows.length);
