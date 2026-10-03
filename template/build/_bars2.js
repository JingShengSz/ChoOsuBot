const S = require("D:/Cho Osu Bot/template/star_strip.js");
const fs = require("fs");
const W = 600, H = 12;
const rows = [];

function add(t, sub, opts){
  const r = S.renderStatBar(Object.assign({ width: W, height: H, ramp: 'num',
                                            idPrefix: 'b' + rows.length }, opts));
  rows.push([t, sub + "  →  " + r.color + " · 填充 " + Math.round(r.fillFraction*100) +
             "%  " + (r.bipolar ? "· 双极，0 点在 x=" + Math.round(r.originX) : ""), r.svg]);
}

add("OD 9.0 · 普通 0..10", "刻度每 1", { value: 9.0, min: 0, max: 10, tickStep: 1 });
add("OD 3.0 · 普通 0..10", "刻度每 1", { value: 3.0, min: 0, max: 10, tickStep: 1 });
add("OD -5.0 · DA -15..15", "★从 0 点向左填", { value: -5.0, min: -15, max: 15, tickStep: 5 });
add("OD +6.0 · DA -15..15", "从 0 点向右填", { value: 6.0, min: -15, max: 15, tickStep: 5 });
add("OD +14.0 · DA -15..15", "接近右端", { value: 14.0, min: -15, max: 15, tickStep: 5 });
add("HP 6.0 · 普通 0..10", "刻度每 1", { value: 6.0, min: 0, max: 10, tickStep: 1 });
add("HP 11.0 · DA 0..11", "尾部 11，满格", { value: 11.0, min: 0, max: 11, tickStep: 1 });

let h = `<!doctype html><html><head><meta charset="utf-8"><style>
body{margin:0;background:#0B0D11;font:13px "Segoe UI","Microsoft YaHei",sans-serif;padding:20px 24px;color:#8C97A9}
.r{margin-bottom:20px}.cap{margin-bottom:7px}
.cap b{color:#EAEEF6;font-weight:700}.cap i{color:#5F6878;font-style:normal}
</style></head><body>`;
for (const [t, s, svg] of rows) h += `<div class="r"><div class="cap"><b>${t}</b> &nbsp;<i>${s}</i></div>${svg}</div>`;
fs.writeFileSync("D:/Cho Osu Bot/template/build/bars2.html", h + "</body></html>");
console.log("rows:", rows.length);
