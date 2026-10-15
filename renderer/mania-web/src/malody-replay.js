// Malody 4.x PC windows and head-only matching follow Mania-Replay-Master.
export function matchMalodyReplay(beatmap, replay) {
  const [best, cool, good, miss] = replay.windows;
  const windows = { perfect: best, great: cool, good, ok: good, meh: miss, miss };
  const objs = beatmap.hitObjects.map(h => ({ time: h.time, endTime: h.isHold ? h.endTime : h.time,
    col: h.column, isHold: h.isHold, matched: false, error: 0 })).sort((a,b) => a.time-b.time);
  const judgements = [], comboTrail = [];
  for (let col = 0; col < beatmap.keys; col++) {
    const notes = objs.filter(o => o.col === col);
    let next = 0;
    const addMiss = o => judgements.push({ time: o.time+miss, objTime:o.time, kind:'head',
      col, result:'miss', offset:0, byPress:false });
    for (const press of replay.presses.filter(p => p.key === col)) {
      while (next < notes.length && press.time > notes[next].time+miss) addMiss(notes[next++]);
      if (next >= notes.length || press.time < notes[next].time-miss) continue;
      const o = notes[next++], offset = press.time-o.time, delta = Math.abs(offset);
      const result = delta <= best ? 'perfect' : delta <= cool ? 'great' : delta <= good ? 'good' : 'miss';
      o.matched = true; o.error = offset; press.hold = o.isHold;
      judgements.push({ time:press.time, objTime:o.time, kind:'head', col, result, offset, byPress:true });
    }
    while (next < notes.length) addMiss(notes[next++]);
  }
  judgements.sort((a,b) => a.time-b.time);
  if (replay.recordedJudgements) {
    // MRV stores the game's own results and combo at each timestamp. Use those
    // snapshots instead of deriving V judgements from the older 4.x windows.
    const columns = Array.from({length:beatmap.keys}, (_,col) => objs.filter(o=>o.col===col));
    const cursors = new Array(beatmap.keys).fill(0);
    const recorded = replay.recordedJudgements.map(j => {
      let nearest = null;
      const notes = columns[j.key] || [];
      let cursor = cursors[j.key] || 0;
      if (Number.isFinite(j.obj_time)) {
        while (cursor<notes.length && notes[cursor].time<j.obj_time) cursor++;
        if (cursor<notes.length && notes[cursor].time===j.obj_time) nearest=notes[cursor++];
      } else {
        while (cursor<notes.length && notes[cursor].time<j.time-miss) cursor++;
        if (cursor<notes.length && notes[cursor].time<=j.time+miss) nearest=notes[cursor++];
      }
      cursors[j.key]=cursor;
      if (nearest) {nearest.matched=j.result!=='miss';nearest.error=j.time-nearest.time;}
      return {time:j.time, objTime:nearest?.time ?? j.time, kind:'head', col:j.key, result:j.result,
        offset:nearest ? j.time-nearest.time : 0, byPress:!!nearest && j.result!=='miss'};
    });
    return {objs, presses:replay.presses, comboTrail:replay.recordedJudgements.map(j=>({time:j.time,combo:j.combo})),
      judgements:recorded, windows};
  }
  let combo = 0;
  for (const j of judgements) {
    combo = j.result === 'miss' ? 0 : combo+1;
    comboTrail.push({time:j.time, combo});
  }
  return { objs, presses: replay.presses, comboTrail, judgements, windows };
}
