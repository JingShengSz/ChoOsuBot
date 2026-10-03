const S = require("D:/Cho Osu Bot/template/star_strip.js");
const fs = require("fs");

// 与页面默认一致：value 10.77, scaleMax 15, starCount 15, starSize 46, spacing 1.24
const r = S.renderStarStrip({ value: 10.77, idPrefix: "p" });
console.log("default(15 stars, 46px):", r.width + " x " + r.height,
            "| tier=" + r.tier.key, "| star=" + r.starColor, "| num=" + r.numColor,
            "| filled=" + r.filled.toFixed(2));

const toolW = 1025, toolH = 84;
console.log("tool reference        :", toolW + " x " + toolH,
            (r.width === toolW ? "WIDTH MATCH" : "WIDTH MISMATCH"),
            (r.height === toolH ? "HEIGHT MATCH" : "HEIGHT MISMATCH"));

// 不同星数下的宽度（用于版面决策）
for (const n of [10, 12, 15]) {
  const a = S.renderStarStrip({ value: 7.32, starCount: n });
  // 塞进 600px 左栏 / 1180px 通栏 时的单星尺寸
  const fit600  = (600  / (a.width  / 46)).toFixed(1);
  const fit1180 = (1180 / (a.width  / 46)).toFixed(1);
  console.log(String(n).padStart(2) + " stars @46px -> " + String(a.width).padStart(4) + "px"
    + "  | fits 600px at starSize " + fit600 + "px"
    + "  | fits 1180px at starSize " + fit1180 + "px");
}

// 导出几个样本 SVG 备用
for (const v of [7.32, 9.87, 10.77, 12.66]) {
  const s = S.renderStarStrip({ value: v, bg: null });
  fs.writeFileSync("D:/Cho Osu Bot/template/build/strip_" + v + ".svg", s.svg);
  console.log("wrote strip_" + v + ".svg  (" + s.width + "x" + s.height + ", " + s.starColor + ")");
}
