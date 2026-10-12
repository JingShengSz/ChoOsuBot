import { readFile, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { parseOsuManiaFromText } from '../upstream/ManiaMapAnalyser by Leo_Black/js/parser/patternOsuParser.js';
import { createChart } from '../upstream/ManiaMapAnalyser by Leo_Black/js/patterns/chart.js';
import { fromChart } from '../upstream/ManiaMapAnalyser by Leo_Black/js/patterns/summary.js';

/**
 * Classify consecutive time windows with the same upstream pattern engine used
 * for the whole chart. Windows are anchored at the first note, so they align
 * with the density histogram. A boundary belongs to the window on its right.
 */
export function chartAtRate(osuText, rate = 1) {
  if (!Number.isFinite(rate) || rate < .1 || rate > 3) throw new Error('Invalid speed rate');
  const chart = parseOsuManiaFromText(osuText);
  return createChart(chart.Keys,
    chart.Notes.map(row => ({...row,Time:row.Time/rate})),
    chart.BPM.map(item => ({...item,Time:item.Time/rate,Data:{...item.Data,MsPerBeat:item.Data.MsPerBeat/rate}})),
    chart.SV.map(item => ({...item,Time:item.Time/rate})));
}

export function patternAtRate(osuText, rate = 1) {
  const report=fromChart(chartAtRate(osuText,rate));
  return {...report,Clusters:report.Clusters.map(c=>({Pattern:c.Pattern,SpecificTypes:c.SpecificTypes,
    RatingMultiplier:c.RatingMultiplier,BPM:c.BPM,Mixed:c.Mixed,Amount:c.Amount}))};
}

export function classifyPatternSegments(osuText, seconds = 10, rate = 1) {
  if (!Number.isFinite(seconds) || seconds <= 0) throw new Error('seconds must be positive');
  const chart = chartAtRate(osuText,rate);
  const windowMs = Math.round(seconds * 1000);
  const firstMs = chart.FirstNote;
  const lastMs = chart.LastNote;
  const count = Math.floor((lastMs - firstMs) / windowMs) + 1;
  const segments = [];
  let cursor = 0;
  for (let index = 0; index < count; index += 1) {
    const startMs = firstMs + index * windowMs;
    const endMs = Math.min(firstMs + (index + 1) * windowMs, lastMs + 1);
    const rows = [];
    while (cursor < chart.Notes.length && chart.Notes[cursor].Time < endMs) {
      if (chart.Notes[cursor].Time >= startMs) rows.push(chart.Notes[cursor]);
      cursor += 1;
    }
    let report = null;
    if (rows.length >= 2) {
      try { report = fromChart(createChart(chart.Keys, rows, chart.BPM, chart.SV)); }
      catch { /* A sparse or malformed window has no reliable category. */ }
    }
    const top = report?.Clusters?.[0];
    segments.push({
      index, startMs, endMs, rowCount: rows.length,
      category: report?.Category ?? 'Uncategorised',
      modeTag: report?.ModeTag ?? null,
      topPattern: top?.Pattern ?? null,
      topSpecific: top?.SpecificTypes?.[0]?.[0] ?? null,
    });
  }
  return { seconds, rate, firstMs, lastMs, segments };
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  const [input, output, secondsText = '10', rateText = '1'] = process.argv.slice(2);
  if (!input || !output) throw new Error('Usage: node pattern_segments.mjs input.osu output.json [seconds]');
  const result = classifyPatternSegments(await readFile(input, 'utf8'), Number(secondsText),Number(rateText));
  await writeFile(output, JSON.stringify(result, null, 2), 'utf8');
  console.log(`${result.segments.length} windows of ${result.seconds}s`);
  for (const item of result.segments) {
    console.log(`${item.index.toString().padStart(2)} ${((item.startMs-result.firstMs)/1000).toFixed(0)}s ${item.category} (${item.rowCount} rows)`);
  }
}
