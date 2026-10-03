const S = require("D:/Cho Osu Bot/template/star_strip.js");
const fs = require("fs");
const r = S.renderStarStripFit(7.32, 600, { showTier:false, bg:null });
fs.writeFileSync("D:/Cho Osu Bot/template/build/fit10_7.32.svg", r.svg);
console.log("regen:", r.width + "x" + r.height, "starSize=" + r.starSize, "spacing=" + r.spacing);
// 顺便确认小星星颜色已改成跟星星同色
const m = /<path d="M[^"]*" fill="(#[0-9a-f]{6})"\/><text/.exec(r.svg);
console.log("badge star fill:", m ? m[1] : "(not parsed)", "| row star:", r.starColor, "| number:", r.numColor);
