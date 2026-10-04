// Extra mod icons in the line_v1 visual system.
const fs = require('fs');
const path = require('path');
const sharp = require(process.env.CODEX_NODE_MODULES + '/sharp');
const root = path.resolve(__dirname, '../assets/mods');
const icons = {
  nc: ['Nightcore', '<path d="M36 68V28L76 20V60M36 39L76 31"/><ellipse cx="26" cy="70" rx="10" ry="8"/><ellipse cx="66" cy="62" rx="10" ry="8"/>'],
  cl: ['Classic', '<path d="M23 46A29 29 0 1 1 22 62M23 28V46H41M50 32V51L64 60"/>'],
};
(async () => {
  const dir = path.join(root, 'line_v1');
  const manifestPath = path.join(dir, 'manifest.json');
  const manifest = JSON.parse(fs.readFileSync(manifestPath));
  for (const [key, [name, body]] of Object.entries(icons)) {
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 100 100"><g fill="none" stroke="#A8B2C4" stroke-width="5" stroke-linecap="round" stroke-linejoin="round">${body}</g></svg>`;
    fs.writeFileSync(path.join(dir, `mod_${key}.svg`), svg);
    for (const size of [512, 32, 40, 64]) {
      await sharp(Buffer.from(svg)).resize(size, size).png().toFile(path.join(dir, `mod_${key}${size === 512 ? '' : '_' + size}.png`));
    }
    manifest.mods = manifest.mods.filter(m => m.key !== key);
    manifest.mods.push({key,label:key.toUpperCase(),name,svg:`mod_${key}.svg`,png:`mod_${key}.png`});
    const label = Buffer.from(`<svg xmlns="http://www.w3.org/2000/svg" width="100" height="48"><text x="47" y="33" font-family="Segoe UI,Arial,sans-serif" font-size="25" fill="#A8B2C4">${key.toUpperCase()}</text></svg>`);
    const badge = await sharp(label).composite([{input:path.join(dir,`mod_${key}_40.png`),left:3,top:4}]).png().toBuffer();
    fs.writeFileSync(path.join(root,`ready/mod_${key}.png`),badge);
    await sharp(badge).resize(400,192).png().toFile(path.join(root,`ready/mod_${key}@4x.png`));
    await sharp({create:{width:300,height:100,channels:4,background:'#0C1017'}})
      .composite([{input:await sharp(badge).resize(200,96).toBuffer(),left:50,top:2}])
      .png().toFile(path.join(dir,`preview_${key}.png`));
  }
  fs.writeFileSync(manifestPath, JSON.stringify(manifest,null,2));
})();
