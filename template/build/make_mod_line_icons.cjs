// MOD pictograms matching the BPM / OD / HP attribute icon specification.
const fs = require('fs');
const path = require('path');
const sharp = require(process.env.CODEX_NODE_MODULES + '/sharp');
const out = path.resolve(__dirname, '../assets/mods/line_v1');
const color = '#A8B2C4';
const icons = {
  hd: ['HD', 'Hidden', '<path d="M21 39C27 28 38 21 50 21C64 21 76 31 83 43C77 54 66 62 53 64M35 62C28 58 22 51 17 43M40 35A14 14 0 0 1 61 52M19 17L81 79" transform="translate(0 7)"/>'],
  dt: ['DT', 'Double Time', '<path d="M22 22L48 50L22 78M52 22L78 50L52 78"/>'],
  ht: ['HT', 'Half Time', '<path d="M65 22L37 50L65 78"/>'],
  hr: ['HR', 'Hard Rock', '<path d="M50 80V20M24 46L50 20L76 46"/>'],
  ez: ['EZ', 'Easy', '<path d="M50 20V80M24 54L50 80L76 54"/>'],
  fl: ['FL', 'Flashlight', '<path d="M19 39H47L63 28V72L47 61H19ZM47 39V61M28 39V31H38V39M74 35L82 30M74 50H84M74 65L82 70"/>'],
  nf: ['NF', 'No Fail', '<path d="M50 19C40 26 30 29 22 30V49C22 66 34 77 50 83C66 77 78 66 78 49V30C68 29 59 25 50 19Z"/>'],
  so: ['SO', 'Spun Out', '<path d="M79 65C86 47 75 24 57 20C36 15 19 30 19 49C19 67 33 81 49 81C64 81 74 70 74 57C74 44 64 34 52 34C41 34 32 43 32 53C32 63 40 69 48 69C56 69 61 63 61 56C61 50 56 46 51 47"/>'],
  sd: ['SD', 'Sudden Death', '<path d="M34 78V66C24 62 20 53 20 43C20 26 33 18 50 18C67 18 80 26 80 43C80 53 76 62 66 66V78ZM44 68V78M56 68V78"/><circle cx="37" cy="44" r="7"/><circle cx="63" cy="44" r="7"/>'],
  pf: ['PF', 'Perfect', '<path d="M50 18L59 39L82 42L64 58L69 81L50 69L31 81L36 58L18 42L41 39Z"/>'],
};
function svg(body, size = 512) {
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 100 100"><g fill="none" stroke="${color}" stroke-width="5" stroke-linecap="round" stroke-linejoin="round">${body}</g></svg>`;
}
async function main() {
  fs.mkdirSync(out, { recursive: true });
  const composites = [];
  let sheet = `<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="750"><rect width="1200" height="750" fill="#0C1017"/><g font-family="Segoe UI,Arial,sans-serif"><text x="40" y="46" fill="#EAEEF6" font-size="25">MOD / ATTRIBUTE — LINE ICONS</text><text x="40" y="76" fill="${color}" font-size="16">#A8B2C4 · rounded strokes · transparent PNG + SVG</text>`;
  for (const [i, [key, [label, name, body]]] of Object.entries(icons).entries()) {
    const source = svg(body);
    fs.writeFileSync(path.join(out, `mod_${key}.svg`), source);
    for (const size of [512, 32, 40, 64]) {
      const suffix = size === 512 ? '' : `_${size}`;
      await sharp(Buffer.from(source)).resize(size, size).png().toFile(path.join(out, `mod_${key}${suffix}.png`));
    }
    const x = 40 + (i % 5) * 232, y = 108 + Math.floor(i / 5) * 210;
    sheet += `<rect x="${x}" y="${y}" width="212" height="190" rx="14" fill="#151B25"/><text x="${x + 18}" y="${y + 139}" fill="#EAEEF6" font-size="20">${label}</text><text x="${x + 18}" y="${y + 165}" fill="${color}" font-size="14">${name}</text>`;
    composites.push({input: await sharp(Buffer.from(source)).resize(110,110).png().toBuffer(), left:x+12, top:y+6});
    composites.push({input: path.join(out, `mod_${key}_32.png`), left:x+155, top:y+52});
  }
  sheet += '<text x="40" y="568" fill="#EAEEF6" font-size="20">EXISTING REFERENCES / 40 PX</text><text x="40" y="665" fill="#EAEEF6" font-size="20">SCORE CARD ROW / 40 PX</text>';
  for (const [i,key] of ['bpm','od','hp'].entries()) {
    composites.push({input: await sharp(path.resolve(out, '../../attrs',key+'.png')).resize(40,40).png().toBuffer(),left:40+i*180,top:583});
    sheet += `<text x="${92+i*180}" y="609" fill="${color}" font-size="17">${key.toUpperCase()}</text>`;
  }
  for (const [i,key] of ['hd','dt','hr','fl','ez','nf'].entries()) {
    const x=40+i*150;
    composites.push({input:path.join(out,`mod_${key}_40.png`),left:x,top:683});
    sheet += `<text x="${x+45}" y="710" fill="${color}" font-size="20">${key.toUpperCase()}</text>`;
  }
  sheet += '</g></svg>';
  await sharp(Buffer.from(sheet)).composite(composites).png().toFile(path.join(out,'preview.png'));
  fs.writeFileSync(path.join(out,'manifest.json'),JSON.stringify({color,strokeWidth:26,canvas:512,style:'rounded monochrome outline',mods:Object.entries(icons).map(([key,[label,name]])=>({key,label,name,svg:`mod_${key}.svg`,png:`mod_${key}.png`}))},null,2));
  console.log(out);
}
main().catch(e=>{console.error(e);process.exit(1);});
