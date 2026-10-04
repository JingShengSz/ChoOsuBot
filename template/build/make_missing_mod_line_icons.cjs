// Complete the screenshot's mania MOD set using the existing BPM/OD/HP line-icon rules.
// Existing assets are never replaced: this script only creates missing named files.
const fs = require('fs');
const path = require('path');
const sharp = require(process.env.CODEX_NODE_MODULES + '/sharp');

const root = path.resolve(__dirname, '../assets/mods');
const lineDir = path.join(root, 'line_v1');
const readyDir = path.join(root, 'ready');
const color = '#A8B2C4';
const icons = {
  dc: ['Daycore', '<circle cx="50" cy="50" r="19"/><path d="M50 16V23M50 77V84M16 50H23M77 50H84M26 26L31 31M69 69L74 74M74 26L69 31M31 69L26 74"/>'],
  nr: ['No Release', '<path d="M31 19V59M31 31L67 24V54M31 42L67 35"/><ellipse cx="23" cy="62" rx="9" ry="7"/><path d="M52 69H80M70 59L80 69L70 79"/>'],
  fi: ['Fade In', '<path d="M24 72V58M37 72V48M50 72V38M63 72V28M76 72V18M19 79H81"/>'],
  co: ['Cover', '<path d="M20 26H80V74H20Z M20 47H80M32 47V74M44 47V74M56 47V74M68 47V74"/>'],
  ac: ['Accuracy Challenge', '<circle cx="50" cy="50" r="29"/><circle cx="50" cy="50" r="14"/><path d="M50 14V24M50 76V86M14 50H24M76 50H86"/><circle cx="50" cy="50" r="2"/>'],
  rd: ['Random', '<path d="M20 30H37C51 30 49 70 64 70H77M68 61L77 70L68 79M20 70H37C51 70 49 30 64 30H77M68 21L77 30L68 39"/>'],
  ds: ['Dual Stages', '<path d="M22 26H43V74H22ZM57 26H78V74H57ZM32 37V61M68 37V61"/>'],
  mr: ['Mirror', '<path d="M50 20V80M39 28L22 50L39 72M61 28L78 50L61 72"/>'],
  da: ['Difficulty Adjust', '<path d="M19 30H81M19 50H81M19 70H81"/><circle cx="37" cy="30" r="7"/><circle cx="64" cy="50" r="7"/><circle cx="45" cy="70" r="7"/>'],
  in: ['Invert', '<circle cx="50" cy="50" r="29"/><path d="M50 21C66 32 66 43 50 50C34 57 34 68 50 79"/><circle cx="50" cy="36" r="2"/><circle cx="50" cy="64" r="2"/>'],
  cs: ['Constant Speed', '<path d="M23 66A31 31 0 0 1 77 66M31 70H69M50 62L67 42M30 50L25 47M50 36V30M70 50L75 47"/>'],
  ho: ['Hold Off', '<path d="M25 27V67M25 27L56 21V61"/><ellipse cx="17" cy="68" rx="8" ry="6"/><ellipse cx="48" cy="62" rx="8" ry="6"/><path d="M67 35L79 47M79 35L67 47M67 59L79 71M79 59L67 71"/>'],
  wu: ['Wind Up', '<path d="M19 72C37 72 48 61 48 49C48 39 56 31 71 31H80M69 20L80 31L69 42M21 83H42M21 62H33"/>'],
  wd: ['Wind Down', '<path d="M80 72C62 72 51 61 51 49C51 39 43 31 28 31H19M30 20L19 31L30 42M58 83H79M67 62H79"/>'],
  mu: ['Muted', '<path d="M18 41H35L52 28V72L35 59H18ZM65 42L81 58M81 42L65 58"/>'],
  as: ['Adaptive Speed', '<path d="M25 63A28 28 0 0 1 70 32M75 37V25H63M30 72A28 28 0 0 0 75 54M50 61L64 43M26 79H74"/>'],
};

function source(body) {
  return `<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 100 100"><g fill="none" stroke="${color}" stroke-width="5" stroke-linecap="round" stroke-linejoin="round">${body}</g></svg>`;
}

async function main() {
  fs.mkdirSync(lineDir, {recursive: true});
  fs.mkdirSync(readyDir, {recursive: true});
  const manifestPath = path.join(lineDir, 'manifest.json');
  const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
  const created = [];
  for (const [key, [name, body]] of Object.entries(icons)) {
    const stem = `mod_${key}`;
    const paths = [
      path.join(lineDir, `${stem}.svg`),
      ...[512, 32, 40, 64].map(size => path.join(lineDir, `${stem}${size === 512 ? '' : '_' + size}.png`)),
      path.join(readyDir, `${stem}.png`),
      path.join(readyDir, `${stem}@4x.png`),
    ];
    const present = paths.filter(file => fs.existsSync(file));
    if (present.length === paths.length) continue;
    if (present.length) throw new Error(`Incomplete existing asset set for ${key}; refusing to overwrite`);

    const svg = source(body);
    fs.writeFileSync(paths[0], svg, {flag: 'wx'});
    for (const size of [512, 32, 40, 64]) {
      await sharp(Buffer.from(svg)).resize(size, size).png().toFile(path.join(lineDir, `${stem}${size === 512 ? '' : '_' + size}.png`));
    }
    const label = Buffer.from(`<svg xmlns="http://www.w3.org/2000/svg" width="100" height="48"><text x="47" y="33" font-family="Segoe UI,Arial,sans-serif" font-size="25" fill="${color}">${key.toUpperCase()}</text></svg>`);
    const badge = await sharp(label).composite([{input: path.join(lineDir, `${stem}_40.png`), left: 3, top: 4}]).png().toBuffer();
    fs.writeFileSync(path.join(readyDir, `${stem}.png`), badge, {flag: 'wx'});
    await sharp(badge).resize(400, 192).png().toFile(path.join(readyDir, `${stem}@4x.png`));
    created.push(key);
  }

  for (const [key, [name]] of Object.entries(icons)) {
    if (!manifest.mods.some(item => item.key === key)) {
      manifest.mods.push({key, label: key.toUpperCase(), name, svg: `mod_${key}.svg`, png: `mod_${key}.png`});
    }
  }
  fs.writeFileSync(manifestPath, JSON.stringify(manifest, null, 2) + '\n');

  const mods = manifest.mods;
  const columns = 5, cellW = 220, cellH = 150;
  const rows = Math.ceil(mods.length / columns);
  const width = columns * cellW + 40, height = rows * cellH + 100;
  let layout = `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}"><rect width="100%" height="100%" fill="#0C1017"/><g font-family="Segoe UI,Arial,sans-serif"><text x="24" y="40" fill="#EAEEF6" font-size="24">MOD LINE ICONS — ${mods.length} TOTAL</text><text x="24" y="66" fill="${color}" font-size="15">${Object.keys(icons).length} new MODs · 32px and 40px assets included</text>`;
  const composites = [];
  for (const [i, mod] of mods.entries()) {
    const x = 20 + (i % columns) * cellW, y = 80 + Math.floor(i / columns) * cellH;
    const added = Object.hasOwn(icons, mod.key);
    const nameSize = mod.name.length > 16 ? 12 : 15;
    layout += `<rect x="${x}" y="${y}" width="200" height="132" rx="10" fill="#151B25"/><text x="${x + 80}" y="${y + 47}" fill="#EAEEF6" font-size="19">${mod.label}</text><text x="${x + 80}" y="${y + 76}" fill="${color}" font-size="${nameSize}">${mod.name}</text><text x="${x + 80}" y="${y + 104}" fill="${added ? '#76D7B0' : '#788596'}" font-size="12">${added ? 'NEW' : 'EXISTING'}</text>`;
    composites.push({input: path.join(lineDir, `mod_${mod.key}_64.png`), left: x + 10, top: y + 24});
  }
  layout += '</g></svg>';
  await sharp(Buffer.from(layout)).composite(composites).png().toFile(path.join(lineDir, 'preview_complete.png'));
  console.log(`Created: ${created.map(x => x.toUpperCase()).join(', ') || '(none)'}`);
  console.log(`Manifest: ${mods.length} mods; preview_complete.png`);
}

main().catch(error => { console.error(error); process.exit(1); });
