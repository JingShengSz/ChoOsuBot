const S = require("D:/Cho Osu Bot/template/star_strip.js");
const fs = require("fs");

console.log("spacing for 15 stars @ same width:", S.spacingForSameWidth(10, 1.24, 15).toFixed(4));
console.log("");

const TARGET = 600;   // 左栏可用宽度
console.log("target width = " + TARGET + "px  (showTier off)");
console.log("value   mode       stars  starSize  spacing  actual W   err");
for (const v of [1.2, 5.4, 7.32, 9.87, 10.0, 10.01, 10.77, 12.66, 14.32]) {
  const r = S.renderStarStripFit(v, TARGET, { showTier: false, bg: null });
  console.log(
    String(v).padStart(6) + "  " + r.mode.padEnd(9) +
    String(r.starCount).padStart(4) + "  " + String(r.starSize).padStart(7) + "px" +
    "  " + r.spacing.toFixed(3).padStart(6) +
    "  " + String(r.width).padStart(5) + "px" +
    "  " + String(r.widthError).padStart(5)
  );
}

fs.writeFileSync("D:/Cho Osu Bot/template/build/fit10_7.32.svg",
  S.renderStarStripFit(7.32, 600, { showTier: false, bg: null }).svg);
fs.writeFileSync("D:/Cho Osu Bot/template/build/fit15_12.66.svg",
  S.renderStarStripFit(12.66, 600, { showTier: false, bg: null }).svg);
console.log("");
console.log("wrote fit10_7.32.svg / fit15_12.66.svg");
