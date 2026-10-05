// Two compact score-card pictograms: length and key count.
// Status icons have their own colored source in make_status_icon_review.cjs.
// Keep this generator scoped to the neutral icons so a rerun cannot replace
// the approved status artwork with the old gray outlines.
const fs = require('fs');
const path = require('path');
const sharp = require(process.env.CODEX_NODE_MODULES + '/sharp');
const out = path.resolve(__dirname, '../assets/ui_extra');
fs.mkdirSync(out, {recursive:true});
const icons = {
  length: '<circle cx="50" cy="53" r="30"/><path d="M50 53V34M50 53L63 61M39 16H61M50 16V23M73 25L80 19"/>',
  keys: '<rect x="16" y="22" width="68" height="57" rx="5"/><path d="M33 22V78M50 22V78M67 22V78M27 22V51H39V22M44 22V51H56V22M61 22V51H73V22"/>',
};
async function render(name, body) {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 100 100"><g fill="none" stroke="#A8B2C4" stroke-width="5" stroke-linecap="round" stroke-linejoin="round">${body}</g></svg>`;
  fs.writeFileSync(path.join(out,`${name}.svg`),svg);
  for (const size of [512,40,32]) {
    await sharp(Buffer.from(svg)).resize(size,size).png().toFile(path.join(out,`${name}${size===512?'':'_'+size}.png`));
  }
}
(async()=>{for(const [name,body] of Object.entries(icons)) await render(name,body)})().catch(e=>{console.error(e);process.exit(1)});
