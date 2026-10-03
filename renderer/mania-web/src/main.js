import { readZip } from './zip.js';
import { parseOsu, parseOsr, parseSkinIni } from './parsers.js';
import { Renderer } from './renderer.js';

const $ = (id) => document.getElementById(id);
const canvas = $('game');
const hudCanvas = $('hud');
const hudCtx = hudCanvas.getContext('2d');
const info = $('info');
const VIEW_W = 1920, VIEW_H = 1080;
// Hit-burst width as a fraction of its lane. 1 = lane width; scaled, aspect preserved.
const HIT_BURST_LANE_FRACTION = 0.75;

let renderer = null;
let beatmap = null;
let replay = null;
let skin = null;
let ini = null;        // parseSkinIni() result: { blocks, version, forKeys() }
let block = null;      // the [Mania] block matching the beatmap's key count
let geometry = null;
let bgImage = null;
let bgDim = 0.3;
let bgBlur = 0;
let audio = $('audio');
let playing = false;
let animFrame = 0;
let scrollSpeed = 30;
let seekDragging = false;
let skinList = [];
// hit matching for combo / errors
let hitMatch = null;
// Last hit-burst quad actually drawn, for the __mania debug hook (null between bursts).
let lastBurstRect = null;

// ── playback clock ───────────────────────────────────────────────────────────
// Playback is driven by a wall clock, not by <audio>.timeupdate, so 播放 still works
// when no audio track could be fetched (missing sid / mirror down) — the notes and
// HUD animate regardless. When a real track IS loaded the audio element stays the
// source of truth so the picture and the music cannot drift apart.
let hasAudio = false;
let audioNote = '';
let playStartWall = 0;     // performance.now() when playback (re)started
let playStartPos = 0;      // track position (ms) at that moment

function currentTimeMs() {
  if (!playing) return pausedAtMs;
  const rate = +($('playSpeed')?.value || 1);
  const elapsed = (performance.now() - playStartWall) * rate;
  return playStartPos + elapsed;
}
let pausedAtMs = 0;

function seekTo(ms) {
  pausedAtMs = Math.max(0, ms);
  if (hasAudio) audio.currentTime = pausedAtMs / 1000;
}

// ── geometry ──
// Coordinates: skin.ini VALUES are in osu!stable's 480-height space; scale maps them
// onto the 1080px viewport (480 * 2.25 == 768 * 1.40625, lazer's 768-space).
// Sprite PIXEL dimensions are different: lazer draws a legacy texture at its native
// pixel size inside a 768-unit-tall playfield, so they map by VIEW_H/768 — using the
// 480-space factor on them makes every sprite 1.6x too large.
const TEX_SCALE = VIEW_H / 768;
// Inter-column margins. `Stage.COLUMN_SPACING = 1` (768-space) is only the fallback used
// when there is no legacy `[Mania]` config at all — `skin.GetConfig(LeftColumnSpacing)?.Value
// ?? Stage.COLUMN_SPACING` never falls through for a decoded skin.ini, because the lookup
// returns a `Bindable<float>`, and a bindable holding 0 is not null. `ColumnSpacing`
// defaults to all zeros, so a skin that does not set it gets **contiguous columns**.
const DEFAULT_COLUMN_SPACING_768 = 0;
// Lane panel — LegacyStageBackground.ColumnBackground:
//
//     Color4 backgroundColour = skin.GetManiaSkinConfig<Color4>(
//         LegacyManiaSkinConfigurationLookups.ColumnBackgroundColour, columnIndex)?.Value
//         ?? Color4.Black;
//     LegacyColourCompatibility.ApplyWithDoubledAlpha(
//         new Box { RelativeSizeAxes = Axes.Both }, backgroundColour);
//
// `ColumnBackgroundColour` is `getCustomColour(existing, $"Colour{columnIndex + 1}")` — the
// mania block's own `Colour{n}` key, **1-based**. There is **no lane background image**:
// `LegacyManiaSkinConfigurationLookups` has no such entry, and the mania wiki page lists no
// `mania-column*` sprite. The lane is a plain solid `Box`, opaque black by default; boj
// overrides it with `Colour1..n: 0,0,0,230` (90 % opaque). `ApplyWithDoubledAlpha` puts the
// colour's alpha on the drawable's Alpha and forces a **zero** alpha to opaque.
//
// `COLUMN_BACKGROUND_OVERRIDE` is a knob, not a source value: `null` follows the skin;
// `[r, g, b, opacity]` (each 0-1) forces one look for every skin.
const COLUMN_BACKGROUND_OVERRIDE = null;

/** Lane fill for column `i` as `[r, g, b, opacity]` in 0-1, following `Colour{i+1}`. */
function columnBackground(i) {
  if (COLUMN_BACKGROUND_OVERRIDE) return COLUMN_BACKGROUND_OVERRIDE;
  const c = block && block.colours && block.colours['colour' + (i + 1)];
  if (!c) return [0, 0, 0, 1];                       // Color4.Black, fully opaque
  return [c[0] / 255, c[1] / 255, c[2] / 255, (c[3] === 0 ? 255 : c[3]) / 255];
}
// LegacyStageBackground.ColumnBackground draws its divider lines at
// `Scale = new Vector2(0.740f, 1)` — the width is scaled horizontally by this much.
const COLUMN_LINE_SCALE_X = 0.740;
// LegacyColumnBackground.OnReleased: the stage light fades and squashes to nothing over
// 250 ms (linear); OnPressed brings it back to full alpha / full height instantly.
const STAGE_LIGHT_RELEASE_MS = 250;

function buildGeometry(b, keys) {
  const scale = VIEW_H / 480;
  const rawW = (b.columnWidth && b.columnWidth.length >= keys)
    ? b.columnWidth.slice(0, keys) : Array(keys).fill(30);
  // A single non-finite width would poison every column position — Cho' ships a
  // commented-out `ColumnWidth: 85,85,85,85 // …` line that used to yield NaN here.
  const w = rawW.map(v => (Number.isFinite(v) && v > 0) ? v : 30);

  // LegacySkin: `LeftColumnSpacing(i)` is `ColumnSpacing[i-1] / 2` and `RightColumnSpacing(i)`
  // is `ColumnSpacing[i] / 2`, with an empty bindable (margins 0) at the stage's outer edges.
  // One skin.ini entry therefore equals the FULL gap between two lanes, and the array has
  // `keys - 1` entries. `ColumnSpacing` is a 480-space value (lazer decodes it with
  // POSITION_SCALE_FACTOR), hence `* scale`.
  const gapFull = [];
  for (let i = 0; i < keys - 1; i++) {
    const s = b.columnSpacing && b.columnSpacing[i];
    gapFull.push(Number.isFinite(s) && s > 0
      ? s * scale
      : DEFAULT_COLUMN_SPACING_768 * (VIEW_H / 768));
  }
  const leftMargin = (i) => (i === 0 ? 0 : gapFull[i - 1] / 2);
  const rightMargin = (i) => (i === keys - 1 ? 0 : gapFull[i] / 2);

  const colW = w.map(v => v * scale);
  const totalW = colW.reduce((a, c) => a + c, 0) + gapFull.reduce((a, c) => a + c, 0);
  const startX = (VIEW_W - totalW) / 2;
  const colX = [];
  let x = startX;
  for (let i = 0; i < keys; i++) {
    x += leftMargin(i);
    colX.push(x);
    x += colW[i] + rightMargin(i);
  }
  // HitPosition is the 480-space distance from the BOTTOM edge up to the judgement line,
  // so the scroll length is (480 - HitPosition) — lazer's `lengthToHitPosition`.
  const hitFromBottom = Number.isFinite(b.hitPosition) ? b.hitPosition : 78;
  const lengthToHit = Math.max(1, 480 - hitFromBottom);
  const hitY = lengthToHit * scale;

  // DrawableManiaRuleset.updateTimeRange:
  //   scale     = (768 - hitPosition) / (768 - DEFAULT_HIT_POSITION)
  //   TimeRange = (11485 / ScrollSpeed) * scale
  // DEFAULT_HIT_POSITION = (480 - 402) * 1.6, i.e. a 480-space length of 402.
  const DEFAULT_LENGTH_TO_HIT = 402;
  const timeRange = (11485 / scrollSpeed) * (lengthToHit / DEFAULT_LENGTH_TO_HIT);

  return { keys, colX, colW, rawW: w, hitY, stageLeft: startX, stageRight: startX + totalW, totalW, timeRange, scale, texScale: TEX_SCALE };
}

// Re-resolve the [Mania] block and geometry for the current skin + beatmap.
// A skin may declare several `[Mania]` sections (owc ships 4K and 7K); the block
// must match the beatmap's column count, never the last block in the file.
function applyIni() {
  if (!ini || !beatmap) return;
  block = ini.forKeys(beatmap.keys);
  geometry = buildGeometry(block, beatmap.keys);
}

// ── where the API lives ─────────────────────────────────────────────────────
// The same page is served in two places: at the render node's own root ("/"),
// and under a subpath when the blog proxies it (e.g. "/renderer/", so visitors
// can watch a chart without touching the owner's machine).  Every API path is
// therefore built from the document's own base rather than from "/" — hardcoding
// "/api/..." made the page work in exactly one of those two places, and under
// the proxy every fetch would have hit the blog's own API instead.
const API = (() => {
  const p = new URL('./api/', document.baseURI).pathname;
  return p.endsWith('/') ? p.slice(0, -1) : p;
})();

// ── mania judgement, traced to osu!lazer ────────────────────────────────────
// A line-by-line mirror of mania_render/judge.py, which cites the source files.
// The rules that matter, and that this file used to get wrong:
//   * ManiaScoreProcessor.GetBaseScoreForResult returns 305 for a PERFECT (the
//     base ScoreProcessor returns 300 for both Perfect and Great), and
//     ScoreProcessor.Accuracy = base / maximum where the maximum is
//     GetBaseScoreForResult(MaxResult) = 305 per judged object.  So a full-GREAT
//     play is 300/305 = 98.36%, which lazer asserts in TestSceneManiaModDoubleTime.
//   * A hold note is TWO judgements: HeadNote and TailNote are both Notes with
//     MaxResult Perfect.  The HoldNote itself is an IgnoreJudgement and its body
//     (HoldNoteBodyJudgement.MaxResult = IgnoreHit) cannot affect accuracy.
//   * DrawableNote auto-misses an object once (now - start) passes the MEH
//     window (CanBeHit compares against the lowest SUCCESSFUL result), so a
//     press later than that finds the note gone and is offered to the next one.
//   * OrderedHitPolicy note locks: an object cannot be hit once a LATER object
//     has started, and a successful hit force-misses earlier unjudged objects.
//   * HitObjectContainer.Compare puts earlier objects first for input.
const HIT_RESULTS = ['perfect', 'great', 'good', 'ok', 'meh', 'miss'];
const BASE_SCORE = { perfect: 305, great: 300, good: 200, ok: 100, meh: 50, miss: 0 };
const MAX_SCORE = BASE_SCORE.perfect;            // 305
const RELEASE_WINDOW_LENIENCE = 1.5;             // TailNote.RELEASE_WINDOW_LENIENCE
// ManiaHitWindows DifficultyRanges: [OD0, OD5, OD10] — the numbers DECREASE.
const WINDOW_RANGES = {
  perfect: [22.4, 19.4, 13.9], great: [64, 49, 34], good: [97, 82, 67],
  ok: [127, 112, 97], meh: [151, 136, 121], miss: [188, 173, 158],
};

// IBeatmapDifficultyInfo.DifficultyRange(difficulty, min, mid, max)
function difficultyRange(od, lo, mid, hi) {
  if (od > 5) return mid + (hi - mid) * (od - 5) / 5;
  if (od < 5) return mid + (mid - lo) * (od - 5) / 5;
  return mid;
}

// ManiaHitWindows.updateWindows: Math.Floor(range * totalMultiplier) + 0.5
function getHitWindows(od) {
  const w = {};
  for (const name of HIT_RESULTS) w[name] = Math.floor(difficultyRange(od, ...WINDOW_RANGES[name])) + 0.5;
  return w;
}

// HitWindows.ResultFor — null when the offset is outside EVERY window (including
// miss), which means the press consumes nothing at all.
function resultForOffset(offset, w) {
  const a = Math.abs(offset);
  for (const name of HIT_RESULTS) if (a <= w[name]) return name;
  return null;
}

// ── hit matching (combo / error bar / judge) ──
function buildHitMatch() {
  if (!beatmap || !replay) return;
  const od = (beatmap.od !== undefined && beatmap.od !== null) ? beatmap.od : 5;
  const w = getHitWindows(od);
  const objs = beatmap.hitObjects.map(h => ({ time: h.time, endTime: h.isHold ? h.endTime : h.time, col: h.column, isHold: h.isHold, matched: false, error: 0 }));
  objs.sort((a, b) => a.time - b.time);
  const match = { objs, presses: [], comboTrail: [], judgements: [], windows: w };
  hitMatch = match;

  // per column, in StartTime order (HitObjectContainer.AliveObjects)
  const byCol = new Map();
  for (const o of objs) {
    if (!byCol.has(o.col)) byCol.set(o.col, []);
    byCol.get(o.col).push(o);
  }
  const pressByCol = new Map();
  for (const p of replay.presses) {
    const col = p.key % (geometry?.keys || 4);
    if (!pressByCol.has(col)) pressByCol.set(col, []);
    pressByCol.get(col).push(p);
  }
  const relByCol = new Map();
  for (const r of (replay.releases || [])) {
    const col = r.key % (geometry?.keys || 4);
    if (!relByCol.has(col)) relByCol.set(col, []);
    relByCol.get(col).push(r.time);
  }
  for (const arr of pressByCol.values()) arr.sort((a, b) => a.time - b.time);
  for (const arr of relByCol.values()) arr.sort((a, b) => a - b);

  const J = (time, objTime, kind, result, offset, byPress) => {
    const rec = { time, objTime, kind, result, offset, byPress: !!byPress };
    match.judgements.push(rec);
    return rec;
  };

  for (const [col, list] of byCol) {
    const judged = new Map();       // index -> result
    const headPress = new Map();    // index -> press time
    const headJ = new Map();        // index -> the head judgement record
    for (const press of (pressByCol.get(col) || [])) {
      const t = press.time;
      for (let i = 0; i < list.length; i++) {
        if (judged.has(i)) continue;
        const o = list[i];
        if (t > o.time + w.meh) {           // already auto-missed before this press
          judged.set(i, 'miss');
          J(Math.round(o.time + w.meh), o.time, 'head', 'miss', 0, false);
          continue;
        }
        // Note lock: "next" is the next object still in AliveObjects, and a
        // judged object is killed — so it leaves that list.  Mirror of judge.py.
        let nxt = null;
        for (let j = i + 1; j < list.length; j++) {
          if (!judged.has(j)) { nxt = list[j]; break; }
        }
        if (nxt && t >= nxt.time) continue;  // note lock
        const off = t - o.time;
        const r = resultForOffset(off, w);
        if (!r) continue;                    // wasted press
        judged.set(i, r);
        headPress.set(i, t);
        o.matched = true;
        o.error = off;
        // Drives lightingL vs lightingN in pressLog(), which reads the ORIGINAL
        // press objects — the old code set this on a throwaway copy, so the hold
        // lighting was never once drawn.
        press.hold = o.isHold;
        headJ.set(i, J(t, o.time, 'head', r, off, true));
        if (r !== 'miss') {                  // OrderedHitPolicy.HandleHit
          for (let j = 0; j < i; j++) {
            if (judged.has(j)) continue;
            judged.set(j, 'miss');
            J(Math.round(list[j].time + w.meh), list[j].time, 'head', 'miss', 0, false);
          }
        }
        break;
      }
    }
    for (let i = 0; i < list.length; i++) {
      if (judged.has(i)) continue;
      judged.set(i, 'miss');
      J(Math.round(list[i].time + w.meh), list[i].time, 'head', 'miss', 0, false);
    }
    // Tails: resolved by the release, with the 1.5x lenience and the Meh cap.
    for (let i = 0; i < list.length; i++) {
      const o = list[i];
      if (!o.isHold) continue;
      const head = judged.get(i) || 'miss';
      let rel = null;
      if (headPress.has(i)) {
        for (const rt of (relByCol.get(col) || [])) {
          if (rt >= headPress.get(i)) { rel = rt; break; }
        }
      }
      let tailResult, off, when;
      if (rel === null) {
        tailResult = 'miss';
        off = 0;
        when = Math.round(o.endTime + RELEASE_WINDOW_LENIENCE * w.meh);
      } else {
        off = (rel - o.endTime) / RELEASE_WINDOW_LENIENCE;
        tailResult = resultForOffset(off, w) || 'miss';
        when = rel;
      }
      if (head === 'miss' && HIT_RESULTS.indexOf(tailResult) < HIT_RESULTS.indexOf('meh')) {
        tailResult = 'meh';                  // DrawableHoldNoteTail.GetCappedResult
      }
      if (replay.classic) {
        // osu!stable counts a hold ONE time, and what it judges is the RELEASE:
        // holding is the whole test.  Fold the tail's result back onto the head's
        // record instead of emitting a second judgement.  Measured over 31 cached
        // stable replays, the header total is N+M and never N+2M — see
        // mania_render/judge.py, judgements_per_hold().
        const hj = headJ.get(i);
        if (hj) {
          hj.result = tailResult;
          hj.offset = off;
          hj.time = when;
        }
        continue;
      }
      J(when, o.endTime, 'tail', tailResult, off, false);
    }
  }

  match.judgements.sort((a, b) => a.time - b.time);
  reconcileJudgements(match.judgements, replay.counts);

  // Combo follows the judgements in the order they are applied.
  let combo = 0;
  for (const j of match.judgements) {
    if (j.result === 'miss') combo = 0; else combo++;
    match.comboTrail.push({ time: j.time, combo });
  }
}

// ── pinning the counter to the score's own counts ───────────────────────────
// Mirror of judge.reconcile().  The .osr header carries the judgement counts
// osu! itself recorded for the play, and they are the authoritative answer to
// "what accuracy did this score get": lazer reads exactly these when it decodes
// a legacy score rather than re-deriving them, and the osu! website's accuracy
// is a pure function of them.
//
// This engine can still disagree with them by a few judgements, because the
// client's input matching is not fully reproducible from a replay — osu!stable's
// source is not public, and lazer's OrderedHitPolicy is not what stable does, so
// a single stray press cascades differently (one real 2026-09-26 play had a
// ghost tap 89ms before a dense stream and drifted ten judgements).
//
// So the counts decide, and this engine's own ordering decides WHICH judgement
// moves: results are re-dealt worst-first over judgements ordered worst-first,
// so only the ones nearest the boundary change.  Every judgement keeps its time,
// so the counter's curve is unchanged; only its final value is pinned.
function reconcileJudgements(list, counts) {
  if (!counts) return 0;
  let total = 0;
  for (const k of HIT_RESULTS) total += counts[k] || 0;
  if (!total || total !== list.length) return 0;   // model mismatch: leave alone

  const have = {};
  for (const k of HIT_RESULTS) have[k] = 0;
  for (const j of list) if (j.result in have) have[j.result]++;
  if (HIT_RESULTS.every(k => have[k] === (counts[k] || 0))) return 0;

  const desired = [];
  for (let i = HIT_RESULTS.length - 1; i >= 0; i--) {           // worst first
    for (let n = 0; n < (counts[HIT_RESULTS[i]] || 0); n++) desired.push(HIT_RESULTS[i]);
  }
  const rank = j => (j.byPress ? HIT_RESULTS.indexOf(j.result) : HIT_RESULTS.length);
  // Worst first: highest rank, then largest |offset| within a rank.  Mirrors
  // judge._quality(), whose tuple sorted ascending gives the same order.
  const ordered = list.slice().sort((a, b) =>
    (rank(b) - rank(a)) || (Math.abs(b.offset || 0) - Math.abs(a.offset || 0)));

  let changed = 0;
  for (let i = 0; i < ordered.length; i++) {
    const want = desired[i];
    if (ordered[i].result !== want) { ordered[i].result = want; changed++; }
  }
  return changed;
}

// ── key state ────────────────────────────────────────────────────────────────
// Replay drives real key presses; autoplay (FC sim) synthesises them from the
// chart. Returns the columns held down at `nowMs` (wiki: mania-key{n}D / stage light).
function pressedColumns(nowMs) {
  const held = new Set();
  if (!geometry) return held;
  if (replay && replay.presses.length) {
    const last = new Map();   // column -> 'down' | 'up'
    for (const p of replay.presses) { if (p.time <= nowMs) last.set(p.key % geometry.keys, 'down'); else break; }
    for (const r of replay.releases) { if (r.time <= nowMs) last.set(r.key % geometry.keys, 'up'); else break; }
    for (const [col, st] of last) if (st === 'down') held.add(col);
    return held;
  }
  if (beatmap) {
    for (const h of beatmap.hitObjects) {
      if (!h.isHold) continue;
      if (h.time <= nowMs && nowMs <= h.endTime) held.add(h.column);
    }
  }
  return held;
}

/** Presses that are still within the 200ms lighting window.
 *  Hit lighting mirrors real key presses, so it is replay-only — autoplay stays
 *  without hit imagery (the agreed behaviour). `hold` picks lightingL over lightingN. */
function pressLog(nowMs) {
  if (!replay || !replay.presses.length || !geometry) return [];
  const out = [];
  for (const p of replay.presses) {
    const age = nowMs - p.time;
    if (age < 0) break;
    if (age > 200) continue;
    out.push({ key: p.key, time: p.time, hold: !!p.hold });
  }
  return out;
}

/**
 * Per-column stage-light state for LegacyColumnBackground:
 *   OnPressed  -> `light.FadeIn()` + `light.ScaleTo(Vector2.One)`   (both instant)
 *   OnReleased -> `light.FadeTo(0, 250)` + `light.ScaleTo((1, 0), 250)`, linear, and the
 *                 light is anchored BottomCentre, so it collapses DOWN onto its bottom edge.
 * Returns column -> { alpha, scaleY }. Columns that were never pressed are absent.
 */
function stageLightState(nowMs) {
  const out = new Map();
  if (!geometry) return out;
  if (!replay || !replay.releases.length) {
    // No release log (autoplay): fall back to "held now" with no release animation.
    for (const col of pressedColumns(nowMs)) out.set(col, { alpha: 1, scaleY: 1 });
    return out;
  }
  const lastDown = new Map(), lastUp = new Map();
  for (const p of replay.presses) { if (p.time <= nowMs) lastDown.set(p.key % geometry.keys, p.time); else break; }
  for (const r of replay.releases) { if (r.time <= nowMs) lastUp.set(r.key % geometry.keys, r.time); else break; }
  for (const [col, downAt] of lastDown) {
    const upAt = lastUp.get(col);
    if (upAt === undefined || upAt < downAt) { out.set(col, { alpha: 1, scaleY: 1 }); continue; }
    const k = (nowMs - upAt) / STAGE_LIGHT_RELEASE_MS;
    if (k < 1) out.set(col, { alpha: 1 - k, scaleY: 1 - k });
  }
  return out;
}

function getCombo(nowMs) {
  if (hitMatch) {
    let c = 0;
    for (const t of hitMatch.comboTrail) {
      if (t.time <= nowMs) c = t.combo; else break;
    }
    return c;
  }
  // FC sim (no replay): all notes hit, combo = count up to nowMs
  if (!beatmap) return 0;
  let c = 0;
  for (const h of beatmap.hitObjects) {
    if (h.time <= nowMs) {
      c++;
      if (h.isHold) c++;  // LN tail also counts
    } else break;
  }
  return c;
}

function getCPS(nowMs) {
  if (replay && replay.presses.length) {
    return replay.presses.filter(p => p.time > nowMs - 1000 && p.time <= nowMs).length;
  }
  // FC sim: count note heads in last 1s
  if (!beatmap) return 0;
  return beatmap.hitObjects.filter(h => h.time > nowMs - 1000 && h.time <= nowMs).length;
}

function getAccuracy(nowMs) {
  if (!hitMatch) return 100;                 // FC sim / autoplay: nothing missed
  const c = getJudgeCounts(nowMs);
  const total = c.max + c.g300 + c.g200 + c.g100 + c.g50 + c.miss;
  if (!total) return 100;
  // ScoreProcessor.Accuracy for mania: base / (305 * judgements).  A PERFECT is
  // worth 305, NOT 300 — with 300 an all-GREAT play reads 100% instead of lazer's
  // 98.36%, and every mixed play is off by a fraction of a percent.
  return 100 * (c.max * BASE_SCORE.perfect + c.g300 * BASE_SCORE.great
    + c.g200 * BASE_SCORE.good + c.g100 * BASE_SCORE.ok
    + c.g50 * BASE_SCORE.meh) / (MAX_SCORE * total);
}

/** osu!stable's mania accuracy, shown beside the lazer one.
 *  Perfect and Great both score 300 over a 300-per-judgement denominator, so a
 *  full-GREAT play reads 100% here and 98.36% in lazer. */
function getAccuracyStable(nowMs) {
  if (!hitMatch) return 100;
  const c = getJudgeCounts(nowMs);
  const total = c.max + c.g300 + c.g200 + c.g100 + c.g50 + c.miss;
  if (!total) return 100;
  return 100 * ((c.max + c.g300) * 300 + c.g200 * 200 + c.g100 * 100 + c.g50 * 50) / (300 * total);
}

function getJudgeCounts(nowMs) {
  const counts = { max: 0, g300: 0, g200: 0, g100: 0, g50: 0, miss: 0 };
  if (!hitMatch) return counts;
  // Straight from the judgements — head AND tail, with the windows the engine
  // actually used.  The old version re-derived the result from the offset with
  // hardcoded thresholds (16/37/70/100) that ignored OD entirely and treated
  // every offset past 100ms as a Meh, so a MISS beyond the meh window was
  // published as a 50.
  const key = { perfect: 'max', great: 'g300', good: 'g200', ok: 'g100', meh: 'g50', miss: 'miss' };
  for (const j of hitMatch.judgements) {
    if (j.time > nowMs) break;               // sorted by time
    counts[key[j.result]]++;
  }
  return counts;
}

function getBPM(nowMs) {
  if (!beatmap.timings || !beatmap.timings.length) return 0;
  let chosen = beatmap.timings[0];
  for (const t of beatmap.timings) { if (t.time <= nowMs) chosen = t; else break; }
  return chosen.bpm || 0;
}

// ── skin: root-level skin.ini wins; textures keyed by full path AND stem ──
async function loadSkinFromZip(zip) {
  // find skin.ini — prefer root-level
  const iniNames = zip.names().filter(n => {
    const low = n.toLowerCase().replace(/\\/g, '/');
    return low.endsWith('skin.ini');
  });
  iniNames.sort((a, b) => {
    const da = a.replace(/\\/g, '/').split('/').length;
    const db = b.replace(/\\/g, '/').split('/').length;
    return da - db;
  });
  const iniText = iniNames.length ? await zip.readText(iniNames[0]) : null;
  const skinIni = iniText ? parseSkinIni(iniText) : parseSkinIni('');
  const textures = new Map();
  for (const name of zip.names()) {
    const low = name.toLowerCase().replace(/\\/g, '/');
    if (!low.endsWith('.png') && !low.endsWith('.jpg') && !low.endsWith('.jpeg')) continue;
    if (low.includes('ranking') || low.includes('selection')) continue;
    try {
      const blob = await zip.readBlob(name, low.endsWith('.png') ? 'image/png' : 'image/jpeg');
      if (!blob) continue;
      const rawBmp = await createImageBitmap(blob);
      // `@2x` sprites are drawn at HALF their pixel size (osu sets ScaleAdjust = 2 for them).
      // Halving the bitmap once, right here, fixes every consumer at once instead of teaching
      // each draw site about it. Aspect ratios are unchanged, so notes/LN geometry is untouched.
      let bmp = rawBmp;
      if (/@2x$/.test(low.replace(/\.(png|jpg|jpeg)$/, ""))) {
        const hc = document.createElement("canvas");
        hc.width = Math.max(1, Math.round(rawBmp.width / 2));
        hc.height = Math.max(1, Math.round(rawBmp.height / 2));
        hc.getContext("2d").drawImage(rawBmp, 0, 0, hc.width, hc.height);
        bmp = hc;
      }
      const depth = low.split('/').length;
      // store by full relative path (lowercase, forward slashes)
      const fullPath = low.replace(/\.(png|jpg|jpeg)$/, '');
      const prevFull = textures.get(fullPath);
      if (!prevFull || depth < (prevFull._depth || 99)) {
        bmp._depth = depth;
        textures.set(fullPath, bmp);
      }
      // also store by stem (basename without ext) — root-level wins
      const stem = fullPath.split('/').pop();
      const prevStem = textures.get(stem);
      if (!prevStem || depth < (prevStem._depth || 99)) {
        bmp._depth = depth;
        textures.set(stem, bmp);
      }
    } catch (e) {}
  }
  return { ini: skinIni, textures };
}

// lookup: try full path first, then stem, then stem0/stem1
function getTex(name) {
  if (!skin || !name) return null;
  const raw = String(name).replace(/\\/g, '/').toLowerCase().replace(/\.(png|jpg|jpeg)$/, '');
  const stem = raw.split("/").pop();
  // osu strips `@2x` from the component name and tries it FIRST (LegacySkin.cs:561-579).
  const hi = skin.textures.get(raw + "@2x") || skin.textures.get(stem + "@2x");
  if (hi) return hi;
  if (skin.textures.has(raw)) return skin.textures.get(raw);
  if (skin.textures.has(stem)) return skin.textures.get(stem);
  return skin.textures.get(stem + '0') || skin.textures.get(stem + '1') || null;
}

// collect animated frames for hit sprites (wiki: mania-hit300g-{n}.png at 60fps)
const _hitFrameCache = new Map();
function getHitFrames(baseName) {
  if (_hitFrameCache.has(baseName)) return _hitFrameCache.get(baseName);
  const frames = [];
  // try frames: base-0, base-1, ... up to 64
  for (let i = 0; i < 64; i++) {
    const f = getTex(baseName + '-' + i);
    if (!f) break;
    frames.push(f);
  }
  // fallback: single frame (base name without suffix)
  if (!frames.length) {
    const single = getTex(baseName);
    if (single) frames.push(single);
  }
  _hitFrameCache.set(baseName, frames);
  return frames;
}

// flip image vertically (canvas helper)
const _flipCache = new Map();

/**
 * True when a sprite has no visible pixels at all (owc ships `mania-note{1,2}T.png`
 * as a 1x1 fully transparent placeholder).
 *
 * This is a LAYOUT question, not a fallback trigger: lazer's hold-note geometry is
 * expressed in `Head.Height` / `Tail.Height`, which are real extents of real sprites.
 * A sprite with no pixels has no extent, so it must contribute 0 to the layout —
 * otherwise a 1x1 placeholder reports a 90px height and drags the body over the tail.
 * The sprite is still the one the skin asked for (no substitution), it just measures 0.
 */
const _blankCache = new WeakMap();
function isBlankSprite(img) {
  if (!img) return true;
  const cached = _blankCache.get(img);
  if (cached !== undefined) return cached;
  let blank = false;
  try {
    const c = document.createElement('canvas');
    c.width = 32; c.height = 32;          // whole image sampled, no region missed
    const cx = c.getContext('2d', { willReadFrequently: true });
    cx.drawImage(img, 0, 0, img.width, img.height, 0, 0, 32, 32);
    const d = cx.getImageData(0, 0, 32, 32).data;
    blank = true;
    for (let i = 3; i < d.length; i += 4) if (d[i] > 8) { blank = false; break; }
  } catch { blank = false; }
  _blankCache.set(img, blank);
  return blank;
}

/**
 * Average colour of a sprite visible pixels, cached per bitmap.
 * `DefaultBodyPiece` paints the hold body as a flat shape rather than a texture, so the
 * shape comes from the source and the colour from the skin own body sprite -- that keeps
 * each column palette (owc white/blue, Cho grey) instead of inventing one.
 */
const _avgCache = new WeakMap();
function avgColour(img) {
  if (!img) return null;
  const hit = _avgCache.get(img);
  if (hit !== undefined) return hit;
  let out = null;
  try {
    const c = document.createElement("canvas");
    c.width = 32; c.height = 32;
    const cx = c.getContext("2d", { willReadFrequently: true });
    cx.drawImage(img, 0, 0, img.width, img.height, 0, 0, 32, 32);
    const d = cx.getImageData(0, 0, 32, 32).data;
    let r = 0, g = 0, b = 0, n = 0;
    for (let i = 0; i < d.length; i += 4) {
      if (d[i + 3] > 8 && (d[i] > 12 || d[i + 1] > 12 || d[i + 2] > 12)) { r += d[i]; g += d[i + 1]; b += d[i + 2]; n++; }
    }
    if (n) out = [r / n / 255, g / n / 255, b / n / 255];
  } catch { out = null; }
  _avgCache.set(img, out);
  return out;
}

/**
 * osu! skins routinely author mania note / long-note parts on an OPAQUE BLACK
 * background — Cho's `Orbs/noteL.png` and `Orbs/noteT.png` are ~50% solid black.
 * Drawn as-is that shows as black slabs around the body; keying pure black out
 * leaves the LN transparent where the skin intends nothing.
 * Only note sprites are keyed: key images and the stage side panels are
 * legitimately opaque black in many skins (Cho's `4KR.png`, `mania-stage-left.png`).
 */
const _keyedCache = new WeakMap();
function keyOutBlack(img) {
  if (!img) return null;
  const cached = _keyedCache.get(img);
  if (cached) return cached;
  let out = img;
  try {
    const c = document.createElement('canvas');
    c.width = img.width; c.height = img.height;
    const cx = c.getContext('2d', { willReadFrequently: true });
    cx.drawImage(img, 0, 0);
    const data = cx.getImageData(0, 0, c.width, c.height);
    const p = data.data;
    let changed = false;
    for (let i = 0; i < p.length; i += 4) {
      if (p[i + 3] > 0 && p[i] < 12 && p[i + 1] < 12 && p[i + 2] < 12) { p[i + 3] = 0; changed = true; }
    }
    if (changed) { cx.putImageData(data, 0, 0); out = c; }
  } catch { out = img; }
  _keyedCache.set(img, out);
  return out;
}

/** Everything that caches a sprite must be dropped when the skin changes:
 *  the GPU texture slots (keyed by role), the hit-frame list and the flips. */
function invalidateSkinCaches() {
  if (renderer) renderer.resetTextures();
  _hitFrameCache.clear();
  _flipCache.clear();
  // _keyedCache is keyed by the bitmap itself, so a new skin's bitmaps simply miss it.
}

function flipV(img) {
  const key = img._flipKey || (img._flipKey = Symbol('flip'));
  if (_flipCache.has(key)) return _flipCache.get(key);
  const c = document.createElement('canvas');
  c.width = img.width; c.height = img.height;
  const ctx = c.getContext('2d');
  ctx.translate(0, img.height);
  ctx.scale(1, -1);
  ctx.drawImage(img, 0, 0);
  _flipCache.set(key, c);
  return c;
}

// ── background ──
async function loadBackground(url) {
  const img = new Image();
  img.crossOrigin = 'anonymous';
  img.src = url;
  await img.decode();
  const off = document.createElement('canvas');
  off.width = img.width; off.height = img.height;
  const octx = off.getContext('2d');
  if (bgBlur > 0) octx.filter = `blur(${bgBlur}px)`;
  octx.drawImage(img, 0, 0);
  bgImage = off;
  window._bgLoaded = true;
  window._bgSize = { w: img.width, h: img.height };
  if (renderer) renderer.uploadTexture('bg', off);
  drawFrame(audio.currentTime * 1000 || 0);
}

// Resolve the beatmapset id: metadata API first, then the id embedded in the .osu.
// Without this an unreachable metadata API meant no sid at all, so the audio and
// background were never even requested and 播放 had nothing to play.
function resolveSid(meta, bm) {
  return String(meta.beatmapset_id || meta.set_id || bm.beatmapSetID || '').replace(/^-1$/, '');
}

async function loadAudioAndBackground(bm, meta, sid) {
  // The GPU texture slot is keyed by a fixed role name, and `uploadTexture` returns the
  // cached texture on a hit — so without dropping it here the next beatmap kept drawing
  // the PREVIOUS song's background, cropped with the new image's UV rect. Clear both the
  // texture and `bgImage` so a failed fetch shows nothing rather than the old artwork.
  bgImage = null;
  window._bgLoaded = false;
  if (renderer) renderer.dropTexture('bg');

  // `bm.audioFilename` comes from parsers.js, which reads the `AudioFilename:` line of the
  // .osu this page already downloaded — that IS the authoritative name, and it is what the
  // mirror is addressed by (`files/{sid}/{name}`). The metadata API carries no audio
  // filename at all, so do NOT try to source it from `meta` here: asking the server to
  // backfill it costs an extra osu.ppy.sh round trip on every metadata request.
  const audioName = bm.audioFilename || 'audio.mp3';
  if (!sid) { setAudioState(false, '缺少曲包 ID，无法获取音频'); return; }
  // Build the URL once so the failure message can name it verbatim. `Failed to fetch` means
  // the browser got no response at all, which can only be told apart from a server error by
  // knowing the exact origin and path that was attempted.
  const audioUrl = `${API}/audio/${sid}/${encodeURIComponent(audioName)}`;
  // Remember the identity so the export can fall back to the neutral alias if fetching the
  // audio URL is what the client refuses to do (see encodeBeatmapAudio).
  window.__lastAudio = { sid, name: audioName, alias: `${API}/media/${sid}/${encodeURIComponent(audioName)}` };
  // Two delivery paths, tried in order, each labelled so a failure names the STEP instead of
  // collapsing into one opaque "fetch failed".
  //
  // PATH 1 hands the URL to the <audio> element. That is what a media element is for: it
  // streams through the browser's own network stack and never materialises an 11 MB Blob in
  // JS — the fewest moving parts between the server and the decoder.
  async function viaAudioElement() {
    return new Promise((resolve, reject) => {
      const cleanup = () => {
        clearTimeout(timer);
        audio.removeEventListener('loadedmetadata', onOk);
        audio.removeEventListener('error', onErr);
      };
      const onOk = () => { cleanup(); resolve(); };
      const onErr = () => {
        cleanup();
        reject(new Error(`<audio> 元素报错 code=${audio.error ? audio.error.code : '?'}`));
      };
      // 30 s is generous for 11 MB on loopback; it exists so this cannot hang forever.
      const timer = setTimeout(() => { cleanup(); reject(new Error('等待 loadedmetadata 超时')); }, 30000);
      audio.addEventListener('loadedmetadata', onOk);
      audio.addEventListener('error', onErr);
      audio.src = audioUrl;
      try { audio.load(); } catch (e) { /* load() is optional */ }
    });
  }

  // PATH 2 is EXACTLY what /diag does — fetch, read the body with arrayBuffer(), then wrap it
  // in a Blob. That is deliberate: /diag returned 200 with all 11,555,872 bytes for this same
  // URL in the reporting browser while the page's fetch->blob() path raised "Failed to
  // fetch", so the byte-level access that is known to work is the fallback.
  async function viaFetchBuffer() {
    let aRes = null, lastErr = null;
    for (let attempt = 0; attempt < 2 && !aRes; attempt++) {
      try {
        aRes = await fetch(audioUrl, { cache: 'no-store' });
      } catch (err) {
        lastErr = err;
        if (attempt === 0) { setAudioState(false, '音频获取失败，重试中…'); await new Promise(r => setTimeout(r, 1200)); }
      }
    }
    if (!aRes) throw new Error(`fetch 抛出：${(lastErr && (lastErr.message || lastErr.name)) || lastErr}`);
    if (!aRes.ok) {
      // A 502 carries {"error": ...} when no mirror would serve the set — in practice an
      // unranked / graveyard / delisted beatmap, which the mirrors do not carry at all.
      let why = '';
      try { why = (await aRes.json()).error || ''; } catch {}
      const detail = why ? ` — ${why}` : '';
      if (aRes.status === 502) throw new Error(`镜像站没有这张谱面的音频（未 rank / 已下架）${detail}`);
      throw new Error(`HTTP ${aRes.status}${detail}`);
    }
    let buf;
    try {
      buf = await aRes.arrayBuffer();
    } catch (err) {
      throw new Error(`读取正文失败（头 HTTP ${aRes.status}，Content-Length=${aRes.headers.get('content-length')}）：` +
                      `${(err && (err.message || err.name)) || err}`);
    }
    audio.src = URL.createObjectURL(new Blob([buf], { type: 'audio/mpeg' }));
  }

  try {
    try {
      await viaAudioElement();
    } catch (elErr) {
      try {
        await viaFetchBuffer();
      } catch (fetchErr) {
        // Keep BOTH complaints: the element and fetch paths fail for different reasons, and
        // knowing that they differ is itself the diagnosis.
        throw new Error(`元素路径→${elErr.message}；抓取路径→${fetchErr.message}`);
      }
    }
    setAudioState(true, '');
  } catch (err) {
    const why = (err && (err.message || err.name)) || String(err);
    setAudioState(false, `音频获取失败（${why}）页面来源=${location.origin} 请求=${audioUrl}`);
  }

  const bgName = bm.bgFilename || meta.background_filename;
  if (bgName) {
    loadBackground(`${API}/bg/${sid}/${encodeURIComponent(bgName)}`).catch(() => {
      loadBackground(`${API}/bg/${sid}/cover.jpg`).catch(() => {});
    });
  } else {
    loadBackground(`${API}/bg/${sid}/cover.jpg`).catch(() => {});
  }
}

/** Records whether a real audio track is available (drives the play-mode fallback). */
function setAudioState(ok, why) {
  hasAudio = ok;
  audioNote = why || '';
}

// ── load from bid ──
async function loadFromBid(bid) {
  info.textContent = `获取谱面 ${bid}…`;
  const osuRes = await fetch(`${API}/beatmap_osu/${bid}`);
  if (!osuRes.ok) throw new Error('谱面获取失败');
  beatmap = parseOsu(await osuRes.text());
  info.textContent = `${beatmap.title} [${beatmap.version}]  ${beatmap.keys}K → 获取音频…`;

  const metaRes = await fetch(`${API}/beatmap_meta?bid=${bid}`);
  const meta = metaRes.ok ? await metaRes.json() : {};
  if (meta.difficultyrating) beatmap.starRating = +meta.difficultyrating;
  if (!beatmap.bgFilename && meta.background_filename) beatmap.bgFilename = meta.background_filename;

  checkReady();
  await loadAudioAndBackground(beatmap, meta, resolveSid(meta, beatmap));
  info.textContent = `${beatmap.title} [${beatmap.version}]  ${beatmap.keys}K  ✓ 就绪` + audioNote;
}

// ── load from osr ──
// `fallbackBid` is the 谱面 ID typed in the drawer. It is only used when the replay's
// MD5 cannot be resolved online (sayobot unreachable / beatmap unranked), so an
// offline or blocked network still renders a replay instead of failing outright.
async function loadFromOsr(file, fallbackBid = null) {
  info.textContent = '解析 .osr…';
  // send to backend for LZMA decompression + MD5 lookup
  const fd = new FormData();
  fd.append('osr', file);
  const res = await fetch(`${API}/resolve_osr`, { method: 'POST', body: fd });
  if (!res.ok) throw new Error('osr 解析失败');
  const data = await res.json();
  if (data.error) throw new Error(data.error);

  replay = {
    beatmapMd5: data.md5,
    username: data.username,
    presses: data.presses || [],
    releases: data.releases || [],
    // Mirror (osu!stable bit 30) is a PLAY-TIME transform: the .osu file is never
    // rewritten, so a mirrored play records key presses in mirrored columns while the
    // beatmap still describes the unmirrored chart. Without the flip below every
    // judgement is matched to the wrong lane and the HUD reports nonsense.
    mirror: !!data.mirror,
    mods: data.mods | 0,
    // The judgement counts osu! itself recorded for this play, and which client
    // wrote the replay.  See setObjectModel()/reconcileJudgements(): a stable
    // replay counts a hold ONCE, a lazer replay TWICE, and the header's counts
    // are what the displayed accuracy is pinned to.
    counts: data.counts || null,
    classic: !!data.classic,
  };
  const md5 = data.md5;
  if (!md5) throw new Error('osr 中没有谱面 MD5');
  info.textContent = `MD5 ${md5.slice(0, 8)}… → 查询谱面…`;

  let bid = data.bid;
  const usedFallback = !bid && !!fallbackBid;
  if (usedFallback) bid = fallbackBid;
  if (!bid) throw new Error('谱面未找到（可在「谱面 ID」里手填后重试）');

  const metaRes = await fetch(`${API}/beatmap_meta?md5=${encodeURIComponent(md5)}`);
  const meta = metaRes.ok ? await metaRes.json() : {};

  const osuRes = await fetch(`${API}/beatmap_osu/${bid}`);
  if (!osuRes.ok) throw new Error('.osu 下载失败');
  beatmap = parseOsu(await osuRes.text());
  if (meta.difficultyrating) beatmap.starRating = +meta.difficultyrating;
  if (!beatmap.bgFilename && meta.background_filename) beatmap.bgFilename = meta.background_filename;
  // ManiaModMirror: `Column = (columnCount - 1) - Column`, applied the moment the chart
  // is loaded — exactly what the game does. It has to happen before buildHitMatch()
  // pairs presses with objects and before anything draws them, so the whole page
  // (judgements, combo, notes, LN bodies) agrees on the chart the player actually saw.
  if (replay.mirror) {
    const k = beatmap.keys;
    for (const h of beatmap.hitObjects) h.column = (k - 1) - h.column;
  }
  info.textContent = `${beatmap.title} [${beatmap.version}]  ${beatmap.keys}K → 获取音频…`;

  if (replay.presses.length) {
    const cols = replay.presses.reduce((m, p) => Math.max(m, p.key + 1), 0);
    if (cols > beatmap.keys)
      info.textContent = `⚠ 回放为 ${cols}K，谱面为 ${beatmap.keys}K，判定可能不匹配`;
  }

  checkReady();
  buildHitMatch();
  await loadAudioAndBackground(beatmap, meta, resolveSid(meta, beatmap));
  info.textContent = `${beatmap.title} [${beatmap.version}]  ${beatmap.keys}K  ✓ 就绪 (${replay.presses.length} presses)`
    + (usedFallback ? ' · MD5 未在线匹配，按填写的谱面 ID 配对' : '') + audioNote;
}

// ── skins ──
async function loadSkinList() {
  try {
    const r = await fetch(`${API}/skins`);
    const d = await r.json();
    skinList = d.skins || [];
    const sel = $('skinSel');
    sel.innerHTML = '';
    for (const s of d.skins || []) {
      const o = document.createElement('option');
      o.value = s.key;
      o.textContent = `${s.key} (${s.scroll})`;
      sel.appendChild(o);
    }
    if (d.skins && d.skins.length) {
      // The server names the default (`/api/skins` → `default`, currently boj) rather than
      // leaving it to dictionary order.
      const def = d.skins.find(s => s.key === d.default) || d.skins[0];
      sel.value = def.key;
      scrollSpeed = def.scroll || 30;
      $('scrollSpeed').value = scrollSpeed;
      await loadSkinByKey(def.key);
    }
  } catch {}
}

// Skin loads are asynchronous and a large .osk takes seconds. Without a generation
// token the initial auto-load can land AFTER the user picks another skin and silently
// overwrite it — the dropdown then shows one skin while the renderer draws another.
let skinLoadToken = 0;

/** Adopts a fully-loaded skin and re-resolves geometry for the current beatmap. */
function adoptSkin(loaded) {
  skin = loaded;
  ini = skin.ini;
  invalidateSkinCaches();
  if (beatmap) {
    applyIni();
    drawFrame(audio.currentTime * 1000 || 0);
  }
}

/** Returns false when a newer skin load superseded this one. */
async function loadSkinByKey(key) {
  const token = ++skinLoadToken;
  const r = await fetch(`${API}/skin_file/${encodeURIComponent(key)}`);
  if (!r.ok) throw new Error(`skin ${key} failed`);
  const loaded = await loadSkinFromZip(await readZip(await r.arrayBuffer()));
  if (token !== skinLoadToken) return false;
  adoptSkin(loaded);
  return true;
}

$('skinSel').addEventListener('change', async (e) => {
  if (!e.target.value) return;
  const key = e.target.value;
  info.textContent = `加载皮肤 ${key}…`;
  try {
    const applied = await loadSkinByKey(key);
    if (!applied) return;   // a newer selection won; leave its state alone
    // sync scroll speed from the skin list (per-skin memory)
    const sel = skinList.find(s => s.key === key);
    if (sel && sel.scroll) {
      scrollSpeed = sel.scroll;
      $('scrollSpeed').value = scrollSpeed;
      if (beatmap && ini) {
        applyIni();
        drawFrame(audio.currentTime * 1000 || 0);
      }
    }
    const decl = ini ? ini.declaredKeys.join('/') : '?';
    info.textContent = `皮肤 ${key} 已加载 (${skin.textures.size} 贴图 · [Mania] ${decl}K)`;
  } catch (err) { info.textContent = '皮肤错误: ' + err.message; }
});

$('fOsk').addEventListener('change', async (e) => {
  const f = e.target.files[0]; if (!f) return;
  const token = ++skinLoadToken;
  try {
    const loaded = await loadSkinFromZip(await readZip(await f.arrayBuffer()));
    if (token !== skinLoadToken) return;   // superseded by a newer skin selection
    adoptSkin(loaded);
    info.textContent = `皮肤已加载 (${skin.textures.size} 贴图)`;
  } catch (err) { info.textContent = '皮肤错误: ' + err.message; }
});

$('btnLoad').addEventListener('click', async () => {
  const bid = $('bidInput').value.trim();
  const f = $('fOsr').files[0];
  try {
    if (f) await loadFromOsr(f, bid || null);
    else if (bid) await loadFromBid(bid);
    else { info.textContent = '请输入谱面 ID 或上传 .osr'; return; }
  } catch (err) { info.textContent = '错误: ' + err.message; }
});

$('fOsr').addEventListener('change', async (e) => {
  const f = e.target.files[0]; if (!f) return;
  try { await loadFromOsr(f, $('bidInput').value.trim() || null); }
  catch (err) { info.textContent = '错误: ' + err.message; }
});

// Typing a 谱面 ID takes over from a selected .osr instead of silently losing to it:
// 加载 prefers the file, so with a .osr still selected the ID box looks like it does
// nothing. Clearing the selection on the first edit makes the ID authoritative again.
$('bidInput').addEventListener('input', () => {
  if (!$('fOsr').files.length) return;
  $('fOsr').value = '';
  const note = '已取消 .osr，改为按谱面 ID 加载';
  info.textContent = note;
});

$('btnClearOsr').addEventListener('click', () => {
  $('fOsr').value = '';
  replay = null;
  hitMatch = null;
  if (beatmap) drawFrame(audio.currentTime * 1000 || 0);
  info.textContent = '已取消 .osr，切换到自动游玩';
});

$('scrollSpeed').addEventListener('change', () => {
  scrollSpeed = +$('scrollSpeed').value || 30;
  if (beatmap && ini) { applyIni(); drawFrame(audio.currentTime * 1000 || 0); }
  // Per-skin scroll memory: persist so switching back to this skin restores the value.
  const key = $('skinSel').value;
  if (key) {
    const entry = skinList.find(s => s.key === key);
    if (entry) entry.scroll = scrollSpeed;
    fetch(`${API}/skin_scroll`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ skin: key, scroll: scrollSpeed }),
    }).catch(() => {});
  }
});
$('playSpeed').addEventListener('change', () => {
  const rate = +$('playSpeed').value;
  if (hasAudio) audio.playbackRate = rate;
  // rebase the clock so changing speed does not jump the playhead
  playStartPos = pausedAtMs;
  playStartWall = performance.now();
});
$('bgDim').addEventListener('input', () => {
  bgDim = +$('bgDim').value / 100;
  $('bgDimVal').textContent = $('bgDim').value + '%';
  drawFrame(audio.currentTime * 1000 || 0);
});
$('bgBlur').addEventListener('input', () => {
  bgBlur = +$('bgBlur').value;
  $('bgBlurVal').textContent = bgBlur;
});

// ── drawFrame ──
function drawFrame(nowMs) {
  if (!renderer || !geometry || !beatmap) return;
  const g = geometry;
  renderer.clear();

  // background — cover-cropped (scale to fill, then centre-crop), never stretched
  if (bgImage) {
    const uv = Renderer.coverUV(bgImage.width, bgImage.height, VIEW_W, VIEW_H);
    renderer.drawBackground(renderer.uploadTexture('bg', bgImage), 1 - bgDim, uv);
  }
  renderer.drawDim(0, 0, VIEW_W, VIEW_H, bgDim);

  // ── stage background ──
  // LegacyManiaColumnElement.FallbackColumnIndex: the middle column of an odd key
  // count is the "special" (S) column, otherwise parity of the distance to the edge
  // picks note1 / note2. This reproduces the wiki's "default key layout" table.
  const fallbackIdx = (col) => {
    if (g.keys % 2 === 1 && col === (g.keys - 1) / 2) return 'S';
    return Math.min(col, g.keys - 1 - col) % 2 === 0 ? '1' : '2';
  };
  const noteMap = (suffix) => suffix === 'H' ? block.noteImagesH
    : suffix === 'L' ? block.noteImagesL
      : suffix === 'T' ? block.noteImagesT
        : block.noteImages;
  /**
   * skin.ini custom name first, then the wiki default `mania-note{1|2|S}{suffix}`.
   * Existence is what decides, exactly like lazer's `GetAnimation` — a skin that ships
   * a transparent `mania-note{n}T` (owc's is 1x1) is deliberately saying "no tail cap",
   * and the fade at the tail comes from the body texture's own transparent rows instead.
   * Pure black is keyed out (Cho authors its LN parts on an opaque black background).
   */
  const pickTex = (name) => {
    const raw = getTex(name);
    return raw ? keyOutBlack(raw) : null;
  };
  const noteTex = (col, suffix = '') => {
    const m = noteMap(suffix);
    return pickTex(m && m[col]) || pickTex(`mania-note${fallbackIdx(col)}${suffix}`);
  };

  // column strips — a solid box per column, `Colour{n}` (1-based), opaque black by default
  for (let i = 0; i < g.keys; i++) {
    const [r, gg, b, a] = columnBackground(i);
    if (a <= 0) continue;
    renderer.drawColorQuad([r, gg, b], g.colX[i], 0, g.colW[i], VIEW_H, a, 0);
  }

  // ── column divider lines — LegacyStageBackground.ColumnBackground ──
  // `ColumnLineWidth` has `keys + 1` entries in 768-space, read left to right:
  //   [0] lane 0's left edge, [1..keys-1] the LEFT edge of every following lane,
  //   [keys] the last lane's right edge. So 4K = 5 boundaries (2 outer + 3 inner) and
  //   `0,5,5,5,0` means "no outer border, three 5-wide inner lines" — entry 0 of the array
  //   is the left border, which is why the two outer zeros switch the outer borders off.
  // A width of 0 means the line is not drawn at all (`hasLeftLine = leftLineWidth > 0`).
  // Both the inner and outer lines sit at the boundary rather than being duplicated from
  // each neighbouring column (lazer builds them per column — `ColumnLineWidth[i]` as that
  // column's left line and `ColumnLineWidth[i+1]` as its right line — which would draw
  // every shared boundary twice and double its alpha).
  // `Scale = new Vector2(0.740f, 1)` shrinks the width horizontally; the lines live in a
  // HitTargetInsetContainer, so they stop at the judgement line, not the column bottom.
  const lineW = block.columnLineWidth || [];
  // `LegacyColourCompatibility.ApplyWithDoubledAlpha`: Drawable.Alpha = colour.A and the
  // colour itself goes through DisallowZeroAlpha (a fully transparent colour becomes
  // opaque), so `ColourColumnLine: 0,0,0` is an opaque black line. Default white.
  const lc = block.colourColumnLine;
  const lineRGB = lc ? [lc[0] / 255, lc[1] / 255, lc[2] / 255] : [1, 1, 1];
  const lineAlpha = lc ? ((lc[3] === 0 ? 255 : lc[3]) / 255) : 1;
  for (let k = 0; k <= g.keys; k++) {
    const raw = lineW[k] || 0;
    if (raw <= 0) continue;
    const lw = raw * g.texScale * COLUMN_LINE_SCALE_X;
    const rightEdge = g.colX[g.keys - 1] + g.colW[g.keys - 1];
    const x = (k === g.keys) ? rightEdge - lw : g.colX[k];
    renderer.drawColorQuad(lineRGB, x, 0, lw, g.hitY, lineAlpha, 0);
  }

  // stage side bars — wiki: Origin BottomRight, stretched to the stage height.
  // The sprite's WIDTH is a texture dimension → texScale, not the 480-space factor.
  const sl = getTex(block.leftStageImage) || getTex('mania-stage-left');
  if (sl) { const sw = sl.width * g.texScale; renderer.drawQuad(renderer.uploadTexture('sl', sl), g.stageLeft - sw, 0, sw, VIEW_H, 1, 0); }
  const sr = getTex(block.rightStageImage) || getTex('mania-stage-right');
  if (sr) { const sw = sr.width * g.texScale; renderer.drawQuad(renderer.uploadTexture('sr', sr), g.stageRight, 0, sw, VIEW_H, 1, 0); }

  // ── stage light — wiki: `mania-stage-light`, Origin Bottom, positioned by `LightPosition`,
  //    tinted white by default (skin.ini `ColourLight`), and **placed underneath the notes**.
  //    LegacyColumnBackground puts it in a container anchored BottomCentre with
  //    `Padding.Bottom = LightPosition`, and the sprite inside it is BottomCentre with
  //    `RelativeSizeAxes = Axes.X; Width = 1` — stretched to the column width, bottom edge
  //    `LightPosition` above the bottom of the column.
  //
  //    BLEND: the wiki says Multiplicative, but `LegacyColumnBackground` sets **no**
  //    `Blending` at all — and every mania element that wants additive says so explicitly
  //    (`LegacyHitExplosion`, `LegacyBodyPiece`, `LegacyManiaComboCounter`, …). So lazer
  //    draws the light with normal alpha blending, and that is what we follow: a multiply
  //    with a white sprite is a mathematical no-op (factor `1 - a*(1-1)` = 1), so owc's
  //    white gradient could never glow. The previous revision used our multiplicative mode
  //    with a NON-premultiplied source, which evaluates to `dst*(rgb + 1 - a)` ≈ `dst*1.5`
  //    — a flat brightening, not the sprite's alpha ramp.
  //
  //    owc's light is 64x640: rows 0-329 fully transparent, rows 330-639 **white** with
  //    alpha ramping 10 -> 130, so it reads as a glow that bites hardest near the receptors.
  //    Cho' ships a fully transparent one, which must therefore draw nothing.
  const stageLight = getTex(block.stageLight) || getTex("mania-stage-light");
  if (stageLight) {
    const lightStates = stageLightState(nowMs);
    const lhFull = Math.min(stageLight.height, 768) * g.texScale;   // wiki: max height 768
    const lightBottom = VIEW_H - (block.lightPosition ?? 67) * g.scale;
    for (const [col, st] of lightStates) {
      const lh = lhFull * st.scaleY;
      if (lh <= 0 || st.alpha <= 0) continue;
      renderer.drawQuad(renderer.uploadTexture("slgt", stageLight),
        g.colX[col], lightBottom - lh, g.colW[col], lh, st.alpha, 0);
    }
  }

  // ── receptors (wiki: mania-key{1|2|S}, Origin Bottom, stretched to column width) ──
  // lazer's LegacyKeyArea anchors the container BottomCentre, so the key sprite's
  // bottom edge sits at the bottom of the column — not centred on the judgement line.
  // Width = column width (stretched); HEIGHT stays the texture's own height, which is
  // a texture dimension and therefore scales by texScale.
  const keyTexUp = (col) => getTex(block.keyImages[col]) || getTex(`mania-key${fallbackIdx(col)}`) || getTex('mania-key1');
  const keyTexDown = (col) => getTex(block.keyImagesD[col]) || getTex(`mania-key${fallbackIdx(col)}D`) || keyTexUp(col);
  const pressed = pressedColumns(nowMs);
  for (let i = 0; i < g.keys; i++) {
    const ki = (pressed.has(i) ? keyTexDown(i) : null) || keyTexUp(i);
    if (ki) {
      const kh = ki.height * g.texScale;
      renderer.drawQuad(renderer.uploadTexture('k' + i, ki), g.colX[i], VIEW_H - kh, g.colW[i], kh, 1, 0);
    } else {
      renderer.drawQuad(null, g.colX[i], g.hitY - 3, g.colW[i], 6, 0.7, 0);
    }
  }

  // ── judgement line ──
  // LegacyHitTarget: the hint sprite is ALWAYS drawn (`StageHint` overrides
  // `mania-stage-hint`, with no fallback), stretched to the full stage width with
  // Scale.y = 0.9 * 1.6025. The 1px white bar on top is the `JudgementLine` toggle.
  const hintName = block.stageHint || 'mania-stage-hint';
  const hint = getTex(hintName);
  if (hint) {
    const hh = hint.height * g.texScale * (0.9 * 1.6025);
    renderer.drawQuad(renderer.uploadTexture('hint', hint),
      g.stageLeft, g.hitY - hh / 2, g.stageRight - g.stageLeft, hh, 0.9, 0);
  }
  if (block.judgementLine !== false) {
    renderer.drawQuad(null, g.stageLeft, g.hitY - 0.5, g.stageRight - g.stageLeft, 1, 0.9, 0);
  }

  // ── notes ──
  // LegacyNotePiece.Update: noteHeight = WidthForNoteHeightScale ?? DrawWidth, then
  // sprite height = texH * noteHeight / texW. WidthForNoteHeightScale == 0 means
  // "not configured", in which case the height follows the column width.
  const spriteH = (img, colW) => {
    const noteHeight = block.widthForNoteHeight > 0
      ? block.widthForNoteHeight * g.scale
      : colW;
    return img.height * noteHeight / img.width;
  };

  for (const h of beatmap.hitObjects) {
    const t1 = h.time, t2 = h.isHold ? h.endTime : h.time;
    const y1 = g.hitY - (t1 - nowMs) / g.timeRange * g.hitY;
    const y2 = h.isHold ? g.hitY - (t2 - nowMs) / g.timeRange * g.hitY : y1;
    const margin = 100;
    if (Math.max(y1, y2) < -margin || Math.min(y1, y2) > VIEW_H + margin) continue;
    if (!h.isHold && nowMs > t1 + 150) continue;
    if (h.isHold && nowMs > t2 + 100) continue;

    const col = h.column;
    const cx = g.colX[col], cw = g.colW[col];
    const matched = hitMatch && hitMatch.objs.find(o => o.time === t1 && o.col === col)?.matched;

    if (h.isHold) {
      // ── hold note composition (osu.Game.Rulesets.Mania/Objects/Drawables/DrawableHoldNote.cs) ──
      //
      // lazer builds a hold note from four pieces, and every position below comes from
      // that one model rather than from per-element tweaks:
      //
      //   Head   — a note sprite at the head's time position, drawn OUTSIDE the mask so it
      //            stays visible while the note is held (bottom-aligned like any note).
      //   Body   — "Position and resize the body to lie half-way under the head and the
      //            tail notes. The rationale for this is account for heads/tails with
      //            corner radius." So the body spans tailCentre → headCentre.
      //   Tail   — a sprite at the tail's time position, INSIDE the mask.
      //   Mask   — while held, a mask whose edge sits Head.Height/2 above the shrinking
      //            container bottom eats the hold from the head end; body and tail are
      //            clipped at that edge, which is why nothing can poke out past the head.
      const headImg = noteTex(col, 'H') || noteTex(col, '');
      const tailImg = noteTex(col, 'T') || noteTex(col, 'H') || noteTex(col, '');
      // Extents, not sprite boxes: a placeholder sprite measures 0 (see isBlankSprite).
      const hh = (headImg && !isBlankSprite(headImg)) ? spriteH(headImg, cw) : 0;
      const th = (tailImg && !isBlankSprite(tailImg)) ? spriteH(tailImg, cw) : 0;

      // The head falls with the note, then parks on the judgement line while held — bottom
      // aligned, so the held position is exactly where notes disappear.
      const headY = nowMs < t1 ? y1 : g.hitY;
      // The mask edge: the head's centre. Everything below is eaten as the hold progresses.
      // The mask bottom edge is CONSTANT in time: judgement line - Head.Height/2. At rest it
      // is a strict superset of the body, so the mask is a no-op until the note is held.
      const maskBottom = g.hitY - hh / 2;

      // Source: legacy bodyTop = y2 - Tail.Height/2 ("half-way under the tail"), whose stated
      // purpose is to fill the tail sprite rounded corners. That only works when the tail
      // sprite is as wide as the lane. Cho tail is a dome narrower than the lane, so the
      // overlapped half of a lane-wide body shows as grey shoulders either side of the tail.
      // Stop the body at the tail own time position: the tail then butts cleanly onto it.
      const bodyTop = y2;
      const bodyBot = headY - hh / 2;
        if (bodyBot > bodyTop) {
          // body -- the skin own NoteImage{n}L, tiled at its natural aspect unless
          // NoteBodyStyle: Stretch (lazer LegacyBodyPiece picks WrapMode.Repeat otherwise).
          const clipTop = Math.max(bodyTop, -margin);
          const clipBot = Math.min(bodyBot, VIEW_H + margin);
          const bodyImg = noteTex(col, "L");
          const stretch = String(block.noteBodyStyle || "").toLowerCase() === "stretch";
          if (bodyImg && clipBot > clipTop) {
            const hpx = clipBot - clipTop;
            if (stretch) {
              renderer.drawQuad(renderer.uploadTexture("b" + col, bodyImg), cx, clipTop, cw, hpx, 1, 0);
            } else {
              // Non-Stretch branch of LegacyBodyPiece.Update(): the sprite fills the body
              // rect and is then scaled by max(1, 32800 / sprite.DrawHeight), so the texture
              // always occupies a FIXED 32800 lazer-units (768-space) from the body TOP,
              // clipped by the rect. The visible slice is the top (hpx / 32800u) of the
              // texture, wrapping if the texture is shorter than that.
              const unitH = 32800 * g.texScale;
              const v0 = (clipTop - bodyTop) / unitH;
              renderer.drawQuad(renderer.uploadTexture("b" + col, bodyImg, "repeat"),
                cx, clipTop, cw, hpx, 1, 0, [0, v0, 1, v0 + hpx / unitH]);
            }
          } else if (clipBot > clipTop) {
            renderer.drawQuad(null, cx, clipTop, cw, clipBot - clipTop, 0.5, 0);
          }
        }

      // tail -- painted BEFORE the head (maskedContents order: body proxy, tail proxy; the
      // head lives in headContainer and is drawn last). Inside the mask, whose bottom edge is
      // the constant judgement line - Head.Height/2, it is clipped from the bottom as it
      // arrives. lazer flips it unconditionally; we still honour NoteFlipWhenUpsideDownT.
      if (nowMs < t2 && tailImg && th > 0) {
        const flipCfg = block.flips['NoteFlipWhenUpsideDownT'];
        const flipTail = flipCfg === undefined ? true : flipCfg !== '0';
        const drawn = flipTail ? flipV(tailImg) : tailImg;
        const tailTop = y2 - th;
        const tailBot = Math.min(y2, maskBottom);
        if (tailBot > tailTop && tailBot > -margin && tailTop < VIEW_H + margin) {
          renderer.drawQuad(renderer.uploadTexture('t' + col + (flipTail ? 'f' : ''), drawn),
            cx, tailTop, cw, tailBot - tailTop, 1, 0, [0, 0, 1, (tailBot - tailTop) / th]);
        }
      }

      // head -- outside the mask and painted LAST, so it caps the front of the note
      if (nowMs <= t2 && headImg) {
        if (headY - hh < VIEW_H + margin && headY > -margin) {
          renderer.drawQuad(renderer.uploadTexture('h' + col, headImg), cx, headY - hh, cw, hh, 1, 0);
        }
        }


    } else {
      // normal note — wiki: Origin Bottom, so the sprite's bottom edge sits at its time
      // position. Once that edge touches the judgement line the note is gone; it must not
      // linger clamped on the line. A note the replay marked as MISSED keeps falling.
      if (y1 - VIEW_H > margin) continue;
      if (nowMs > t1 && matched) continue;
      const missed = !!(hitMatch && hitMatch.objs.find(o => o.time === t1 && o.col === col && !o.matched));
      if (!missed && y1 >= g.hitY) continue;
      const img = noteTex(col, '') || getTex('note');
      const nh = img ? spriteH(img, cw) : cw * 0.25;
      if (y1 - nh > VIEW_H + margin) continue;
      if (img) renderer.drawQuad(renderer.uploadTexture('n' + col, img), cx, y1 - nh, cw, nh, 1, 0);
      else renderer.drawQuad(null, cx, y1 - nh, cw, nh, 1, 0);
    }
  }

  // ── stage foreground — wiki: mania-stage-bottom, drawn over the notes,
  //    NOT stretched to the stage width (0.625x of it), anchored to the bottom.
  //    lazer LegacyStageForeground applies Scale = 1.6 on top of the texture size. ──
  const bottom = getTex(block.bottomStageImage) || getTex('mania-stage-bottom');
  if (bottom) {
    // lazer LegacyStageForeground: natural texture size with Scale = 1.6 on top.
    const bw = bottom.width * g.texScale * 1.6;
    const bh = bottom.height * g.texScale * 1.6;
    renderer.drawQuad(renderer.uploadTexture('stagebottom', bottom),
      g.stageLeft + (g.stageRight - g.stageLeft) / 2 - bw / 2, VIEW_H - bh, bw, bh, 1, 0);
  }

  // ── hit lighting — wiki: lightingN (single/tail) & lightingL (hold), Additive,
  //    Origin Centre, at the judgement-line × lane-centre crossing. Skin pixels only. ──
  const lightFramesOf = (name) => {
    const frames = [];
    for (let i = 0; i < 64; i++) {
      const f = getTex(name + '-' + i);
      if (!f) break;
      frames.push(f);
    }
    if (!frames.length) {
      const single = getTex(name);
      if (single) frames.push(single);
    }
    return frames;
  };
  const comboBursts = getHitFrames('comboburst-mania');
  const lightN = lightFramesOf(block.lightingN || 'lightingN');
  const lightL = lightFramesOf(block.lightingL || 'lightingL');
  const drawLight = (frames, widths, col, age) => {
    if (!frames.length || age < 0 || age > 200) return;
    const alpha = age < 80 ? age / 80 : Math.max(0, 1 - (age - 80) / 120);
    // lazer: frameLength = max(1000/60, 170 / frameCount)
    const frameLen = Math.max(1000 / 60, 170 / frames.length);
    const fi = Math.min(frames.length - 1, Math.floor(age / frameLen));
    const img = frames[fi];
    // LightingNWidth / LightingLWidth are the lighting sprite's width in 480-space
    // (lazer stores them as `ExplosionWidth`); absent means "use the texture size",
    // which is a texture dimension and so scales by texScale.
    const configured = (widths && widths[col]) || 0;
    const lw = configured > 0 ? configured * g.scale : img.width * g.texScale;
    const lh = img.height * (lw / img.width);
    renderer.drawQuad(renderer.uploadTexture('lf' + col + fi + frames.length, img),
      g.colX[col] + g.colW[col] / 2 - lw / 2, g.hitY - lh / 2, lw, lh, alpha, 1);
  };
  for (const p of pressLog(nowMs)) {
    const col = p.key % g.keys;
    drawLight(p.hold ? lightL : lightN, p.hold ? block.lightingLWidth : block.lightingNWidth, col, nowMs - p.time);
  }

  // ── per-note judgement sprites (wiki: mania-hit*) — replay only, auto-play = empty ──
  // Placement is LegacyManiaJudgementPiece.onDirectionChanged(). Write S / H for the
  // ×1.6 config values of ScorePosition / HitPosition, i.e. in lazer's 768-space:
  //   hitPositionFromTop = 768 - H
  //   S > hitPositionFromTop / 2  ->  Anchor BottomCentre, Y = S - (768 - H)
  //   else                        ->  Anchor TopCentre,    Y = S
  // The piece's parent is the Stage's HitPositionPaddedContainer, whose Padding.Bottom is
  // the raw HitPosition config value, so its content box is exactly `768 - H` tall. With
  // Origin = Centre the two branches then both resolve to:
  //   BottomCentre: centre = (768 - H) + (S - (768 - H)) = S
  //   TopCentre   : centre = 0 + S                       = S
  // i.e. the branch never moves the sprite: a mania hit burst always sits at ScorePosition
  // measured from the top of the stage, wherever the judgement line happens to be.
  // ScorePosition is stored raw in 480-space, so 768-space -> our view is just VIEW_H/480.
  if (hitMatch && replay && replay.presses.length) {
    const burstCentreY = (block.scorePosition ?? 300) * g.scale;
    let drawn = false;
    for (const obj of hitMatch.objs) {
      const age = nowMs - obj.time;
      if (age < 0 || age > 600) continue;
      const alpha = age < 80 ? age / 80 : Math.max(0, 1 - (age - 80) / 520);
      let hitKey;
      if (!obj.matched) hitKey = "hit0";
      else {
        const err = Math.abs(obj.error);
        if (err <= 16) hitKey = "hit300g";
        else if (err <= 37) hitKey = "hit300";
        else if (err <= 70) hitKey = "hit200";
        else if (err <= 100) hitKey = "hit100";
        else hitKey = "hit50";
      }
      const baseName = (block.hitSprites && block.hitSprites[hitKey]) || ("mania-" + hitKey);
      const frames = getHitFrames(baseName);
      if (!frames.length) continue;
      const fi = Math.floor(age / (1000 / 60)) % frames.length;   // wiki: fixed 60 FPS loop
      const img = frames[fi];
      // Sizing: the source draws this at its natural texture size (AutoSizeAxes.Both),
      // which for wide skins overflows the lane. Scaled to a fraction of the LANE WIDTH
      // instead, preserving aspect ratio (scaled, never stretched).
      const bw = g.colW[obj.col] * HIT_BURST_LANE_FRACTION;
      const bh = bw * (img.height / img.width);
      const cx = g.colX[obj.col] + g.colW[obj.col] / 2;
      renderer.drawQuad(renderer.uploadTexture("j_" + hitKey + "_" + fi, img),
        cx - bw / 2, burstCentreY - bh / 2, bw, bh, alpha, 0);
      lastBurstRect = {
        key: hitKey, fi, col: obj.col, cx, cy: burstCentreY, w: bw, h: bh,
        natural: [img.width, img.height], laneW: g.colW[obj.col], alpha,
      };
      drawn = true;
    }
    if (!drawn) lastBurstRect = null;
  } else lastBurstRect = null;

  // ── comboburst — wiki: comboburst-mania[-{n}].png, Origin BottomLeft, max height 768px,
  // one of the set appears when a combo milestone is met. osu uses every 50; the wiki does
  // not state a number, so 50 is the convention we follow. Stateless so seeking stays sane:
  // the burst shows while a multiple of 50 lies within the last COMBO_BURST_MS.
  const COMBO_BURST_MS = 900;
  if (comboBursts.length) {
    const cur = getCombo(nowMs);
    const milestone = Math.floor(cur / 50) * 50;
    if (milestone > 0 && getCombo(nowMs - COMBO_BURST_MS) < milestone) {
      const img = comboBursts[(milestone / 50) % comboBursts.length];
      const h = Math.min(img.height, 768) * g.texScale;
      const w = img.width * (h / img.height);
      const age = nowMs - Math.max(0, nowMs - COMBO_BURST_MS);
      const alpha = Math.min(1, age / 120) * Math.max(0, 1 - age / COMBO_BURST_MS);
      renderer.drawQuad(renderer.uploadTexture("combo" + ((milestone / 50) % comboBursts.length), img),
        0, VIEW_H - h, w, h, alpha, 0);
    }
  }

  // ── warning arrow — wiki: mania-warningarrow.png, Origin Centre, points down, shown
  // before the map starts.
  const warnArrow = getTex(block.warningArrow) || getTex("mania-warningarrow");
  const firstObject = beatmap.hitObjects.length ? beatmap.hitObjects[0].time : 0;
  if (warnArrow && nowMs < firstObject) {
    const wh = warnArrow.height * g.texScale;
    const ww = warnArrow.width * g.texScale;
    renderer.drawQuad(renderer.uploadTexture("warnarrow", warnArrow),
      (g.stageLeft + g.stageRight) / 2 - ww / 2, VIEW_H / 2 - wh / 2, ww, wh, 1, 0);
  }

  drawHUD(nowMs);
  // update bottom time
  const elapsed = Math.max(0, nowMs / 1000);
  const total = Math.max(0, (beatmap.duration || 0) / 1000);
  $('time').textContent = `${fmt(elapsed)} / ${fmt(total)}`;
  if (!seekDragging) $('seek').value = Math.min(10000, Math.round((nowMs / Math.max(1, beatmap.duration || 1)) * 10000));
}

function fmt(s) {
  if (!isFinite(s) || s < 0) s = 0;
  return `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
}

// ── HUD (osu component layout) ──
function drawHUD(nowMs) {
  hudCtx.clearRect(0, 0, VIEW_W, VIEW_H);
  const elapsed = Math.max(0, nowMs / 1000);
  const total = Math.max(0, (beatmap.duration || 0) / 1000);
  const pct = total > 0 ? Math.min(1, elapsed / total) : 0;

  // 1. ComboCounter — TopLeft(20, 20)
  hudCtx.fillStyle = '#fff';
  hudCtx.font = 'bold 56px system-ui';
  hudCtx.textAlign = 'left';
  hudCtx.fillText(`${getCombo(nowMs)}x`, 20, 20 + 56);

  // 2. BeatmapAttributeText — TopRight(-20, 20) — difficulty name, NOT key count
  hudCtx.textAlign = 'right';
  hudCtx.font = '24px system-ui';
  hudCtx.fillStyle = '#fff';
  const diffName = beatmap.version || beatmap.title || '';
  hudCtx.fillText(diffName.length > 30 ? diffName.slice(0, 28) + '…' : diffName, VIEW_W - 20, 20 + 24);

  // 3. BPMCounter — TopRight(-20, 55)
  hudCtx.font = '24px system-ui';
  const bpm = getBPM(nowMs);
  hudCtx.fillText(bpm ? `${Math.round(bpm)} BPM` : 'BPM', VIEW_W - 20, 55 + 24);

  // 4. SongProgress — TopRight(-20, 100)
  hudCtx.font = '20px system-ui';
  hudCtx.fillStyle = '#ccc';
  hudCtx.fillText(`${Math.floor(elapsed)}s / ${Math.floor(total)}s (${Math.round(pct * 100)}%)`, VIEW_W - 20, 100 + 20);

  // 5. AccuracyCounter — BottomRight(-20, -50)
  hudCtx.textAlign = 'right';
  hudCtx.font = '28px system-ui';
  hudCtx.fillStyle = '#fff';
  // Two accuracy figures, unlabelled, SIDE BY SIDE on the one line the skin
  // gives this component: lazer's first (ScoreProcessor, where a PERFECT is
  // worth 305), then osu!stable's (Perfect and Great both 300, denominator 300
  // per judgement). They disagree on every play that is not all-perfect, so
  // both are shown.
  //
  // Side by side rather than stacked on purpose: the clicks-per-second counter
  // sits at BottomRight(-20, -90), and a second line 34px above this one ran
  // straight through it. Sharing the baseline costs width, not height, and this
  // component is right-anchored, so the extra width grows away from everything.
  hudCtx.fillText(`${getAccuracy(nowMs).toFixed(2)}% ${getAccuracyStable(nowMs).toFixed(2)}%`,
    VIEW_W - 20, VIEW_H - 50);

  // 6. ClicksPerSecondCounter — BottomRight(-20, -90)
  hudCtx.font = '20px system-ui';
  hudCtx.fillStyle = '#ccc';
  hudCtx.fillText(`${getCPS(nowMs)} clicks/sec`, VIEW_W - 20, VIEW_H - 90);

  // 7. BarHitErrorMeter — BottomCentre 20px up (replay only)
  if (replay && hitMatch) {
    drawErrorBar(nowMs);
  }

  // 8. Judgement panel — LeftCentre (replay only)
  if (replay && hitMatch) {
    drawJudgePanel(nowMs);
  }
}

function drawErrorBar(nowMs) {
  const barW = 500, barH = 6;
  const cx = VIEW_W / 2, y = VIEW_H - 20 - barH;
  const x0 = cx - barW / 2;

  // background
  hudCtx.fillStyle = 'rgba(255,255,255,0.12)';
  hudCtx.fillRect(x0, y, barW, barH);

  // zone colours (mania hit windows: 16/37/70/100 ms for MAX/300/200/100)
  const zones = [
    [16, 'rgba(120,230,220,0.25)'],
    [37, 'rgba(245,215,80,0.20)'],
    [70, 'rgba(170,210,120,0.15)'],
    [100, 'rgba(240,168,104,0.12)'],
  ];
  for (const [ms, color] of zones) {
    const w = (ms / 120) * barW / 2;
    hudCtx.fillStyle = color;
    hudCtx.fillRect(cx - w, y, w * 2, barH);
  }

  // centre line
  hudCtx.fillStyle = 'rgba(255,255,255,0.7)';
  hudCtx.fillRect(cx - 1, y - 2, 2, barH + 4);

  // ticks for recent hits (fade over 5s)
  if (!hitMatch) return;
  for (const obj of hitMatch.objs) {
    if (!obj.matched) continue;
    const age = nowMs - obj.time;
    if (age < 0 || age > 5000) continue;
    const alpha = age < 100 ? age / 100 : Math.max(0, 1 - (age - 100) / 4900);
    const err = Math.max(-120, Math.min(120, obj.error));
    const tx = cx + (err / 120) * (barW / 2);
    hudCtx.fillStyle = `rgba(100,200,255,${alpha * 0.85})`;
    hudCtx.fillRect(tx - 1, y - 3, 2, barH + 6);
  }

  // moving-average chevron
  let sum = 0, n = 0;
  for (const obj of hitMatch.objs) {
    if (obj.time > nowMs) break;
    if (obj.matched) { sum += obj.error; n++; }
  }
  if (n > 0) {
    const avg = Math.max(-120, Math.min(120, sum / n));
    const ax = cx + (avg / 120) * (barW / 2);
    hudCtx.fillStyle = 'rgba(255,255,255,0.7)';
    hudCtx.beginPath();
    hudCtx.moveTo(ax, y - 8);
    hudCtx.lineTo(ax - 5, y - 2);
    hudCtx.lineTo(ax + 5, y - 2);
    hudCtx.fill();
  }
}

function drawJudgePanel(nowMs) {
  const c = getJudgeCounts(nowMs);
  const x = 24, y = VIEW_H / 2 - 130;
  // Ratio = MAX/300 (python: ratio_label)
  let ratio = '—';
  if (c.g300 > 0) ratio = (c.max / c.g300).toFixed(1);
  else if (c.max > 0) ratio = '∞';
  const ur = getUR(nowMs);
  const rows = [
    ['Ratio', ratio, '#fff', true],
    ['MAX', String(c.max), '#78e6dc', false],
    ['300', String(c.g300), '#f5d750', false],
    ['200', String(c.g200), '#aad278', false],
    ['100', String(c.g100), '#f0a868', false],
    ['50', String(c.g50), '#e06c75', false],
    ['0', String(c.miss), '#a0a0a0', false],
    ['UR', ur, '#e0e0e8', true],
  ];
  hudCtx.textAlign = 'left';
  for (let i = 0; i < rows.length; i++) {
    const [label, val, color, bold] = rows[i];
    hudCtx.font = bold ? 'bold 22px system-ui' : '22px system-ui';
    hudCtx.fillStyle = '#fff';
    hudCtx.fillText(label, x, y + i * 30);
    hudCtx.fillStyle = color;
    hudCtx.fillText(val, x + 80, y + i * 30);
  }
}

function getUR(nowMs) {
  if (!hitMatch) return '—';
  let n = 0, mean = 0, m2 = 0;
  for (const obj of hitMatch.objs) {
    if (obj.time > nowMs) break;
    if (!obj.matched) continue;
    n++;
    const x = obj.error;
    const delta = x - mean;
    mean += delta / n;
    m2 += delta * (x - mean);
  }
  if (n < 2) return '—';
  return (10 * Math.sqrt(m2 / n)).toFixed(1);
}

// ── drawer: slides out when the pointer approaches the bottom edge ───────────
// Everything except the playfield lives in here, so the stage stays unobstructed.
const drawer = $('drawer');
let drawerPinned = false;
let drawerHideTimer = 0;

function setDrawer(open) {
  if (open === drawerPinned) return;
  drawerPinned = open;
  drawer.classList.toggle('open', open);
}

// Is the pointer over the drawer, or on the strip that summons it?
let pointerOnDrawer = false;
let pointerNearBottom = false;

// Pinning the drawer open for as long as a text field has focus left it stuck open
// forever: focus does not expire, so once you had typed in 谱面 ID the drawer never
// closed again even with the pointer far away and nothing loaded. Keep the pin, but let
// it lapse a few seconds after the last keystroke unless the pointer is still on the
// drawer — so you can type undisturbed, then move away and have it hide.
const TYPING_HOLD_MS = 3000;
let lastKeystroke = 0;

/** Focus inside a text-like control in the drawer keeps it open (see TYPING_HOLD_MS). */
function typingInsideDrawer() {
  const el = document.activeElement;
  const tag = (el && el.tagName) || '';
  if (!el || !drawer.contains(el)) return false;
  return tag === 'TEXTAREA' || el.isContentEditable
    || (tag === 'INPUT' && !['range', 'file'].includes(el.type))
    || tag === 'SELECT';
}

function updateDrawer() {
  const typingFresh = typingInsideDrawer() && Date.now() - lastKeystroke < TYPING_HOLD_MS;
  setDrawer(pointerNearBottom || pointerOnDrawer || typingFresh);
  // While a field holds focus but the pointer has moved away, re-check once the hold
  // lapses so the drawer closes without waiting for another mouse move.
  clearTimeout(drawerHideTimer);
  if (typingInsideDrawer() && !pointerOnDrawer && !pointerNearBottom) {
    drawerHideTimer = setTimeout(updateDrawer, TYPING_HOLD_MS + 50);
  }
}

window.addEventListener('mousemove', (e) => {
  pointerNearBottom = e.clientY >= window.innerHeight - 18;
  pointerOnDrawer = !!(e.target && e.target.closest && e.target.closest('#drawer'));
  updateDrawer();
});
window.addEventListener('keydown', () => { lastKeystroke = Date.now(); updateDrawer(); });
window.addEventListener('mouseleave', () => {
  pointerOnDrawer = pointerNearBottom = false;
  updateDrawer();
});

// ── fullscreen ───────────────────────────────────────────────────────────────
// The document element (not #stage) so the drawer stays reachable in fullscreen.
function toggleFullscreen() {
  if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
  else document.documentElement.requestFullscreen().catch(() => {});
}
$('btnFull').addEventListener('click', toggleFullscreen);
document.addEventListener('fullscreenchange', () => {
  $('btnFull').textContent = document.fullscreenElement ? '⛶ 退出全屏' : '⛶ 全屏';
  // the status overlay is a dev read-out, not part of the picture
  document.body.classList.toggle('noinfo', !!document.fullscreenElement);
});

// ── playback ──
function tick() {
  if (!playing || !beatmap) return;
  let nowMs;
  if (hasAudio && !audio.paused) {
    // audio is the master clock so picture and music cannot drift apart
    nowMs = (audio.currentTime || 0) * 1000;
    playStartPos = nowMs;
    playStartWall = performance.now();
  } else {
    nowMs = currentTimeMs();
  }
  pausedAtMs = nowMs;
  const total = beatmap.duration || 0;
  if (total > 0 && nowMs >= total) { pausePlayback(); return; }
  drawFrame(nowMs);
  animFrame = requestAnimationFrame(tick);
}

function setPlayButton(isPlaying) {
  $('btnPlay').textContent = isPlaying ? '⏸ 暂停' : '▶ 播放';
  $('btnPlay').classList.toggle('playing', isPlaying);
}

function startPlayback() {
  if (!beatmap) return;
  if (playing) return;
  const rate = +$('playSpeed').value;
  playStartPos = pausedAtMs;
  playStartWall = performance.now();
  playing = true;
  setPlayButton(true);
  cancelAnimationFrame(animFrame);
  if (hasAudio) {
    audio.playbackRate = rate;
    audio.play().catch(() => {
      // a browser can refuse to start audio; the clock keeps the render going
      setAudioState(false, '音频无法播放，已切换为无声播放');
      info.textContent = (info.textContent || '') + ' · 无声播放';
    });
  }
  tick();
}

function pausePlayback() {
  if (hasAudio) { try { audio.pause(); } catch {} }
  if (playing) {
    pausedAtMs = currentTimeMs();
  }
  playing = false;
  cancelAnimationFrame(animFrame);
  setPlayButton(false);
  drawFrame(pausedAtMs);
}

function togglePlayback() { if (playing) pausePlayback(); else startPlayback(); }

function resetPlayback() {
  if (hasAudio) { try { audio.pause(); audio.currentTime = 0; } catch {} }
  playing = false; pausedAtMs = 0; cancelAnimationFrame(animFrame);
  setPlayButton(false);
  drawFrame(0);
}

$('btnPlay').addEventListener('click', togglePlayback);
$('btnReset').addEventListener('click', resetPlayback);

// Space toggles playback, unless a form control has focus.
window.addEventListener('keydown', (e) => {
  if (e.code !== 'Space' && e.key !== ' ') return;
  const el = document.activeElement;
  const tag = (el && el.tagName) || '';
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || tag === 'BUTTON' || (el && el.isContentEditable)) return;
  e.preventDefault();
  togglePlayback();
});

$('seek').addEventListener('mousedown', () => { seekDragging = true; });
$('seek').addEventListener('mouseup', () => { seekDragging = false; });
$('seek').addEventListener('input', (e) => {
  if (!beatmap) return;
  const t = (+e.target.value / 10000) * (beatmap.duration || 1);
  seekTo(t);
  if (playing) { playStartPos = t; playStartWall = performance.now(); }
  drawFrame(t);
});
drawVolCircle();

// ── export ──
// This is a CANVAS RECORDING, not a render: `captureStream` + MediaRecorder only produce
// frames as they are painted, so the export always takes **1x real time** — a 3:08 chart
// needs the whole song's worth of wall clock (measured: `audio.currentTime` advances at
// exactly 1 s/s), and nothing appears until it finishes.
//
// It used to stop only on `audio.onended`, which broke in three ways:
//   * no audio track (the fetch failed) -> `startPlayback` never plays, `onended` never
//     fires, and the button sat on 导出中… forever;
//   * the track can outlast the chart (201.7 s of audio for a 188.1 s chart here), so it
//     also recorded ~14 s of empty playfield;
//   * pausing mid-export made it hang the same way.
// The stop condition is now the CHART clock, `audio.onended` is only a backstop, the
// button reports progress, and a second click cancels.
// ── WebCodecs export ─────────────────────────────────────────────────────────
// MediaRecorder samples the canvas against the wall clock, so an export can never beat
// 1x and its frame rate collapses on any machine that cannot paint 60fps. VideoEncoder
// takes the timestamps WE choose: rendering speed and video time are independent, so a
// chart exports at whatever rate the machine draws and the result is exactly 60fps.
//
// `avc.format = 'annexb'` makes Chrome emit start-code delimited H.264 (verified on this
// build), which ffmpeg reads as a raw elementary stream — no JS muxer is needed. Chunks
// are streamed to the server as they are produced rather than accumulated: a 5-minute
// chart is roughly 200 MB of encoded data and holding all of it would be its own bug.
const WC_FPS = 60;

// The two bitrate constants the export picks between. The file has to survive a delivery
// channel, and which channel decides the ceiling:
//
//   * A BOT render is uploaded — the service muxes it, the plugin downloads it and hands
//     it to the protocol adapter, and the adapter pushes it over a WebSocket upload that
//     times out on a large body. Measured on a real user render: 6 Mbps produced 74.8 MB
//     for an 86 s chart, the send call timed out, and the plugin reported a failure even
//     though the video had already arrived in the chat. The rate for this path is NOT
//     chosen here — the service sets `window.__webglBitrate` from the request's
//     `bitrate_kbps` (see mania_render/webapp.py), so the number lives in one place.
//   * A MANUAL export (a human clicking 导出) is written straight to the local downloads
//     folder and never crosses an upload channel, so it keeps the higher rate. Nothing
//     sets `__webglBitrate` on that path, which is what MANUAL_BITRATE is the fallback for.
const MANUAL_BITRATE = 6_000_000;

// Size backstop for the bot path, independent of the requested rate: the plugin switches
// from the video channel to the file channel at `video_file_threshold_mb` (80 MB), so an
// unusually long chart must not sail past it on a high requested rate. 72 MB is the ceiling
// for the WHOLE file, so it bounds the total rather than just the video; the budget below
// subtracts the audio the mux is about to add, because a cap that ignores the 192 kbps AAC
// track is off by ~8% and that is exactly the margin that matters at 4+ minutes.
//
// Measured effect: the cap does not bind at all for a 4:11 chart at the 2000 kbps default
// (2.21 Mbps allowed there vs 2.0 requested), and only starts pulling the rate down past
// ~5 minutes — where it holds the delivered file near 75 MB instead of growing without
// limit. A manual export is exempt: it is never uploaded, so capping it would only take
// quality away for nothing.
const BOT_MAX_BYTES = 72 * 1024 * 1024;
const MUX_AUDIO_BPS = 192_000;

/**
 * Encode the beatmap audio to AAC for the in-page muxer.
 *
 * The export used to be silent: MediaRecorder only ever saw the canvas, and the server
 * path muxes audio afterwards with ffmpeg. A browser-side export has no ffmpeg, so the
 * audio has to be encoded here — `fetch` works on the blob: URL the player already uses,
 * `decodeAudioData` turns it into PCM, and AudioEncoder turns that into AAC.
 */
async function encodeBeatmapAudio(onProgress, isCancelled) {
  if (!audio || !audio.src) return null;
  // Second attempt uses `/api/media/...`: byte-identical content under a neutral path and
  // content type, so a client that refuses the media-typed URL can still export instead of
  // the whole render dying on this fetch.
  let raw;
  try {
    raw = await (await fetch(audio.src)).arrayBuffer();
  } catch (err) {
    const alias = window.__lastAudio && window.__lastAudio.alias;
    if (!alias) throw err;
    raw = await (await fetch(alias, { cache: 'no-store' })).arrayBuffer();
  }
  const SR = 48000, CH = 2;
  const actx = new AudioContext({ sampleRate: SR });
  let decoded;
  try {
    decoded = await actx.decodeAudioData(raw);
  } finally {
    actx.close();
  }

  const { Track } = await import('./mp4.js');
  const track = new Track('audio', SR, 2);
  track.channels = CH;
  track.sampleRate = SR;

  const left = decoded.getChannelData(0);
  const right = decoded.numberOfChannels > 1 ? decoded.getChannelData(1) : left;
  const frames = decoded.length;
  const pcm = new Float32Array(frames * CH);
  for (let i = 0; i < frames; i++) { pcm[i * 2] = left[i]; pcm[i * 2 + 1] = right[i]; }

  let error = null;
  const BLOCK = 1024;                 // AAC-LC frame size; also the per-chunk fallback below
  let prevTs = null;
  const enc = new AudioEncoder({
    output: (chunk, meta) => {
      const desc = meta && meta.decoderConfig && meta.decoderConfig.description;
      if (desc && !track.description) track.description = new Uint8Array(desc);
      const data = new Uint8Array(chunk.byteLength);
      chunk.copyTo(data);
      // Audio uses the sample rate as its timebase, so a duration is a FRAME COUNT.
      //
      // `chunk.numberOfFrames` is an OPTIONAL EncodedAudioChunk attribute and Chrome's AAC
      // encoder does not populate it — it arrives as 0. Trusting it wrote an `stts` with
      // delta 0 for every one of the ~22k audio samples, which zeroed the track's mdhd/tkhd
      // duration and told players that all audio sits at t=0: the exported file played with
      // the audio sped up. Derive the count from the chunk timestamps instead, and fall back
      // to the AAC frame size for the first chunk and for a last one with no successor.
      let dur = chunk.numberOfFrames;
      if (!Number.isFinite(dur) || dur <= 0) {
        dur = (prevTs === null) ? BLOCK : Math.round((chunk.timestamp - prevTs) / 1e6 * SR);
        if (!Number.isFinite(dur) || dur <= 0) dur = BLOCK;
      }
      prevTs = chunk.timestamp;
      track.add(data, dur);
    },
    error: (e) => { error = error || e; },
  });
  enc.configure({ codec: 'mp4a.40.2', sampleRate: SR, numberOfChannels: CH, bitrate: 192000 });

  for (let off = 0; off < frames; off += BLOCK) {
    if (isCancelled() || error) break;
    const n = Math.min(BLOCK, frames - off);
    const data = new AudioData({
      format: 'f32', sampleRate: SR, numberOfFrames: n, numberOfChannels: CH,
      timestamp: Math.round((off / SR) * 1e6),
      data: pcm.slice(off * CH, (off + n) * CH),
    });
    enc.encode(data);
    data.close();
    if (enc.encodeQueueSize > 40) await new Promise((r) => setTimeout(r, 0));
    if ((off / BLOCK) % 200 === 0) {
      onProgress(Math.round(off / frames * 100));
      await new Promise((r) => setTimeout(r, 0));
    }
  }
  await enc.flush();
  enc.close();
  if (error) throw error;
  return track.description ? track : null;
}

async function exportWebCodecs(jobId, total, onProgress, isCancelled) {
  // No job id means a human clicked 导出: encode here and mux in the page, because there
  // is no server round trip to hand the samples to. A job id means AstrBot asked, and the
  // samples are streamed to the service which muxes them with ffmpeg.
  const local = !jobId;
  // Encode at the size the job asked for, not at the canvas size then downscaled: the
  // drawImage below is a GPU blit, whereas encoding 1080p and rescaling later costs a
  // second full encode and throws away quality.
  const outW = Math.max(2, window.__webglOutW || canvas.width);
  const outH = Math.max(2, window.__webglOutH || canvas.height);
  // The rate is chosen by whoever asked for the render: the service sets
  // `window.__webglBitrate` (bits per second) from the request's `bitrate_kbps`. A human
  // clicking 导出 sets nothing and keeps MANUAL_BITRATE. `bySize` is the delivery backstop
  // — see both constants above.
  const durationS = Math.max(1, total / WC_FPS);
  const bySize = local ? Infinity
    : Math.floor(BOT_MAX_BYTES * 8 / durationS) - MUX_AUDIO_BPS;
  const bitrate = Math.max(150_000,
    Math.min(window.__webglBitrate || MANUAL_BITRATE, bySize));
  const composite = document.createElement('canvas');
  composite.width = outW;
  composite.height = outH;
  const cctx = composite.getContext('2d');
  const url = jobId ? `${API}/webgl-stream/${encodeURIComponent(jobId)}` : null;

  let error = null;
  let localTrack = null;
  let batch = [];
  let batchFrames = 0;
  let posted = Promise.resolve();
  // Bytes the service has confirmed it holds. Every POST states the offset it is writing
  // at, which is what lets a failed upload be retried: the service can tell a fresh batch
  // from a repeat of one whose reply was lost, and re-sending blindly would append the
  // same bytes twice and corrupt the stream. Measured: one upload in ~250 was lost
  // mid-flight (the render died at 49% with `Failed to fetch`), so this is not theoretical
  // -- without it a multi-minute chart is very likely to fail somewhere along the way.
  let sentBytes = 0;

  if (local) {
    const { Track } = await import('./mp4.js');
    // Timebase must divide the frame duration exactly. With a 1/1000 s timebase each
    // 16666 us frame has to be rounded to 17 ms, and 1000/17 is 58.8 fps — the file then
    // claims to last longer than the chart and plays slightly slow. WC_FPS * 1000 makes
    // one frame exactly 1000 ticks.
    localTrack = new Track('video', WC_FPS * 1000, 1);
    localTrack.width = outW;
    localTrack.height = outH;
  }

  // Four tries, backing off 0.2/0.4/0.6 s. The service answers with the offset it holds,
  // and that answer -- not our own arithmetic -- is what we send next, so the two can
  // never drift apart.
  const postBatch = async (blob) => {
    let lastErr = null;
    for (let attempt = 0; attempt < 4; attempt++) {
      try {
        const r = await fetch(`${url}?offset=${sentBytes}`, { method: 'POST', body: blob });
        if (!r.ok) throw new Error(`上传失败 HTTP ${r.status}`);
        const j = await r.json();
        if (typeof j.offset === 'number') sentBytes = j.offset;
        return;
      } catch (e) {
        lastErr = e;
        if (attempt < 3) await new Promise((res) => setTimeout(res, 200 * (attempt + 1)));
      }
    }
    throw lastErr;
  };

  const flushBatch = () => {
    if (!batch.length) return;
    const blob = new Blob(batch, { type: 'application/octet-stream' });
    batch = [];
    batchFrames = 0;
    posted = posted
      .then(() => postBatch(blob))
      .catch((e) => { error = error || e; });
  };

  const encoder = new VideoEncoder({
    output: (chunk, meta) => {
      const bytes = new Uint8Array(chunk.byteLength);
      chunk.copyTo(bytes);
      if (local) {
        // MP4 needs AVCC (length-prefixed) samples plus the avcC record, not Annex-B.
        const desc = meta && meta.decoderConfig && meta.decoderConfig.description;
        if (desc && !localTrack.description) localTrack.description = new Uint8Array(desc);
        // One frame is exactly `1000` ticks at a WC_FPS*1000 timebase — no rounding.
        localTrack.add(bytes, 1000, chunk.type === 'key');
        return;
      }
      batch.push(bytes);
      if (++batchFrames >= 120) flushBatch();      // ~2s of video per request
    },
    error: (e) => { error = error || e; },
  });
  // ── rate control ──────────────────────────────────────────────────────────
  // `bitrate` alone is NOT a reliable size control: WebCodecs' default is
  // `bitrateMode: 'variable'`, which lets the encoder trade the target away for quality on
  // busy content. Measured on this machine, same chart, same requested 2000 kbps:
  //
  //   R Skin -> 2,221,891 bps (111% of the request)  -> 24.4 MB for an 86 s chart
  //   boj    -> 4,778,831 bps (239% of the request)  -> 50.2 MB for the same chart
  //
  // and the boj figure reproduced to the bit across three runs, so it is content-driven,
  // not noise. Extrapolated, a 4-minute boj chart is ~146 MB — past the delivery ceiling
  // this path exists to stay under. `bitrateMode: 'constant'` asks for CBR, which enforces
  // the target instead of treating it as a suggestion.
  //
  // Only the BOT path needs it; that is the one with a hard upload ceiling. The manual path
  // keeps the browser's default so a human's local export is unchanged, and the support
  // check means a browser without CBR quietly keeps VBR rather than failing the export.
  let encCfg = {
    codec: 'avc1.640028',
    width: outW,
    height: outH,
    bitrate,
    framerate: WC_FPS,
    // ffmpeg reads a raw Annex-B elementary stream; the in-page muxer needs AVCC.
    ...(local ? {} : { avc: { format: 'annexb' } }),
  };
  if (!local) {
    try {
      const cbr = await VideoEncoder.isConfigSupported({ ...encCfg, bitrateMode: 'constant' });
      if (cbr && cbr.supported) encCfg = cbr.config;
    } catch (e) {
      // No CBR on this build: keep the variable-rate config rather than losing the export.
    }
  }
  encoder.configure(encCfg);

  for (let f = 0; f < total; f++) {
    if (isCancelled() || error) break;
    const t = f * 1000 / WC_FPS;                   // chart time — our choice, not the clock
    drawFrame(t);
    cctx.drawImage(canvas, 0, 0, outW, outH);
    cctx.drawImage(hudCanvas, 0, 0, outW, outH);
    const frame = new VideoFrame(composite, {
      timestamp: Math.round(t * 1000),
      duration: Math.round(1e6 / WC_FPS),
    });
    encoder.encode(frame, { keyFrame: f % 120 === 0 });
    frame.close();
    // Let the encoder drain instead of queueing two hours of frames.
    if (encoder.encodeQueueSize > 24) await new Promise((r) => setTimeout(r, 0));
    if (f % 30 === 0) {
      // The local path still has the audio pass to do, so video is 0..80% of the work.
      onProgress(Math.round((local ? 0.8 : 1) * f / total * 100));
      await new Promise((r) => setTimeout(r, 0));
    }
  }
  await encoder.flush();
  encoder.close();
  if (error) throw error;

  if (local) {
    if (!localTrack.description || !localTrack.samples.length) {
      throw new Error('编码器没有产出可用样本');
    }
    let audioTrack = null;
    try {
      onProgress(82);
      audioTrack = await encodeBeatmapAudio(
        (pct) => onProgress(82 + Math.round(pct * 0.15)), isCancelled);
    } catch (e) {
      // A silent video still beats no video — but say so rather than pretending.
      info.textContent = '音频编码失败，导出无声视频: ' + e.message;
      audioTrack = null;
    }
    onProgress(97);
    const { Mp4Muxer } = await import('./mp4.js');
    const blob = new Mp4Muxer([localTrack, audioTrack]).build();
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `${beatmap.title}_${beatmap.version}.mp4`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 60000);
    onProgress(100);
    return;
  }

  flushBatch();
  await posted;
  // The offset goes with the closing request too, so a batch that never arrived fails the
  // export HERE with a clear message instead of silently muxing a stream with a hole in it.
  const fin = await fetch(`${url}?done=1&offset=${sentBytes}`, { method: 'POST' });
  if (!fin.ok) {
    const detail = await fin.json().catch(() => ({}));
    throw new Error(`结束上传失败 HTTP ${fin.status} ${detail.error || ''}`.trim());
  }
  onProgress(100);
}

let exportAbort = null;

$('btnExport').addEventListener('click', async () => {
  if (!beatmap) return;
  if (exportAbort) { exportAbort(); return; }        // second click cancels

  const btn = $('btnExport');
  const durationMs = Math.max(1, beatmap.duration || (audio.duration ? audio.duration * 1000 : 1));
  const chunks = [];
  let rec = null;
  let poll = 0;
  let finished = false;
  let cancelled = false;

  const cleanup = () => {
    clearInterval(poll);
    document.body.classList.remove('noinfo');
    btn.textContent = '导出';
    exportAbort = null;
    if (hasAudio) audio.onended = null;
    pausePlayback();
  };

  const stop = (aborted) => {
    if (finished) return;
    finished = true;
    cancelled = !!aborted;
    try { rec.stop(); } catch { cleanup(); }
  };

  document.body.classList.add('noinfo');   // keep the status line out of the recording
  btn.textContent = '导出中… 0%';

  // WebCodecs whenever the browser has it: it is several times faster than MediaRecorder,
  // produces a true 60fps, and is the only path that can carry audio. A job id (set by the
  // headless driver) means "hand the samples to the service"; its absence means a human
  // clicked the button, so the samples are muxed and downloaded here. MediaRecorder
  // remains only for browsers without VideoEncoder.
  if (typeof VideoEncoder !== 'undefined') {
    exportAbort = () => stop(true);
    try {
      pausePlayback();
      seekTo(0);
      await exportWebCodecs(
        window.__webglJobId || null,
        Math.max(1, Math.ceil(durationMs / 1000 * 60)),
        (pct) => { btn.textContent = `导出中… ${pct}%`; },
        () => cancelled,
      );
    } catch (e) {
      info.textContent = '导出失败: ' + e.message;
    }
    cleanup();
    return;
  }

  try {
    // QQ (and most chat clients) will not accept a .webm as a video, so record MP4/H.264
    // when the engine offers it — Chrome 126+ does, and it removes the need for ffmpeg on
    // the server entirely. Falls back to VP9 webm where `video/mp4;codecs=avc1` is absent.
    const MP4 = 'video/mp4;codecs=avc1.42E01E';
    const WEBM = 'video/webm;codecs=vp9';
    const useMp4 = typeof MediaRecorder !== 'undefined' && MediaRecorder.isTypeSupported(MP4);
    const mimeType = useMp4 ? MP4 : WEBM;
    const ext = useMp4 ? 'mp4' : 'webm';

    // The playfield is a WebGL canvas and the HUD (combo, title, BPM, accuracy, progress,
    // CPS) is a separate 2D canvas stacked on top of it. Capturing `canvas` alone therefore
    // recorded a HUD-less video — the page looked right and the export did not, which is
    // exactly the kind of difference nobody notices until the file is in front of them.
    // Pump both onto one composite and record that instead.
    const composite = document.createElement('canvas');
    composite.width = canvas.width;
    composite.height = canvas.height;
    const compositeCtx = composite.getContext('2d');
    let pumpId = 0;
    const pump = () => {
      compositeCtx.drawImage(canvas, 0, 0);
      compositeCtx.drawImage(hudCanvas, 0, 0);
      pumpId = requestAnimationFrame(pump);
    };
    pump();

    const stream = composite.captureStream(60);
    rec = new MediaRecorder(stream, { mimeType, videoBitsPerSecond: 8_000_000 });
    rec.ondataavailable = (e) => { if (e.data && e.data.size) chunks.push(e.data); };
    rec.onstop = () => {
      cancelAnimationFrame(pumpId);
      // A cancelled export throws its partial recording away — saving a 3-second fragment
      // just leaves junk in the downloads folder.
      if (!cancelled && chunks.length) {
        const blob = new Blob(chunks, { type: mimeType });
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `${beatmap.title}_${beatmap.version}.${ext}`;
        a.click();
        setTimeout(() => URL.revokeObjectURL(a.href), 10000);
      }
      cleanup();
    };
    exportAbort = () => stop(true);

    // Start from a known state. `startPlayback()` returns early when already playing, so
    // hitting 导出 during playback used to keep the old render clock while the audio
    // restarted at 0 — picture and sound diverged for the whole recording.
    pausePlayback();
    seekTo(0);
    rec.start();
    startPlayback();

    poll = setInterval(() => {
      const ms = currentTimeMs();
      btn.textContent = `导出中… ${Math.min(99, Math.round(ms / durationMs * 100))}%`;
      if (ms >= durationMs) stop(false);
    }, 200);
    if (hasAudio) audio.onended = () => stop(false);   // backstop for a short track
  } catch (err) {
    info.textContent = '导出错误: ' + err.message;
    cleanup();
  }
});

// ── circular volume progress bar ──
function drawVolCircle() {
  const canvas = $('volCircle');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const w = canvas.width, h = canvas.height;
  const cx = w / 2, cy = h / 2, r = w / 2 - 4;
  const vol = audio.volume || 0;
  ctx.clearRect(0, 0, w, h);
  // background ring
  ctx.beginPath();
  ctx.arc(cx, cy, r, 0, Math.PI * 2);
  ctx.strokeStyle = '#2a2a3a';
  ctx.lineWidth = 5;
  ctx.stroke();
  // progress arc
  const start = -Math.PI / 2;
  const end = start + Math.PI * 2 * vol;
  ctx.beginPath();
  ctx.arc(cx, cy, r, start, end);
  ctx.strokeStyle = '#6c5ce7';
  ctx.lineWidth = 5;
  ctx.lineCap = 'round';
  ctx.stroke();
  // percentage text
  ctx.fillStyle = '#e0e0e8';
  ctx.font = 'bold 12px system-ui';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(Math.round(vol * 100) + '%', cx, cy);
}

// click on volume circle to set volume
$('volCircle').addEventListener('click', (e) => {
  const canvas = $('volCircle');
  const rect = canvas.getBoundingClientRect();
  const cx = rect.width / 2, cy = rect.height / 2;
  const dx = e.clientX - rect.left - cx;
  const dy = e.clientY - rect.top - cy;
  const dist = Math.sqrt(dx * dx + dy * dy);
  if (dist < 8) return; // centre click — ignore
  // angle from top, clockwise
  let angle = Math.atan2(dx, -dy);
  if (angle < 0) angle += Math.PI * 2;
  const vol = Math.round((angle / (Math.PI * 2)) * 100) / 100;
  audio.volume = Math.max(0, Math.min(1, vol));
  drawVolCircle();
});

// init volume circle
drawVolCircle();

// ── init ──
function checkReady() {
  const ready = !!beatmap;
  $('btnPlay').disabled = !ready;
  $('btnReset').disabled = !ready;
  $('btnExport').disabled = !ready;
  if (ready) {
    if (!renderer) renderer = new Renderer(canvas);
    if (!ini) ini = parseSkinIni('');
    applyIni();
    drawFrame(0);
  }
}

loadSkinList();

// ── debug hook ───────────────────────────────────────────────────────────────
// Exposes the resolved geometry/skin state so the verification harness can assert
// on what the renderer actually decided, rather than guessing from pixels.
window.__mania = {
  // The WebCodecs export drives rendering itself instead of letting the wall clock do it,
  // so the frame renderer has to be reachable from outside.
  drawFrame,
  /** Column layout + the divider rects the current skin asks for. */
  columns() {
    if (!geometry || !block) return null;
    const g = geometry, lineW = block.columnLineWidth || [];
    const rightEdge = g.colX[g.keys - 1] + g.colW[g.keys - 1];
    const lines = [];
    for (let k = 0; k <= g.keys; k++) {
      const raw = lineW[k] || 0;
      if (raw <= 0) continue;
      const lw = raw * g.texScale * COLUMN_LINE_SCALE_X;
      lines.push({ boundary: k, raw, x: +((k === g.keys) ? rightEdge - lw : g.colX[k]).toFixed(2), w: +lw.toFixed(2) });
    }
    return {
      keys: g.keys, colX: g.colX.map(v => +v.toFixed(2)), colW: +g.colW[0].toFixed(2),
      gaps: g.colX.slice(1).map((x, i) => +(x - (g.colX[i] + g.colW[i])).toFixed(2)),
      columnLineWidth: lineW.slice(), columnSpacing: (block.columnSpacing || []).slice(),
      colourColumnLine: block.colourColumnLine, lines, hitY: +g.hitY.toFixed(1),
      /** Per-column lane fill resolved from the skin's `Colour{n}` (null override = follow skin). */
      columnBackgrounds: g.colX.map((_, i) => columnBackground(i)),
      columnBackgroundOverride: COLUMN_BACKGROUND_OVERRIDE,
    };
  },
  /** Resolved stage-light sprite + the geometry the light is drawn with. */
  stageLight() {
    if (!geometry || !block) return null;
    const tex = getTex(block.stageLight) || getTex('mania-stage-light');
    return {
      name: block.stageLight || 'mania-stage-light',
      sprite: tex ? { w: tex.width, h: tex.height } : null,
      lightPosition: block.lightPosition,
      bottom: VIEW_H - (block.lightPosition ?? 67) * geometry.scale,
      heightView: tex ? Math.min(tex.height, 768) * geometry.texScale : null,
      columnLineWidth: block.columnLineWidth,
    };
  },
  /** Last hit-burst quad drawn, plus the skin values that place it. */
  burstRect() {
    return {
      rect: lastBurstRect,
      hasBeatmap: !!beatmap, hasReplay: !!replay, replayPresses: replay ? replay.presses.length : 0,
      scorePosition: block ? block.scorePosition : null,
      hitPosition: block ? block.hitPosition : null,
      scale: geometry ? geometry.scale : null, hitY: geometry ? geometry.hitY : null,
      texScale: TEX_SCALE,
      expectedCentreY: block && geometry ? (block.scorePosition ?? 300) * geometry.scale : null,
      laneFraction: HIT_BURST_LANE_FRACTION,
    };
  },
  /** Resolve a skin sprite name and report its size / average colour. */
  probeTex(name) {
    const img = getTex(name);
    if (!img) return { name, found: false };
    const c = document.createElement('canvas');
    c.width = img.width; c.height = img.height;
    const cx = c.getContext('2d');
    cx.drawImage(img, 0, 0);
    const d = cx.getImageData(0, 0, img.width, img.height).data;
    let r = 0, g = 0, b = 0, a = 0, n = 0;
    for (let i = 0; i < d.length; i += 4) {
      if (d[i + 3] > 8) { r += d[i]; g += d[i + 1]; b += d[i + 2]; a += d[i + 3]; n++; }
    }
    return {
      name, found: true, w: img.width, h: img.height,
      avg: n ? [Math.round(r / n), Math.round(g / n), Math.round(b / n), Math.round(a / n)] : null,
      blank: isBlankSprite(img),
    };
  },
  /** Debug: hold notes covering `ms`, and the one whose tail lands nearest `ms`. */
  holdsAt(ms) {
    if (!beatmap) return { covering: [], nearestTail: null };
    const covering = beatmap.hitObjects
      .filter(h => h.isHold && h.time <= ms && ms <= h.endTime)
      .map(h => ({ col: h.column, t1: h.time, t2: h.endTime }));
    let nearestTail = null;
    for (const h of beatmap.hitObjects) {
      if (!h.isHold) continue;
      const d = Math.abs(h.endTime - ms);
      if (!nearestTail || d < nearestTail.d) nearestTail = { d, col: h.column, t1: h.time, t2: h.endTime };
    }
    return { covering, nearestTail, nowMs: ms };
  },
  get state() {
    return {
      keys: beatmap ? beatmap.keys : null,
      title: beatmap ? `${beatmap.title} [${beatmap.version}]` : null,
      durationMs: beatmap ? (beatmap.duration || 0) : null,
      sid: beatmap ? (beatmap.beatmapSetID || 0) : null,
      scrollSpeed,
      timeRange: geometry ? +geometry.timeRange.toFixed(2) : null,
      hitY: geometry ? +geometry.hitY.toFixed(1) : null,
      stageLeft: geometry ? +geometry.stageLeft.toFixed(1) : null,
      stageRight: geometry ? +geometry.stageRight.toFixed(1) : null,
      colX: geometry ? geometry.colX.map(v => +v.toFixed(1)) : null,
      colW: geometry ? geometry.colW.map(v => +v.toFixed(1)) : null,
      declaredKeys: ini ? ini.declaredKeys : null,
      blockKeys: block ? block.keys : null,
      noteImages: block ? [0, 1, 2, 3].map(c => block.noteImages[c] ?? null) : null,
      noteImagesT: block ? [0, 1, 2, 3].map(c => block.noteImagesT[c] ?? null) : null,
      hitSprites: block ? { ...block.hitSprites } : null,
      widthForNoteHeight: block ? block.widthForNoteHeight : null,
      noteBodyStyle: block ? block.noteBodyStyle : null,
      judgementLine: block ? block.judgementLine : null,
      stageHint: block ? block.stageHint : null,
      textures: skin ? skin.textures.size : 0,
      maxTextureSize: renderer ? renderer.maxTex : null,
      replayPresses: replay ? replay.presses.length : 0,
    };
  },
};
