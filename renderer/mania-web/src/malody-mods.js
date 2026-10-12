// Apply only settings verified for MRV. Its bitmask differs from 4.x MR.
export function applyMalodyMods(beatmap, replay) {
  if (replay.holdsToNotes) {
    for (const note of beatmap.hitObjects) {
      note.isHold = false;
      note.endTime = note.time;
    }
    beatmap.duration = beatmap.hitObjects.reduce((end, note) => Math.max(end, note.time), 0);
  }
  if (replay.constantScroll) {
    // The renderer places notes on the elapsed-time axis. BPM continues to
    // update the HUD, but inherited SV points do not alter their distance.
    beatmap.timings = beatmap.timings.filter(point => point.isRed);
  }
}
