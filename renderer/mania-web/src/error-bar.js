import { HIT_COLOURS } from './hit-traces.js';
import {upperBound} from './frame-index.js';

export const ERROR_MARKER_LIFETIME = 5000;
export const ERROR_AVERAGE_EASE_MS = 180;
export const errorColour = result => `rgb(${(HIT_COLOURS[result] || HIT_COLOURS.miss).join(',')})`;

// Use the playback clock so pause, seeking and video export agree. The recent
// weighted mean ages out old offsets instead of freezing behind a song average.
export function errorBarState(traces, nowMs, extent, beamScale = 1) {
  const markers = [];
  let sum = 0, weight = 0;
  for (let i = upperBound(traces,nowMs) - 1; i >= 0; i--) {
    const hit = traces[i], age = nowMs - hit.time;
    if (age >= ERROR_MARKER_LIFETIME) break;
    if (age < 0 || !hit.matched || hit.kind !== 'head') continue;
    const offset = hit.time - hit.objTime;
    if (!Number.isFinite(offset)) continue;
    const fade = (1 - age / ERROR_MARKER_LIFETIME) ** 2;
    const position = Math.max(-1, Math.min(1, offset / extent));
    markers.push({position, colour:errorColour(hit.result), alpha:fade * .85,
      w:2 * beamScale, h:12 * beamScale, radius:beamScale});
    // Ease each new hit into the mean instead of snapping the arrow on key-down.
    // This is evaluated from chart time, independent of frame rate / draw order.
    const progress = Math.min(1, age / ERROR_AVERAGE_EASE_MS);
    const easedWeight = fade * progress * progress * (3 - 2 * progress);
    sum += offset * easedWeight;
    weight += easedWeight;
  }
  markers.reverse();
  return {markers, average:weight ? Math.max(-1, Math.min(1, sum / weight / extent))
    : markers.length ? markers.at(-1).position : null};
}
