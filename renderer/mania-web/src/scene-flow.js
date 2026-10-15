export const INTRO_CYCLE_MS = 650;
export const RESULT_TRANSITION_MS = 650;
export const RESULT_HOLD_MS = 3000;
const ease = t => t*t*(3-2*t);

export function sceneTimeline(firstEntryMs, chartEndMs, rate=1) {
  const introEnd = firstEntryMs - 500*rate;
  const start = Math.min(0, introEnd - 2*INTRO_CYCLE_MS*rate);
  const resultStart = chartEndMs + 2000*rate;
  return {start, introEnd, chartEnd:chartEndMs, resultStart,
    resultEnd:resultStart+RESULT_TRANSITION_MS*rate,
    end:resultStart+(RESULT_TRANSITION_MS+RESULT_HOLD_MS)*rate,rate};
}

export function introArrow(nowMs, timeline) {
  const elapsed=(nowMs-timeline.start)/timeline.rate;
  if(elapsed<0||elapsed>=2*INTRO_CYCLE_MS||nowMs>=timeline.introEnd)return null;
  const p=(elapsed%INTRO_CYCLE_MS)/INTRO_CYCLE_MS;
  return {cycle:Math.floor(elapsed/INTRO_CYCLE_MS),offset:70*ease(p),alpha:1-ease(p)};
}

export function resultTransition(nowMs, timeline) {
  if(nowMs<timeline.resultStart)return 0;
  return ease(Math.min(1,(nowMs-timeline.resultStart)/(timeline.resultEnd-timeline.resultStart)));
}
