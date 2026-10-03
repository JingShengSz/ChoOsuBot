// .osu beatmap parser
export function parseOsu(text) {
  const bm = { keys: 4, mode: 3, title: '', artist: '', version: '', audioFilename: '', bgFilename: '',
    beatmapID: 0, beatmapSetID: 0, hitObjects: [], timings: [], duration: 0, cs: 4, od: 8, hp: 5, ar: 5 };
  let section = '';
  const lines = text.split(/\r?\n/);
  for (const line of lines) {
    const s = line.trim();
    if (s.startsWith('[')) { section = s.slice(1, -1).toLowerCase(); continue; }
    if (!s || s.startsWith('//')) continue;
    if (section === 'general') {
      const [k, v] = splitKV(s);
      if (k === 'mode') bm.mode = +v;
      if (k === 'audiofilename') bm.audioFilename = v;
    } else if (section === 'metadata') {
      const [k, v] = splitKV(s);
      if (k === 'title') bm.title = v;
      if (k === 'artist') bm.artist = v;
      if (k === 'version') bm.version = v;
      // The .osu carries its own ids, so audio/background can be located without
      // any metadata API (sayobot being down must not cost us the whole track).
      if (k === 'beatmapid') bm.beatmapID = +v || 0;
      if (k === 'beatmapsetid') bm.beatmapSetID = +v || 0;
    } else if (section === 'difficulty') {
      const [k, v] = splitKV(s);
      // `.osu` v14 writes the mania key count as `CircleSize:` — `CS:` is only the
      // short form lazer writes back. Matching just `cs` left `bm.keys` on its
      // default 4 for EVERY chart, so a 7K map rendered as 4 lanes.
      if (k === 'cs' || k === 'circlesize') { bm.cs = +v; bm.keys = +v; }
      if (k === 'od') bm.od = +v;
      if (k === 'hp') bm.hp = +v;
      if (k === 'ar') bm.ar = +v;
    } else if (section === 'events') {
      const parts = s.split(',');
      if (parts[0] === '0' && parts[2]) bm.bgFilename = parts[2].replace(/"/g, '').trim();
    } else if (section === 'timingpoints') {
      const p = s.split(',');
      const time = +p[0], beatLen = +p[1];
      const isRed = p.length < 7 || +p[6] === 1;
      if (isRed && beatLen > 0) bm.timings.push({ time, bpm: 60000 / beatLen, isRed: true });
    } else if (section === 'hitobjects') {
      const p = s.split(',');
      const x = +p[0], time = +p[2], type = +p[3];
      const col = Math.min(bm.keys - 1, Math.floor(x * bm.keys / 512));
      const isHold = (type & 128) !== 0;
      if (isHold) {
        const endPart = (p[5] || '0:0').split(':');
        const endTime = +endPart[0];
        bm.hitObjects.push({ time, endTime, column: col, isHold: true });
        bm.duration = Math.max(bm.duration, endTime);
      } else {
        bm.hitObjects.push({ time, endTime: time, column: col, isHold: false });
        bm.duration = Math.max(bm.duration, time);
      }
    }
  }
  bm.hitObjects.sort((a, b) => a.time - b.time);
  return bm;
}

function splitKV(s) {
  const i = s.indexOf(':');
  return i < 0 ? [s, ''] : [s.slice(0, i).trim().toLowerCase(), s.slice(i + 1).trim()];
}

// .osr replay parser
export function parseOsr(buffer) {
  const dv = new DataView(buffer);
  const u8 = new Uint8Array(buffer);
  let off = 0;
  const readU8 = () => u8[off++];
  const readI16 = () => { const v = dv.getInt16(off, true); off += 2; return v; };
  const readU16 = () => { const v = dv.getUint16(off, true); off += 2; return v; };
  const readI32 = () => { const v = dv.getInt32(off, true); off += 4; return v; };
  const readU32 = () => { const v = dv.getUint32(off, true); off += 4; return v; };
  const readI64 = () => { const v = dv.getBigInt64(off, true); off += 8; return v; };
  const readString = () => {
    const marker = u8[off++];
    if (marker === 0) return null;
    if (marker === 0x0b) {
      let n = 0, shift = 0;
      for (;;) {
        const b = u8[off++];
        n |= (b & 0x7f) << shift;
        if (!(b & 0x80)) break;
        shift += 7;
      }
      const s = new TextDecoder().decode(u8.subarray(off, off + n));
      off += n;
      return s;
    }
    return null;
  };
  const readBytes = () => {
    const n = readI32();
    if (n <= 0) return null;
    const d = u8.subarray(off, off + n);
    off += n;
    return d;
  };

  const ruleset = readU8();
  const version = readI32();
  const beatmapMd5 = readString();
  const username = readString();
  readString(); // replay md5
  off += 2 * 6; // counts
  off += 4 + 2 + 1 + 4; // score, combo, perfect, mods
  readString(); // life
  off += 8; // timestamp
  const replayBlob = readBytes();

  if (ruleset !== 3) throw new Error('not mania replay');

  // decompress LZMA replay data — may fail, fall back to empty
  let replayText = '';
  if (replayBlob && replayBlob.length > 13) {
    try {
      replayText = lzmaDecodeSync(replayBlob);
    } catch (e) {
      console.warn('LZMA decode failed (replay lighting disabled):', e);
    }
  }

  // parse frames: "w|x|y|z,..."
  const presses = [];
  const releases = [];
  const frames = replayText ? replayText.split(',') : [];
  let t = 0, prevMask = 0;
  for (const fr of frames) {
    const parts = fr.split('|');
    if (parts.length < 2) continue;
    const w = +parts[0], x = +parts[1], y = parts.length > 2 ? +parts[2] : 0;
    if (w === -12345) continue;
    // The delta counts BEFORE the marker frames are dropped — stable opens a replay with
    // two `(256, -500)` frames ("at time 0 and SkipBoundary - 1") and osu! accumulates
    // every delta first, then removes them (LegacyScoreDecoder.readLegacyReplay). This is
    // normally -1 ms, but one real replay carried 5630 ms here. See mania_render/osr.py.
    t += w;
    if (x === 256 && y === -500) continue;
    const mask = x & 0xfffff;
    for (let bit = 0; bit < 20; bit++) {
      const prev = (prevMask >> bit) & 1, cur = (mask >> bit) & 1;
      if (!prev && cur) presses.push({ time: t, key: bit });
      else if (prev && !cur) releases.push({ time: t, key: bit });
    }
    prevMask = mask;
  }
  presses.sort((a, b) => a.time - b.time);
  releases.sort((a, b) => a.time - b.time);
  return { beatmapMd5, username, presses, releases };
}

// LZMA decoder placeholder — real impl can be added later
function lzmaDecodeSync(data) {
  throw new Error('LZMA not yet implemented — use FC sim');
}

// ─────────────────────────────────────────────────────────────────────────────
// skin.ini parser — mirrors osu.Game/Skinning/LegacyManiaSkinDecoder.cs
//
// Coordinate spaces
//   skin.ini values are in osu!stable's 480-height space.
//   lazer converts them to its 768-height space with POSITION_SCALE_FACTOR = 1.6.
//   This renderer keeps the RAW 480-space numbers and multiplies by VIEW_H/480
//   when building geometry (480-space * 2.25 == 768-space * 1.40625).
//
// Reference: ppy/osu osu.Game/Skinning/LegacyManiaSkinDecoder.cs
// Spec:      https://osu.ppy.sh/wiki/en/Skinning/osu%21mania
// ─────────────────────────────────────────────────────────────────────────────

export const POSITION_SCALE_FACTOR = 1.6;
// LegacyManiaSkinConfiguration.DEFAULT_COLUMN_SIZE = 30 * 1.6 (768-space) → 30 here.
const DEFAULT_COLUMN_SIZE = 30;
// DEFAULT_HIT_POSITION = (480 - 402) * 1.6 → stored as the 480-space distance from the bottom.
const DEFAULT_HIT_POSITION_FROM_BOTTOM = 480 - 402;
const DEFAULT_LIGHT_POSITION_FROM_BOTTOM = 480 - 413;
const DEFAULT_COMBO_POSITION = 111;
const DEFAULT_SCORE_POSITION = 300;

export const DEFAULT_HIT_SPRITES = {
  hit300g: 'mania-hit300g',
  hit300: 'mania-hit300',
  hit200: 'mania-hit200',
  hit100: 'mania-hit100',
  hit50: 'mania-hit50',
  hit0: 'mania-hit0',
};

/** LegacyDecoder.StripComments — everything from `//` to end of line is dropped.
 *  Skins do put prose after a value (e.g. `ColumnWidth: 85,85,85,85 // 65 |越大越瘦？`). */
function stripComments(line) {
  const i = line.indexOf('//');
  return i >= 0 ? line.slice(0, i) : line;
}

/** LegacyManiaSkinDecoder.parseArrayValue — an unparseable entry reads as ZERO
 *  (stable parity, ppy/osu#26464). A NaN here would poison the whole geometry. */
function readArrayEntry(text, applyScale) {
  let f = parseFloat(text);
  if (!Number.isFinite(f)) f = 0;
  return applyScale ? f * POSITION_SCALE_FACTOR : f;
}

/**
 * Applies `value` onto a defaults-filled array, overriding only the indices present.
 * `applyScale` mirrors lazer's `parseArrayValue` (which multiplies by 1.6). We keep
 * every stored number in stable's own 480-space and let buildGeometry apply
 * VIEW_H/480, so the scaling lazer does is deliberately NOT applied here.
 */
function applyArray(target, value) {
  const parts = value.split(',');
  const out = target.slice();
  for (let i = 0; i < parts.length && i < out.length; i++)
    out[i] = readArrayEntry(parts[i], false);
  return out;
}

function num(value, fallback) {
  const f = parseFloat(value);
  return Number.isFinite(f) ? f : fallback;
}

/**
 * `[Colours]` entry → [r, g, b, a] with 0-255 components.
 * `R,G,B` (alpha defaults to 255) or `R,G,B,A`; unparseable components read as 0, which is
 * what stable does for malformed colour entries.
 */
function parseColour(value) {
  const parts = String(value).split(',').map(s => s.trim());
  const out = [0, 0, 0, 255];
  for (let i = 0; i < parts.length && i < 4; i++) {
    const v = parseInt(parts[i], 10);
    out[i] = Number.isFinite(v) ? Math.max(0, Math.min(255, v)) : 0;
  }
  return out;
}

function newManiaBlock(keys) {
  return {
    keys,
    // distance from the BOTTOM of the playfield, 480-space
    hitPosition: DEFAULT_HIT_POSITION_FROM_BOTTOM,
    lightPosition: DEFAULT_LIGHT_POSITION_FROM_BOTTOM,
    comboPosition: DEFAULT_COMBO_POSITION,
    scorePosition: DEFAULT_SCORE_POSITION,
    columnStart: 136,
    columnRight: 19,
    stageSeparation: 40,
    barLineHeight: 1.2,
    // array lengths mirror LegacyManiaSkinConfiguration's constructor
    columnWidth: Array(keys).fill(DEFAULT_COLUMN_SIZE),
    // LegacyManiaSkinConfiguration ctor: `ColumnLineWidth.AsSpan().Fill(2)` — a raw
    // 768-space value (the decoder passes applyScaleFactor: false for this key).
    columnLineWidth: Array(keys + 1).fill(2),
    columnSpacing: Array(Math.max(0, keys - 1)).fill(0),
    lightingNWidth: Array(keys).fill(0),
    lightingLWidth: Array(keys).fill(0),
    // 0 means "not configured" → sprite height follows DrawWidth (LegacyNotePiece)
    widthForNoteHeight: 0,
    lightFps: 60,
    upsideDown: false,
    keysUnderNotes: false,
    judgementLine: true,
    noteBodyStyle: null,
    lightingN: 'lightingN',
    lightingL: 'lightingL',
    stageHint: null,
    stageLight: null,
    warningArrow: null,
    leftStageImage: null,
    rightStageImage: null,
    bottomStageImage: null,
    /** `[Colours] ColourColumnLine` as [r,g,b,a] 0-255, or null → default white. */
    colourColumnLine: null,
    /** Every `Colour*` key of this block's `[Mania]` section, lowercased → [r,g,b,a]. */
    colours: {},
    noteImages: {}, noteImagesH: {}, noteImagesL: {}, noteImagesT: {},
    keyImages: {}, keyImagesD: {},
    hitSprites: { ...DEFAULT_HIT_SPRITES },
    /** NoteFlipWhenUpsideDownT / H / KeyFlipWhenUpsideDown* → raw values */
    flips: {},
  };
}

function applyManiaLine(block, key, value) {
  const k = key.toLowerCase();
  switch (k) {
    case 'columnwidth': block.columnWidth = applyArray(block.columnWidth, value); return;
    case 'columnlinewidth': block.columnLineWidth = applyArray(block.columnLineWidth, value); return;
    case 'columnspacing': block.columnSpacing = applyArray(block.columnSpacing, value); return;
    case 'columnstart': block.columnStart = num(value, block.columnStart); return;
    case 'columnright': block.columnRight = num(value, block.columnRight); return;
    case 'stageseparation': block.stageSeparation = num(value, block.stageSeparation); return;
    case 'barlineheight': block.barLineHeight = num(value, block.barLineHeight); return;
    // (480 - clamp(v,240,480)) * 1.6 in lazer → here the 480-space distance from the bottom
    case 'hitposition': block.hitPosition = 480 - Math.min(480, Math.max(240, num(value, 402))); return;
    case 'lightposition': block.lightPosition = 480 - num(value, 413); return;
    case 'comboposition': block.comboPosition = num(value, DEFAULT_COMBO_POSITION); return;
    case 'scoreposition': block.scorePosition = num(value, DEFAULT_SCORE_POSITION); return;
    case 'judgementline': block.judgementLine = value === '1'; return;
    case 'keysundernotes': block.keysUnderNotes = value === '1'; return;
    case 'upsidedown': block.upsideDown = value === '1'; return;
    case 'notebodystyle': block.noteBodyStyle = value; return;
    case 'widthfornoteheightscale': block.widthForNoteHeight = num(value, 0); return;
    case 'lightingnwidth': block.lightingNWidth = applyArray(block.lightingNWidth, value); return;
    case 'lightinglwidth': block.lightingLWidth = applyArray(block.lightingLWidth, value); return;
    case 'lightframepersecond': {
      const v = parseInt(value, 10);
      block.lightFps = v > 0 ? v : 24;
      return;
    }
    default: break;
  }

  // LegacyManiaSkinDecoder: `case string when pair.Key.StartsWith("Colour", …)` →
  // `HandleColours(currentConfig, …)`. Every `Colour*` key inside `[Mania]` is a custom
  // colour OF THAT MANIA BLOCK (not of the global `[Colours]` section), which is where
  // `ColourColumnLine`, `Colour{n}` (1-based column backgrounds) and `ColourLight{n}` live.
  if (k.startsWith('colour')) {
    block.colours[k] = parseColour(value);
    if (k === 'colourcolumnline') block.colourColumnLine = block.colours[k];
    return;
  }

  if (k.startsWith('noteimage')) {
    const rest = key.slice('NoteImage'.length);
    let i = 0;
    while (i < rest.length && rest[i] >= '0' && rest[i] <= '9') i++;
    if (!i) return;
    const idx = +rest.slice(0, i);
    const suffix = rest.slice(i).toUpperCase();
    const map = { '': 'noteImages', H: 'noteImagesH', L: 'noteImagesL', T: 'noteImagesT' };
    if (map[suffix]) block[map[suffix]][idx] = value;
    return;
  }
  if (k.startsWith('keyimage')) {
    const rest = key.slice('KeyImage'.length);
    let i = 0;
    while (i < rest.length && rest[i] >= '0' && rest[i] <= '9') i++;
    if (!i) return;
    const idx = +rest.slice(0, i);
    const suffix = rest.slice(i).toUpperCase();
    if (suffix === 'D') block.keyImagesD[idx] = value;
    else if (!suffix) block.keyImages[idx] = value;
    return;
  }
  if (k.startsWith('warningarrow')) { block.warningArrow = value; return; }
  if (k === 'stagehint') { block.stageHint = value; return; }
  if (k === 'stagelight') { block.stageLight = value; return; }
  if (k === 'stageleft') { block.leftStageImage = value; return; }
  if (k === 'stageright') { block.rightStageImage = value; return; }
  if (k === 'stagebottom') { block.bottomStageImage = value; return; }
  if (k.startsWith('lightingn')) { block.lightingN = value || 'lightingN'; return; }
  if (k.startsWith('lightingl')) { block.lightingL = value || 'lightingL'; return; }
  if (k.startsWith('keyflipwhenupsidedown') || k.startsWith('noteflipwhenupsidedown')) {
    block.flips[key] = value;
    return;
  }
  if (k.startsWith('hit')) {
    // Hit300g / Hit300 / Hit200 / Hit100 / Hit50 / Hit0
    const name = k.slice(3);
    const hitKey = name === '0' ? 'hit0' : 'hit' + name;
    if (hitKey in block.hitSprites) block.hitSprites[hitKey] = value || DEFAULT_HIT_SPRITES[hitKey];
  }
}

/**
 * Parses skin.ini. Returns `{ blocks, version, forKeys(keys), declaredKeys }`.
 *
 * `blocks` is keyed by the `Keys:` value: a skin may declare several `[Mania]`
 * sections (owc ships a 4K and a 7K one). A duplicate `Keys:` is discarded
 * entirely — stable/lazer keep the FIRST block for that key count.
 */
export function parseSkinIni(text) {
  const blocks = new Map();
  let version = 0;
  let section = '';
  let current = null;
  let pending = [];

  const flush = (block) => {
    for (const [k, v] of pending) applyManiaLine(block, k, v);
    pending = [];
  };

  for (const rawLine of String(text ?? '').split(/\r?\n/)) {
    const line = stripComments(rawLine).trim();
    if (!line) continue;
    if (line.startsWith('[')) {
      section = line.slice(1, -1).trim().toLowerCase();
      current = null;
      pending = [];
      continue;
    }
    const ci = line.indexOf(':');
    if (ci < 0) continue;
    const key = line.slice(0, ci).trim();
    const value = line.slice(ci + 1).trim();

    if (section === 'general') {
      if (key.toLowerCase() === 'version') version = num(value, 0);
      continue;
    }
    if (section !== 'mania') continue;

    if (key.toLowerCase() === 'keys') {
      const keys = parseInt(value, 10);
      if (!Number.isFinite(keys) || keys <= 0) { current = null; pending = []; continue; }
      current = newManiaBlock(keys);
      // duplicate configuration — parsed but discarded (lazer: "silently ignore")
      if (!blocks.has(keys)) blocks.set(keys, current);
      flush(current);
      continue;
    }

    if (current) applyManiaLine(current, key, value);
    else pending.push([key, value]);
  }

  const ordered = [...blocks.values()];

  /** Block for a beatmap's column count, falling back when the skin has no exact block. */
  const forKeys = (keys) => {
    if (blocks.has(keys)) return blocks.get(keys);
    if (!ordered.length) return newManiaBlock(keys);
    // nearest declared key count (CONTEXT.md Q32 fallback)
    let best = ordered[0];
    for (const b of ordered)
      if (Math.abs(b.keys - keys) < Math.abs(best.keys - keys)) best = b;
    return { ...best, keys };
  };

  return { blocks, version, forKeys, declaredKeys: ordered.map(b => b.keys) };
}
