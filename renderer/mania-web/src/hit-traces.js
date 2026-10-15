// Mania-Replay-Master judgement colours, independent of the selected skin.
export const HIT_COLOURS = {
  perfect: [255,255,255], great: [255,210,55], good: [121,208,32],
  ok: [30,104,197], meh: [225,52,155], miss: [255,0,0],
};

// Shared by skin notes and the overlay: successfully matched taps disappear at
// their note time; LN graphics end with the chart tail. Missed taps fall briefly.
export function noteHasEnded(note, nowMs, matched = false) {
  if (note.isHold) return nowMs >= note.endTime;
  return matched ? nowMs >= note.time : nowMs > note.time+150;
}

// Preserve raw presses (including empty presses). Counts and the playback clock
// remain owned by the existing matcher/player; this is only a display index.
export function buildHitTraces(match, replay, keys) {
  if (!match || !replay) return [];
  const heads = new Map();
  const tails = new Map();
  for (const j of match.judgements) {
    if (j.kind === 'head') heads.set(`${j.col}:${j.objTime}`, j);
    if (j.kind === 'tail') tails.set(`${j.col}:${j.objTime}`, j);
  }
  const presses = new Map();
  for (const o of match.objs) {
    if (!o.matched) continue;
    const j = heads.get(`${o.col}:${o.time}`);
    const actual = o.time + o.error;
    const key = `${o.col}:${actual}`;
    if (!presses.has(key)) presses.set(key, []);
    presses.get(key).push({objTime:o.time, result:j?.result || 'miss',
      isHold:o.isHold, endTime:o.endTime});
  }
  const releases = Array.from({length:keys}, () => []);
  for (const r of replay.releases || []) releases[r.key % keys]?.push(r.time);
  for (const list of releases) list.sort((a,b)=>a-b);
  const traces = replay.presses.map(p => {
    const col = p.key % keys;
    const matched = presses.get(`${col}:${p.time}`)?.shift();
    return {col, kind:'head', time:p.time, objTime:matched?.objTime ?? p.time,
      isHold:!!matched?.isHold, endTime:matched?.endTime,
      result:matched?.result || 'miss', matched:!!matched};
  }).sort((a,b) => a.time-b.time);
  const nextPress = new Array(keys).fill(Infinity);
  for (let i=traces.length-1;i>=0;i--) {
    const t=traces[i];
    if (t.isHold) {
      // Do not attach a later key cycle's release to an earlier interrupted hold.
      t.releaseTime = releases[t.col].find(r=>r>=t.time && r<nextPress[t.col]) ?? null;
      t.holdUntil = t.releaseTime ?? nextPress[t.col];
    }
    nextPress[t.col]=t.time;
  }
  const tailTraces = [];
  for (const t of traces) {
    if (!t.isHold || t.releaseTime === null) continue;
    const tail = tails.get(`${t.col}:${t.endTime}`);
    // Malody has no separate release judgement. Keep its recorded head colour;
    // osu uses its existing tail judgement (Stable already folds it into the head).
    tailTraces.push({col:t.col, kind:'tail', time:t.releaseTime, objTime:t.endTime,
      endTime:t.endTime, noteTime:t.objTime, noteIsHold:true,
      result:tail?.result || t.result, matched:true});
  }
  return [...traces,...tailTraces].sort((a,b)=>a.time-b.time);
}

export function hitTraceRects(traces, g, nowMs, height = 1080) {
  if (!g || !(g.timeRange > 0)) return [];
  const yAt = t => g.hitY - (t-nowMs)/g.timeRange*g.hitY;
  const rects = [];
  const thick = Math.max(2, 2*g.scale);
  const floor = Math.min(height,g.hitY);
  for (const t of traces) {
    if (t.col < 0 || t.col >= g.keys) continue;
    const note = {time:t.noteTime ?? t.objTime,
      isHold:t.noteIsHold || t.isHold, endTime:t.endTime};
    if (noteHasEnded(note,nowMs,true)) continue;
    const y = yAt(t.time), noteY = yAt(t.objTime);
    const width = g.colW[t.col]*0.5;
    const x = g.colX[t.col]+g.colW[t.col]/2;
    const rgb = (HIT_COLOURS[t.result] || HIT_COLOURS.miss).map(v=>v/255);
    if (t.isHold) {
      const active = nowMs>=t.time && nowMs<t.holdUntil;
      const endY = Number.isFinite(t.holdUntil) ? yAt(t.holdUntil) : 0;
      const startY = active ? g.hitY : y;
      const top = Math.max(0,Math.min(startY,endY));
      const bottom = Math.min(floor,Math.max(startY,endY));
      if (bottom>top) rects.push({part:'hold', col:t.col, rgb,
        x:x-thick/2,y:top,w:thick,h:bottom-top});
      if (active) rects.push({part:'held',col:t.col,rgb,
        x:x-width/2,y:floor-thick,w:width,h:thick});
    }
    // The LN head is consumed; only its remaining body/held indicator survives.
    if (t.isHold && nowMs>=t.objTime) continue;
    if (Math.max(y,noteY) < 0 || Math.min(y,noteY) > floor) continue;
    // LN tails always form an upright T. Put its bar at the upper timing
    // endpoint and connect downwards, retaining both timing coordinates.
    // A zero-error press still has a short stem so the mark remains a T.
    const barY = t.kind==='tail' ? Math.min(y,noteY) : y;
    const end = t.kind==='tail' ? barY+Math.max(thick*2,Math.abs(noteY-y))
      : Math.abs(noteY-y) < thick*2 ? y+thick*2 : noteY;
    const top = Math.max(0,Math.min(barY,end)), bottom = Math.min(floor,Math.max(barY,end));
    if (bottom > top) rects.push({part:'stem', kind:t.kind, col:t.col, rgb,
      x:x-thick/2, y:top, w:thick, h:bottom-top});
    const capTop = Math.max(0,barY-thick/2), capBottom = Math.min(floor,barY+thick/2);
    if (capBottom > capTop) rects.push({part:'cap', kind:t.kind, col:t.col, rgb,
      x:x-width/2, y:capTop, w:width, h:capBottom-capTop});
  }
  return rects;
}
