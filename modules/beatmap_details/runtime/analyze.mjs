import {readFile, writeFile} from 'node:fs/promises';
import {runAnalysisPipeline} from '../upstream/ManiaMapAnalyser by Leo_Black/js/pipeline/runAnalysisPipeline.js';
import {OsuFileParser} from '../upstream/ManiaMapAnalyser by Leo_Black/js/parser/osuFileParser.js';
import {calculateReworkPp} from '../upstream/ManiaMapAnalyser by Leo_Black/js/rework/reworkPerformance.js';
import {classifyCompanellaDifficulty} from '../upstream/ManiaMapAnalyser by Leo_Black/js/estimator/companellaEstimator.js';
import {detectVibro, detectVibroFromMetadata} from '../upstream/ManiaMapAnalyser by Leo_Black/js/patterns/chartVibro.js';
import {APP_CONFIG} from '../upstream/ManiaMapAnalyser by Leo_Black/config.js';
import {patternAtRate} from './pattern_segments.mjs';

const [input, target, bid,rateText='1'] = process.argv.slice(2);
const speedRate=Number(rateText);
if (!Number.isFinite(speedRate)||speedRate<.1||speedRate>3) throw new Error('Invalid speed rate');
const rawText = await readFile(input, 'utf8');
const parser = new OsuFileParser(rawText); parser.process();
const parsed = parser.getParsedData();
if (!parsed.noteStarts.length) throw new Error('谱面没有可分析物件');
const options = {speedRate, classicMod:true, withGraph:true, withPpMetrics:true,
  forceSunnyWindow:true, enableAnalyzeLN:true, enableAlwaysShowLNDifficulty:true,
  display6kLevel:true, extendedEstimationRange:true, withPattern:true,
  withEtterna:true, withInterlude:true, etternaVersion:'0.72.3',companellaEtternaVersion:'0.74.0'};
const originalId=Number(parsed.metaData.BeatmapID);
const data={beatmapId:/^\d+$/.test(bid)?Number(bid):(originalId>0?originalId:null),sourceId:bid,
  conditions:{client:'Stable',mods:speedRate===1.5?['DT']:speedRate===.75?['HT']:[],...options},parsed,algorithms:{}};
for (const estimatorAlgorithm of ['Sunny','Daniel','Azusa','Roxy','Mixed','Companella']) {
  try { data.algorithms[estimatorAlgorithm]=await runAnalysisPipeline({rawText,estimatorAlgorithm,options}); }
  catch(error) {
    if (estimatorAlgorithm==='Sunny') throw error;
    data.algorithms[estimatorAlgorithm]={...data.algorithms.Sunny,actualEstimatorAlgorithm:'不可用',
      rework:{...data.algorithms.Sunny.rework,star:null,estDiff:String(error),numericDifficulty:null,graph:null}};
  }
}
const s=data.algorithms.Sunny;
// The upstream pattern adapter currently ignores its rate argument.
// Recompute the report from played-time rows so BPM-based categories follow the rate.
if(speedRate!==1){
  const report=patternAtRate(rawText,speedRate);
  for(const result of Object.values(data.algorithms))result.patternReport=report;
}
// Mirror the upstream UI's post-pipeline VIBRO label. The pipeline only
// returns star eligibility; the final decision uses 4K MSD 0.72.3 plus the
// metadata keyword check. Prefer Roxy's own eligibility when it ran, matching
// the Roxy difficulty view; fall back to Sunny when Roxy itself fell back.
const vibroEstimator=data.algorithms.Roxy?.actualEstimatorAlgorithm==='Roxy'
  ? data.algorithms.Roxy : s;
const vibroValues=vibroEstimator.ettResult?.values ?? s.ettResult?.values ?? null;
const vibroThreshold=APP_CONFIG.etterna.vibroJackspeedRatioThreshold;
const metadataVibro=detectVibroFromMetadata(parsed.metaData);
const msdEligible=Boolean(vibroEstimator.vibro?.eligible);
const msdVibro=msdEligible && detectVibro(vibroValues,vibroThreshold);
const jackSpeed=Number(vibroValues?.JackSpeed);
const overall=Number(vibroValues?.Overall);
data.vibroDetection={isVibroMap:metadataVibro||msdVibro,
  metadataVibro,msdVibro,msdEligible,msdVersion:'0.72.3',
  jackSpeedOverallRatio:Number.isFinite(jackSpeed)&&Number.isFinite(overall)&&overall>0
    ?jackSpeed/overall:null,
  threshold:vibroThreshold,estimator:vibroEstimator.actualEstimatorAlgorithm};
data.companella={estDiff:'不适用',numericDifficulty:null,confidence:null,danLabel:null,variant:null,rawModelOutput:null};
if(parsed.columnCount===4 && s.ettResult) {
  // The upstream UI uses its dedicated Companella MSD version when available.
  const companionMsd=data.algorithms.Companella?.companellaEttResult?.values ?? s.ettResult.values;
  try {data.companella=await classifyCompanellaDifficulty({msdValues:companionMsd,interludeStar:s.interludeStar,sunnyStar:s.rework.star});}
  catch(error){data.companella.estDiff=String(error);}
}
const m=s.ppMetrics;
data.maxReworkPp=m?calculateReworkPp({starRating:m.star,variety:m.variety,accScalar:m.accScalar,
  totalNotes:m.totalNotes,perfect:m.totalNotes,great:0,good:0,ok:0,meh:0,miss:0}):null;
// Non-applicable auxiliary metrics remain null; the template displays their status.
s.sunnyWindow ??= {star:null,lnRatio:parsed.lnRatio,columnCount:parsed.columnCount,lnStar:null,
  estDiff:'不适用',numericDifficulty:null,numericDifficultyHint:null,typePercentageData:[],graph:null};
s.patternReport ??= {Clusters:[],Category:'不可用',LNPercent:parsed.lnRatio,HBRowRatio:null,
  ModeTag:'不可用',SVAmount:null,Duration:Math.max(...parsed.noteStarts)-Math.min(...parsed.noteStarts)};
s.ettResult ??= {values:{},keycount:parsed.columnCount,lnRatio:parsed.lnRatio};
s.ppMetrics ??= {};
data.maxReworkPp ??= {};
if(speedRate!==1){
  // The display data uses played time; estimator input above stays unmodified.
  for(const key of ['noteStarts','noteEnds'])data.parsed[key]=data.parsed[key].map(t=>t/speedRate);
  for(const result of Object.values(data.algorithms)){
    if(result.rework?.graph?.times)result.rework.graph.times=result.rework.graph.times.map(t=>t/speedRate);
    if(result.sunnyWindow?.graph?.times)result.sunnyWindow.graph.times=result.sunnyWindow.graph.times.map(t=>t/speedRate);
  }
}
await writeFile(target,JSON.stringify(data));
