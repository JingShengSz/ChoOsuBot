// Local review candidates for beatmap status icons. Does not replace live assets.
const fs = require('fs');
const path = require('path');
const sharp = require(process.env.CODEX_NODE_MODULES + '/sharp');

const output = path.resolve(__dirname, '../assets/ui_extra/status_review');
const icons = {
  ranked: {
    label: 'Rank', color: '#159FEC',
    body: '<path d="M50 10L85 45L72 58L50 36L28 58L15 45Z" fill="#159FEC" stroke="#0879BB" stroke-width="2.5"/><path d="M50 47L81 78L68 91L50 73L32 91L19 78Z" fill="#159FEC" stroke="#0879BB" stroke-width="2.5"/>'
  },
  loved: {
    label: 'Loved', color: '#F46BAA',
    body: '<path d="M50 82C47 82 44 80 40 77C29 68 16 57 15 42C14 28 22 19 34 19C42 19 48 24 50 31C52 24 58 19 66 19C78 19 86 28 85 42C84 57 71 68 60 77C56 80 53 82 50 82Z" fill="#F46BAA" stroke="#BF4382" stroke-width="3" stroke-linejoin="round"/>'
  },
  graveyard: {
    label: '坟图', color: '#897D9A',
    body: '<path d="M24 79V43C24 27 35 18 50 18C65 18 76 27 76 43V79Z" fill="#897D9A" stroke="#5F576E" stroke-width="3"/><path d="M50 34V61M39 44H61" stroke="#E5DBED" stroke-width="5" stroke-linecap="round"/><path d="M15 82H85" stroke="#5F576E" stroke-width="6" stroke-linecap="round"/>'
  },
  qualified: {
    label: '过审', color: '#F6C751',
    body: '<path d="M50 13L60 20L72 19L78 30L88 37L84 50L88 63L78 70L72 81L60 80L50 87L40 80L28 81L22 70L12 63L16 50L12 37L22 30L28 19L40 20Z" fill="#F6C751" stroke="#AD7D2B" stroke-width="3"/><path d="M31 49L44 62L70 36" fill="none" stroke="#7B5722" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/>'
  },
  pending: {
    label: '制作中', color: '#71C3BD',
    body: '<path d="M24 20H61L76 35V78H24Z" fill="#71C3BD" stroke="#348E8D" stroke-width="3"/><path d="M61 20V35H76" fill="none" stroke="#348E8D" stroke-width="3"/><path d="M36 65L39 53L66 32L73 39L46 66Z" fill="#F7C969" stroke="#A87535" stroke-width="3" stroke-linejoin="round"/><path d="M36 65L46 66L32 70Z" fill="#E9DED0" stroke="#A87535" stroke-width="3" stroke-linejoin="round"/>'
  },
};

function svg(body) {
  return `<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 100 100">${body}</svg>`;
}

async function main() {
  fs.mkdirSync(output, {recursive: true});
  const entries = Object.entries(icons);
  for (const [name, icon] of entries) {
    const source = Buffer.from(svg(icon.body));
    fs.writeFileSync(path.join(output, `${name}.svg`), source);
    for (const size of [512, 40, 36, 32]) {
      const suffix = size === 512 ? '' : `_${size}`;
      await sharp(source).resize(size, size).png().toFile(path.join(output, `${name}${suffix}.png`));
    }
  }

  const width = 1120, height = 435;
  let board = `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}"><rect width="100%" height="100%" fill="#101722"/><g font-family="Segoe UI,Microsoft YaHei,Arial,sans-serif"><text x="32" y="43" font-size="25" fill="#F4F7FA">谱面状态图标 · 审查稿</text><text x="32" y="72" font-size="15" fill="#A8B2C4">透明 PNG / SVG · 下方展示成绩图中的 36px 显示尺寸</text>`;
  const composites = [];
  for (const [index, [name, icon]] of entries.entries()) {
    const x = 30 + index * 220;
    board += `<rect x="${x}" y="95" width="200" height="300" rx="16" fill="#1D2939"/><text x="${x + 100}" y="282" text-anchor="middle" font-size="22" fill="#F4F7FA">${icon.label}</text><text x="${x + 100}" y="368" text-anchor="middle" font-size="14" fill="#A8B2C4">36px</text>`;
    composites.push({input: await sharp(path.join(output, `${name}.png`)).resize(124, 124).png().toBuffer(), left: x + 38, top: 112});
    composites.push({input: path.join(output, `${name}_36.png`), left: x + 82, top: 309});
  }
  board += '</g></svg>';
  await sharp(Buffer.from(board)).composite(composites).png().toFile(path.join(output, 'preview.png'));
  console.log(output);
}

main().catch(error => { console.error(error); process.exit(1); });
