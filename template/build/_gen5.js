const S = require("D:/Cho Osu Bot/template/star_strip.js");
const fs = require("fs");
const r = S.renderStarStripFit(7.32, 600, { showTier:false, bg:null });
fs.writeFileSync("D:/Cho Osu Bot/template/build/fit10_7.32.svg", r.svg);
const outlines = (r.svg.match(/fill="none" stroke=/g) || []).length;
console.log("regen 7.32:", r.width + "x" + r.height, "| stroke paths:", outlines, "(expect 0)");
