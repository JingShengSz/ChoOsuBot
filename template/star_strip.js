/* =====================================================================
 * star_strip.js — 星级条生成器（零依赖）
 * ---------------------------------------------------------------------
 * 从 star-rating-painter.html 抽取，色阶与绘制逻辑一字未改。
 * 浏览器与 Node 均可运行。
 *
 * 用途：成绩图插件按每局的星级数值实时生成这条图形，再贴进模板。
 *
 * 用法：
 *   import { renderStarStrip } from './star_strip.js';
 *   const { svg, width, height } = renderStarStrip({ value: 7.32 });
 *
 *   // 或拿 SVG 字符串直接落盘 / 塞进 DOM
 *   document.body.innerHTML = svg;
 * ===================================================================== */

'use strict';

/* ------------------------------------------------------------ 色阶 --- */
/* 星星色阶：随难度升高逐渐压暗，但**压到可见下限就停住**。
 *
 * 旧版尾部一路压到 #040410 / #000000，结果是：
 *   未点亮的星是空的固定灰 #5A6684 @ 0.75 → 合成后相对亮度约 0.081
 *   而 8.3 星以上点亮的星比这个还暗（8.6★ = 0.077，9.6★ = 0.022，10.6★ = 0.005）
 * 也就是**点亮的星比没点亮的还暗**，玩家没法数亮了几颗。
 * 「更难 = 更暗」这条规则一旦越过空星亮度就自相矛盾，所以尾巴停在 ~0.12 亮度，
 * 再往下靠色相（蓝 → 紫）继续拉开区分度，不靠亮度。
 * 详见 RAMPS.md。 */
const STAR_RAMP = [
  [ 0.00, '#4fc3f7'], [ 2.00, '#7ed957'], [ 2.70, '#c9e83c'],
  [ 3.40, '#ffe94a'], [ 4.00, '#ff8c3c'], [ 4.70, '#ff4d6d'],
  [ 5.30, '#e040fb'], [ 6.50, '#7b8cff'], [ 7.60, '#6a6ae8'],
  [ 8.60, '#5b5be0'], [ 9.60, '#6250dc'], [10.60, '#6a45d8'],
  [12.00, '#7040d4'], [18.00, '#7a3ad0'],
];

/* 亮度下限自检：任何星星色都不能暗过未点亮的空星，否则计数会反直觉。
   改动上面那张表后跑 node tools/check_ramps.js 验证。 */
const STAR_RAMP_MIN_LUM = 0.11;

/* 数字色阶：与星星相反，越难越亮 */
const NUM_RAMP = [
  [ 0.00, '#4fc3f7'], [ 2.00, '#7ed957'], [ 3.40, '#ffe94a'],
  [ 4.70, '#ff4d6d'], [ 5.30, '#e040fb'], [ 6.50, '#ffcb2e'],
  [ 7.32, '#ffcb2e'], [ 8.20, '#ffb022'], [ 9.00, '#ffa022'],
  [ 9.50, '#ff8a20'], [ 9.90, '#f4792b'], [10.00, '#ff3b5c'],
  [10.50, '#ff3b8e'], [11.00, '#ff3bd0'], [11.70, '#e83bf5'],
  [12.00, '#c04df5'], [12.70, '#a855f7'], [13.30, '#8b5cf6'],
  [14.30, '#5b6bff'], [16.00, '#4a5cff'],
];

/* 旧版档位色（colorMode: 'tier' 用） */
const TIERS = [
  { key:'Easy',    label:'Easy',    lo:0.0, hi:2.0,      range:'0.0 – 1.99',    color:'#4fc3f7', accent:'#4fc3f7' },
  { key:'Normal',  label:'Normal',  lo:2.0, hi:2.7,      range:'2.0 – 2.69',    color:'#7ed957', accent:'#7ed957' },
  { key:'Hard',    label:'Hard',    lo:2.7, hi:4.0,      range:'2.7 – 3.99',    color:'#ffe94a', accent:'#ffe94a' },
  { key:'Insane',  label:'Insane',  lo:4.0, hi:5.3,      range:'4.0 – 5.29',    color:'#ff4d6d', accent:'#ff4d6d' },
  { key:'Expert',  label:'Expert',  lo:5.3, hi:6.5,      range:'5.3 – 6.49',    color:'#e040fb', accent:'#e040fb' },
  { key:'Expert+', label:'Expert+', lo:6.5, hi:Infinity, range:'6.5 and above', color:'#7b8cff', accent:'#ffcb2e' },
];

const FONT = 'Segoe UI, PingFang SC, Microsoft YaHei, Roboto, Helvetica, Arial, sans-serif';

/* ------------------------------------------------------- 默认参数 --- */
const DEFAULTS = {
  value:        7.32,
  scaleMax:     15,       // 量表上限
  starCount:    15,       // 星星总数
  starSize:     46,       // 单颗星直径(px)
  spacing:      1.24,     // 间距倍率
  colorMode:    'strict', // strict | starOnly | tier | fixed
  fixedColor:   '#6e6ef4',
  badgeBg:      '#2b3048',
  /* 未点亮的星用什么颜色。null = 沿用星星色（旧行为）。
     高分段星星色会压到近黑（10.6 星以上 #0b0b22），如果空星也用星星色，
     点亮与未点亮会一起沉进深色背景，读者数不出亮了几颗。所以默认改成固定灰。 */
  emptyColor:   '#5A6684',
  emptyOpacity: 0.75,
  /* 徽章里小星星的颜色。null = 跟右边那一排星星同色（默认）。
     数字仍然走 numColor（数字色阶），两者是分开的。 */
  badgeStarColor: null,
  /* 数字墨迹中心相对基线的偏移（em 比例），用来显式定位基线。
     不再依赖 dominant-baseline —— Photoshop 导入 SVG 时会忽略它，
     导致数字整体偏高（实测偏高 6.5px）。显式定位后 Chrome 与 PS 表现一致。 */
  capRatio: 0.66,
  /* 星形描边（修法 B）。'auto' = 只在星星本身偏暗时自动加亮边。
     背景是深色时，高分段星星会压到 #04040e，只比背景深一点点，
     描边让星形轮廓重新可见。低分段（星星本身够亮）不会加，视觉不变。 */
  starStroke:        'auto',   // 'auto' | null | '#rrggbb'
  starStrokeWidth:   1.5,
  starStrokeMinLum:  0.30,     // 星星亮度低于此值才自动加描边
  starStrokeWhiteMix: 0.55,    // 描边色 = mix(starColor, #ffffff, 这个比例)
  showBadge:    true,
  showTier:     true,
  fadeTail:     true,
  bg:           null,     // null = 透明底（贴进模板必须用这个）
  font:         FONT,
};

/* --------------------------------------------------------- 工具 --- */
const clamp = (v,a,b) => v < a ? a : (v > b ? b : v);

function hexToRgb(h){
  h = String(h).replace('#','');
  if (h.length === 3) h = h[0]+h[0]+h[1]+h[1]+h[2]+h[2];
  const n = parseInt(h, 16);
  return [(n>>16)&255, (n>>8)&255, n&255];
}
function rgbToHex(r,g,b){
  const t = v => clamp(Math.round(v),0,255).toString(16).padStart(2,'0');
  return '#' + t(r) + t(g) + t(b);
}
function rampColor(ramp, v){
  if (v <= ramp[0][0]) return ramp[0][1];
  const last = ramp[ramp.length-1];
  if (v >= last[0]) return last[1];
  for (let i=0;i<ramp.length-1;i++){
    const [v0,c0] = ramp[i], [v1,c1] = ramp[i+1];
    if (v >= v0 && v <= v1){
      const t = (v1 === v0) ? 0 : (v - v0)/(v1 - v0);
      const a = hexToRgb(c0), b = hexToRgb(c1);
      return rgbToHex(a[0]+(b[0]-a[0])*t, a[1]+(b[1]-a[1])*t, a[2]+(b[2]-a[2])*t);
    }
  }
  return last[1];
}
function tierOf(v){
  for (const t of TIERS) if (v >= t.lo && v < t.hi) return t;
  return TIERS[TIERS.length-1];
}
function luminance(hex){
  const [r,g,b] = hexToRgb(hex);
  return (0.2126*r + 0.7152*g + 0.0722*b) / 255;
}
function mix(hex, target, amt){
  const a = hexToRgb(hex), b = hexToRgb(target);
  return rgbToHex(a[0]+(b[0]-a[0])*amt, a[1]+(b[1]-a[1])*amt, a[2]+(b[2]-a[2])*amt);
}
function escapeXml(s){
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
                  .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}
function starPath(cx, cy, R, r){
  let d = '';
  for (let i=0;i<10;i++){
    const rad = (i % 2 === 0) ? R : r;
    const a = -Math.PI/2 + i*Math.PI/5;
    const x = cx + rad*Math.cos(a), y = cy + rad*Math.sin(a);
    d += (i ? 'L' : 'M') + x.toFixed(2) + ',' + y.toFixed(2);
  }
  return d + 'Z';
}

/* 文字宽度：优先用 canvas 量（浏览器/插件环境），否则回退到数字宽度估算。
   徽章里永远只放 "12.34" 这种数字，所以回退表只需要覆盖数字和点号。 */
let _measureCtx = null;
function makeMeasurer(fontFamily){
  if (typeof document !== 'undefined' && document.createElement){
    const cv = document.createElement('canvas');
    _measureCtx = _measureCtx || cv.getContext('2d');
    return (text, font) => { _measureCtx.font = font; return _measureCtx.measureText(text).width; };
  }
  // 回退：Segoe UI 800 字重下，数字与点号的宽度比
  const RATIO = { '.': 0.28, '0':0.58,'1':0.58,'2':0.58,'3':0.58,'4':0.58,
                  '5':0.58,'6':0.58,'7':0.58,'8':0.58,'9':0.58 };
  return (text, font) => {
    const m = /([\d.]+)px/.exec(font);
    const size = m ? parseFloat(m[1]) : 20;
    let w = 0;
    for (const ch of String(text)) w += (RATIO[ch] !== undefined ? RATIO[ch] : 0.56) * size;
    return w;
  };
}

/* --------------------------------------------------------- 绘制 --- */
/**
 * 生成星级条的结构（defs + body + 尺寸）。
 * @returns {{defs:string, body:string, w:number, h:number, tier:object,
 *            starColor:string, numColor:string, filled:number, n:number, perStar:number}}
 */
function paintStrip(options){
  const s = Object.assign({}, DEFAULTS, options || {});
  const textWidth = makeMeasurer(s.font);

  const prefix   = s.idPrefix || 'p';
  const v        = Math.max(0, Number(s.value) || 0);
  const n        = Math.max(1, Math.round(s.starCount));
  const scale    = Math.max(0.0001, Number(s.scaleMax) || 8);
  const perStar  = scale / n;
  const tier     = tierOf(v);

  let starColor, numColor;
  switch (s.colorMode){
    case 'tier':     starColor = tier.color;               numColor = tier.accent; break;
    case 'starOnly': starColor = rampColor(STAR_RAMP, v);  numColor = starColor;   break;
    case 'fixed':    starColor = s.fixedColor;             numColor = s.fixedColor; break;
    default:         starColor = rampColor(STAR_RAMP, v);  numColor = rampColor(NUM_RAMP, v);
  }
  const badgeHex = numColor;

  const R      = s.starSize/2;
  const pitch  = s.starSize * s.spacing;
  const pad    = Math.round(s.starSize * 0.42);
  const badgeH = s.starSize * 0.96;
  const badgeFontSize = badgeH * 0.50;
  const badgeFont = '800 ' + badgeFontSize.toFixed(2) + 'px ' + s.font;
  const valStr = v.toFixed(2);
  const iconR  = badgeH * 0.27;
  const badgePadX = badgeH * 0.36;
  const badgeInnerGap = badgeH * 0.24;
  const badgeW = badgePadX + iconR*2 + badgeInnerGap + textWidth(valStr, badgeFont) + badgePadX;
  const badgeStarGap = Math.round(s.starSize * 0.42);

  const starsW = n * pitch - (pitch - s.starSize);
  const tierFontSize = Math.max(11, s.starSize*0.30);
  const tierH = s.showTier ? tierFontSize*1.75 : 0;

  const rowH = Math.max(badgeH, s.starSize);
  const W = Math.round(pad*2 + (s.showBadge ? badgeW + badgeStarGap : 0) + starsW);
  const H = Math.round(pad*2 + rowH + tierH);
  const cy = pad + rowH/2;
  const starStartX = pad + (s.showBadge ? badgeW + badgeStarGap : 0);

  let defs = '', body = '';

  // 背景：模板用必须透明，所以只在显式给了 bg 时才画
  if (s.bg) body += '<rect x="0" y="0" width="'+W+'" height="'+H+'" fill="'+escapeXml(s.bg)+'"/>';

  if (s.showBadge){
    const bx = pad, by = cy - badgeH/2, brx = badgeH/2;
    const badgeBg = s.badgeBg;
    const badgeStroke = mix(badgeBg, badgeHex, 0.38);
    const badgeFg = luminance(badgeHex) < 0.18 ? mix(badgeHex, '#ffffff', 0.30) : badgeHex;

    body += '<rect x="'+bx.toFixed(2)+'" y="'+by.toFixed(2)+'" width="'+badgeW.toFixed(2)+
            '" height="'+badgeH.toFixed(2)+'" rx="'+brx.toFixed(2)+
            '" fill="'+badgeBg+'" stroke="'+badgeStroke+'" stroke-width="1.2"/>';
    const icx = bx + badgePadX + iconR;
    // 小星星跟右边那排同色；数字仍用数字色阶
    const iconFill = (s.badgeStarColor === null || s.badgeStarColor === undefined)
                     ? starColor : s.badgeStarColor;
    body += '<path d="'+starPath(icx, cy, iconR, iconR*0.45)+'" fill="'+iconFill+'"/>';
    const tx = icx + iconR + badgeInnerGap;
    // 显式定位基线：让数字墨迹的视觉中心落在 cy 上
    const baselineY = cy + badgeFontSize * (Number(s.capRatio) || 0.66) / 2;
    body += '<text x="'+tx.toFixed(2)+'" y="'+baselineY.toFixed(2)+'" fill="'+badgeFg+
            '" font-family="'+escapeXml(s.font)+'" font-size="'+badgeFontSize.toFixed(2)+
            '" font-weight="800" letter-spacing="-0.3">'+
            escapeXml(valStr)+'</text>';
  }

  const emptyBase = clamp(Number(s.emptyOpacity), 0, 1);
  // 空星颜色：默认固定灰，避免高分段和点亮星一起沉进深色背景
  const emptyColor = (s.emptyColor === null) ? starColor : (s.emptyColor || '#5A6684');

  // 描边：星形偏暗时自动加亮边，让轮廓从深色背景里浮出来
  let strokeW = 0, strokeCol = 'none';
  if (s.starStroke && s.starStroke !== 'none'){
    const explicit = (typeof s.starStroke === 'string' && s.starStroke.charAt(0) === '#');
    const useIt = explicit ? true : (luminance(starColor) < Number(s.starStrokeMinLum));
    if (useIt){
      strokeW = Number(s.starStrokeWidth) || 1.5;
      strokeCol = explicit ? s.starStroke : mix(starColor, '#ffffff', Number(s.starStrokeWhiteMix));
    }
  }

  let pastFill = 0;
  for (let i=0;i<n;i++){
    const cx = starStartX + i*pitch + R;
    const d  = starPath(cx, cy, R, R*0.45);
    const filled = clamp(v/perStar - i, 0, 1);

    let op, fillCol;
    if (filled >= 0.999){
      op = 1; fillCol = starColor; pastFill = 0;
    } else if (filled > 0){
      op = emptyBase + (1-emptyBase)*filled; fillCol = starColor; pastFill = 1;
    } else {
      op = s.fadeTail ? Math.max(0.06, emptyBase*(1 - 0.42*pastFill)) : emptyBase;
      fillCol = emptyColor; pastFill += 1;
    }

    body += '<path d="'+d+'" fill="'+fillCol+'" opacity="'+op.toFixed(3)+'"/>';

    if (filled > 0.002 && filled < 0.998){
      const cid = prefix + '_cp' + i;
      defs += '<clipPath id="'+cid+'"><rect x="'+(cx-R-1).toFixed(2)+'" y="'+(cy-R-1).toFixed(2)+
              '" width="'+(2*R*filled + 1).toFixed(2)+'" height="'+(2*R+2).toFixed(2)+'"/></clipPath>';
      body += '<path d="'+d+'" fill="'+starColor+'" clip-path="url(#'+cid+')"/>';
    }

    // 描边画在填充之上，避免被半亮星的裁剪边缘切出竖线
    if (strokeW > 0 && filled > 0.002){
      body += '<path d="'+d+'" fill="none" stroke="'+strokeCol+
              '" stroke-width="'+strokeW+'" stroke-linejoin="round"/>';
    }
  }

  if (s.showTier){
    const font = '700 ' + tierFontSize.toFixed(2) + 'px ' + s.font;
    const tw = textWidth(tier.label, font);
    body += '<text x="'+starStartX.toFixed(2)+'" y="'+(pad+rowH+tierFontSize*1.05).toFixed(2)+
            '" fill="'+tier.accent+'" font-family="'+escapeXml(s.font)+'" font-size="'+
            tierFontSize.toFixed(2)+'" font-weight="700">'+escapeXml(tier.label)+'</text>';
    body += '<text x="'+(starStartX + tw + tierFontSize*0.6).toFixed(2)+'" y="'+
            (pad+rowH+tierFontSize*1.05).toFixed(2)+'" fill="#ffffff" opacity="0.72" font-family="'+
            escapeXml(s.font)+'" font-size="'+(tierFontSize*0.82).toFixed(2)+'">'+
            escapeXml(tier.range)+'</text>';
  }

  return { defs, body, w: W, h: H, tier, starColor, numColor, badgeColor: badgeHex,
           perStar, filled: clamp(v/perStar, 0, n), n };
}

/** 拼成完整 SVG 字符串 */
function toSvgString(r, idPrefix){
  const pre = idPrefix || 'p';
  return '<svg xmlns="http://www.w3.org/2000/svg" width="'+r.w+'" height="'+r.h+
         '" viewBox="0 0 '+r.w+' '+r.h+'">'+
         (r.defs ? '<defs>'+r.defs+'</defs>' : '') + r.body + '</svg>';
}

/**
 * 一步到位：给数值，拿 SVG。
 * @param {object} options  见 DEFAULTS
 * @returns {{svg:string, width:number, height:number, tier:object,
 *            starColor:string, numColor:string, filled:number}}
 */
function renderStarStrip(options){
  const r = paintStrip(options);
  return {
    svg: toSvgString(r, (options && options.idPrefix) || 'p'),
    width: r.w, height: r.h, tier: r.tier,
    starColor: r.starColor, numColor: r.numColor,
    filled: r.filled, perStar: r.perStar, starCount: r.n,
  };
}

/* =====================================================================
 * 双模式 + 定宽：≤10 星用 10 颗，>10 星切 15 颗并让星星互相重叠
 * ---------------------------------------------------------------------
 * 目的：整条宽度恒定，10 颗和 15 颗两种形态占一样宽，版面不会跳。
 *
 * 星星行宽度 = s * (spacing*(n-1) + 1)      （s = 单星直径）
 * 所以让 15 颗和 10 颗同宽，只需解 spacing：
 *     spacing15 * 14 + 1 = spacing10 * 9 + 1
 * ===================================================================== */

const DUAL_MODE = {
  threshold: 10,          // 超过这个星数就切到 15 颗
  lowStars:  10,
  highStars: 15,
  baseSpacing: 1.24,
};

/** 求出让 nTo 颗星占据和 (nFrom, spFrom) 同样宽度的间距 */
function spacingForSameWidth(nFrom, spFrom, nTo){
  const span = spFrom * (nFrom - 1) + 1;   // 以 s 为单位
  return (span - 1) / (nTo - 1);
}

/**
 * 按数值自动选模式，并把整条宽度锁到 width 像素。
 * @param {number} value       星级数值
 * @param {number} width       期望的整条宽度(px)
 * @param {object} [options]   其余参数同 DEFAULTS
 * @returns 同 renderStarStrip，另带 mode / starSize / spacing
 */
function renderStarStripFit(value, width, options){
  const v = Math.max(0, Number(value) || 0);
  const D = DUAL_MODE;
  const high = v > D.threshold;

  const starCount = high ? D.highStars : D.lowStars;
  const scaleMax  = high ? D.highStars : D.lowStars;      // 一颗星 = 一星
  const spacing   = high
    ? spacingForSameWidth(D.lowStars, D.baseSpacing, D.highStars)
    : D.baseSpacing;

  const base = Object.assign({}, options, {
    value: v, starCount, scaleMax, spacing,
    starSize: 46, idPrefix: (options && options.idPrefix) || 'p',
  });

  // 宽度与 starSize 线性相关（pad 有四舍五入，误差 <1px），一次测算即可
  const probe = paintStrip(base);
  const k = probe.w / 46;
  const starSize = Math.max(8, Math.round((width / k) * 100) / 100);

  const r = renderStarStrip(Object.assign({}, base, { starSize }));
  r.mode = high ? 'dense15' : 'normal10';
  r.starSize = starSize;
  r.spacing = spacing;
  r.targetWidth = width;
  r.widthError = Math.round((r.width - width) * 100) / 100;
  return r;
}

/* =====================================================================
 * 属性进度条（OD / HP）
 * ---------------------------------------------------------------------
 * 普通状态量程 0..10；
 * 开启 Difficulty Adjust(DA) 且数值超出原版范畴时：
 *   OD -> -15..15（0 在正中）
 *   HP -> 0..11
 * 颜色取自上面的色阶（默认 NUM_RAMP）。
 * ===================================================================== */

const STAT_BAR_DEFAULTS = {
  value: 9.0,
  min: 0, max: 10,
  width: 600, height: 12,
  radius: 6,
  trackColor: '#2E3543',
  ramp: 'num',          // 'num' | 'star' | 'fixed'
  fixedColor: '#7b8cff',
  mapTo: 'value',       // 'value' = 颜色按数值 | 'fraction' = 颜色按填充比例
  domainMax: 18,        // mapTo='fraction' 时把 0..1 映射到色阶的哪个区间
  origin: 'auto',       // 'auto' | 'left' | 'zero' —— 双极量程默认从 0 点向两侧填
  tickStep: 0,          // 每隔多少个单位画一条刻度线（0 = 不画）
  tickColor: '#0B0D11',
  tickOpacity: 0.5,
  zeroLineColor: '#EAEEF6',
  zeroLineOpacity: 0.35,
  idPrefix: 'sb',
};

/** 返回 {svg, width, height, fillFraction, color, originX, bipolar} */
function renderStatBar(options){
  const s = Object.assign({}, STAT_BAR_DEFAULTS, options || {});
  const W = Number(s.width), H = Number(s.height);
  const r = Math.min(Number(s.radius), H/2);
  const v = Number(s.value);
  const lo = Number(s.min), hi = Number(s.max);
  const span = (hi - lo) || 1;
  const frac = clamp((v - lo) / span, 0, 1);

  // 是否双极（量程跨过 0）——双极时从 0 点向两侧填充
  const bipolar = (lo < 0 && hi > 0);
  const useZero = (s.origin === 'zero') || (s.origin === 'auto' && bipolar);
  const x0 = useZero ? (0 - lo) / span * W : 0;
  const xv = frac * W;
  const left = Math.min(x0, xv);
  const fillW = Math.abs(xv - x0);

  let color;
  if (s.ramp === 'fixed') color = s.fixedColor;
  else {
    const ramp = (s.ramp === 'star') ? STAR_RAMP : NUM_RAMP;
    const key = (s.mapTo === 'fraction') ? frac * Number(s.domainMax) : v;
    color = rampColor(ramp, key);
  }

  const cid = s.idPrefix + '_f';
  let defs = '', body = '';

  body += '<rect x="0" y="0" width="'+W+'" height="'+H+'" rx="'+r+'" fill="'+s.trackColor+'"/>';

  // 填充：整条圆角矩形按区间裁剪，得到「外端圆、内端平切」的经典形状
  if (fillW > 0.4){
    defs += '<clipPath id="'+cid+'"><rect x="'+left.toFixed(2)+'" y="0" width="'+
            fillW.toFixed(2)+'" height="'+H+'"/></clipPath>';
    body += '<rect x="0" y="0" width="'+W+'" height="'+H+'" rx="'+r+
            '" fill="'+color+'" clip-path="url(#'+cid+')"/>';
  }

  // 刻度线：每隔 tickStep 个单位一条
  const step = Number(s.tickStep) || 0;
  if (step > 0){
    let t = Math.ceil(lo / step) * step;
    for (; t < hi; t += step){
      if (Math.abs(t) < 1e-9) continue;              // 0 点单独画
      const x = (t - lo) / span * W;
      if (x < 1 || x > W - 1) continue;
      body += '<rect x="'+(x - 0.5).toFixed(2)+'" y="0" width="1" height="'+H+
              '" fill="'+s.tickColor+'" opacity="'+s.tickOpacity+'"/>';
    }
  }

  // 双极量程：把 0 点单独标出来
  if (useZero){
    body += '<rect x="'+(x0 - 0.75).toFixed(2)+'" y="0" width="1.5" height="'+H+
            '" fill="'+s.zeroLineColor+'" opacity="'+s.zeroLineOpacity+'"/>';
  }

  return {
    svg: '<svg xmlns="http://www.w3.org/2000/svg" width="'+W+'" height="'+H+
         '" viewBox="0 0 '+W+' '+H+'">'+(defs ? '<defs>'+defs+'</defs>' : '')+body+'</svg>',
    width: W, height: H, fillFraction: frac, color: color,
    originX: x0, bipolar: bipolar, scale: lo + '..' + hi,
  };
}

/* OD / HP 的量程规则（DA = Difficulty Adjust） */
const STAT_RANGES = {
  od: { normal: [0, 10],   da: [-15, 15] },
  hp: { normal: [0, 10],   da: [0, 11] },
};
/** 按字段与实际数值，算出该用哪段量程 */
function statRangeFor(field, value, daEnabled){
  const R = STAT_RANGES[field];
  if (!R) return { min: 0, max: 10, extended: false };
  const v = Number(value);
  const outOfRange = v < R.normal[0] || v > R.normal[1];
  if (daEnabled && outOfRange) return { min: R.da[0], max: R.da[1], extended: true };
  return { min: R.normal[0], max: R.normal[1], extended: false };
}

/* --------------------------------------------------------- 导出 --- */
const API = { renderStarStrip, renderStarStripFit, paintStrip, toSvgString, DEFAULTS,
              DUAL_MODE, spacingForSameWidth,
              renderStatBar, STAT_BAR_DEFAULTS, STAT_RANGES, statRangeFor,
              STAR_RAMP, STAR_RAMP_MIN_LUM, NUM_RAMP, TIERS, rampColor, tierOf, starPath };

if (typeof module !== 'undefined' && module.exports) module.exports = API;
if (typeof window !== 'undefined') window.StarStrip = API;
