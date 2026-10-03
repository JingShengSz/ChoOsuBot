const S = require("D:/Cho Osu Bot/template/star_strip.js");
const lum = h => { const n=parseInt(h.slice(1),16); return (0.2126*((n>>16)&255)+0.7152*((n>>8)&255)+0.0722*(n&255))/255; };
console.log("value   starColor  lum    star-outline-paths  colour");
for (const v of [1.2, 5.4, 7.32, 9.87, 10.0, 10.01, 10.77, 12.66, 14.32]) {
  const r = S.renderStarStripFit(v, 600, { showTier:false, bg:null });
  const m = r.svg.match(/fill="none" stroke="#[0-9a-f]{6}"/gi) || [];
  const c = m.length ? /stroke="(#[0-9a-f]{6})"/i.exec(m[0])[1] : "—";
  console.log(String(v).padStart(6) + "  " + r.starColor + "  " + lum(r.starColor).toFixed(3) +
              "   " + String(m.length).padStart(2) + " paths          " + c +
              "   mode=" + r.mode);
}
