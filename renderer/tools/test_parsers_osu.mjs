// Seam check for the two `parseOsu` facts the renderer depends on:
//   * `CircleSize:` (what .osu v14 actually writes) must set the mania key count.
//   * the mirror flip the page applies to hit objects afterwards must be an involution
//     over the parsed columns.
// `parsers.js` is DOM-free, so it can be imported and exercised directly.
//
// Run: node tools/test_parsers_osu.mjs
import { parseOsu } from '../mania-web/src/parsers.js';

const fails = [];
const check = (name, got, want) => {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${name}: got ${JSON.stringify(got)} want ${JSON.stringify(want)}`);
  if (!ok) fails.push(name);
};

const body = (cs, xs) => `osu file format v14

[General]
Mode: 3

[Difficulty]
CircleSize:${cs}
OD:8

[HitObjects]
${xs.map((x, i) => `${x},192,${1000 + i * 250},1,0,0:0:0:0:`).join('\n')}
`;

// x -> column is floor(x * keys / 512)
const seven = parseOsu(body(7, [0, 73, 146, 219, 292, 365, 438, 511]));
check('CircleSize:7 sets keys', seven.keys, 7);
check('CircleSize:7 columns', seven.hitObjects.map(h => h.column), [0, 0, 1, 2, 3, 4, 5, 6]);

const four = parseOsu(body(4, [0, 128, 256, 384]));
check('CircleSize:4 sets keys', four.hitObjects.map(h => h.column), [0, 1, 2, 3]);

// short form still honoured (lazer writes `CS:` back)
const shortForm = parseOsu(body(4, [0, 128]).replace('CircleSize:', 'CS:'));
check('CS: short form still sets keys', shortForm.keys, 4);

// the mirror flip main.js applies when the replay's mods say Mirror
const mirror = (bm) => { const k = bm.keys; for (const h of bm.hitObjects) h.column = (k - 1) - h.column; };
const before = seven.hitObjects.map(h => h.column);
mirror(seven);
check('mirror flip maps c -> keys-1-c', seven.hitObjects.map(h => h.column), before.map(c => 6 - c));
mirror(seven);
check('mirror flip is its own inverse', seven.hitObjects.map(h => h.column), before);

console.log();
if (fails.length) { console.log(`FAILED (${fails.length}): ${fails.join(', ')}`); process.exit(1); }
console.log('all checks passed');
