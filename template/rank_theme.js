/* =====================================================================
 * 评级配色（rank theme）—— 零依赖，Node 与浏览器通用
 * ---------------------------------------------------------------------
 * 一个评级（XH/SS/SH/S/A/B/C/D）驱动模板里的三处：
 *
 *   1. bgGradient   背景径向染色，叠在 _deco_bg_overlay 之上，给整张卡定调
 *   2. rankGlow     立绘背后的辉光，垫在 signboard 最底层
 *   3. accent       强调色，给准确率数字等用（插件直接设文字颜色）
 *
 * 颜色取自 osu! 客户端的评级色：SS/S/XH 金、SH 银、A 绿、B 蓝、C 紫、D 红。
 * XH 和 SS 都是金，靠亮度区分（XH 更亮更白）；S 的金属感稍弱一点。
 *
 * 用法：
 *   const R = require('./rank_theme.js');
 *   R.rankOf('XH').label          -> 'XH'
 *   R.renderBgGradient('A').svg   -> SVG 字符串
 *   R.renderRankGlow('D').svg
 * ===================================================================== */

/* ------------------------------------------------------------ 色板 --- */
const RANKS = {
  XH: { label: 'XH', name: 'All Perfect + Hidden', color: '#FFE45C', glowStrength: 0.62, tintStrength: 0.26 },
  SS: { label: 'SS', name: 'All Perfect',          color: '#FFCB3D', glowStrength: 0.58, tintStrength: 0.24 },
  SH: { label: 'SH', name: 'Full Combo + Hidden',  color: '#D9E2EF', glowStrength: 0.46, tintStrength: 0.18 },
  S:  { label: 'S',  name: 'Full Combo',           color: '#FFB93D', glowStrength: 0.50, tintStrength: 0.21 },
  A:  { label: 'A',  name: 'A',                    color: '#6BC24A', glowStrength: 0.42, tintStrength: 0.17 },
  B:  { label: 'B',  name: 'B',                    color: '#4A9BE8', glowStrength: 0.40, tintStrength: 0.16 },
  C:  { label: 'C',  name: 'C',                    color: '#A25CE0', glowStrength: 0.38, tintStrength: 0.15 },
  D:  { label: 'D',  name: 'D',                    color: '#E8503F', glowStrength: 0.38, tintStrength: 0.15 },
};

/* 拿不到评级时的兜底（比如成绩还没结算） */
const FALLBACK = 'A';

const DEFAULTS = {
  width: 1920,
  height: 1080,
  /* 辉光圆心与半径 —— 对齐立绘的视觉重心，不是画布中心 */
  glowCx: 1600, glowCy: 560, glowRx: 760, glowRy: 820,
  /* 背景染色的圆心/半径 —— 比辉光大一圈，铺满右侧 */
  tintCx: 1560, tintCy: 420, tintRx: 1180, tintRy: 1080,
};

/* ------------------------------------------------------------ 工具 --- */
function hexToRgb(h){
  return [parseInt(h.substr(1,2),16), parseInt(h.substr(3,2),16), parseInt(h.substr(5,2),16)];
}
function luminance(hex){
  const c = hexToRgb(hex).map(v => { v /= 255; return v <= 0.04045 ? v/12.92 : Math.pow((v+0.055)/1.055, 2.4); });
  return 0.2126*c[0] + 0.7152*c[1] + 0.0722*c[2];
}
/** WCAG 对比度，用来检查强调色在深色底板上够不够读 */
function contrastOn(bgLum, hex){
  const a = Math.max(luminance(hex), bgLum), b = Math.min(luminance(hex), bgLum);
  return (a + 0.05) / (b + 0.05);
}
function rankOf(key){
  return RANKS[String(key || '').toUpperCase()] || RANKS[FALLBACK];
}
function hexToRgba(hex, a){
  const [r,g,b] = hexToRgb(hex);
  return `rgba(${r},${g},${b},${+a.toFixed(4)})`;
}

/* --------------------------------------------------- 1. 背景径向染色 --- */
/**
 * 铺满画布的评级染色。叠在 _deco_bg_overlay 之上（bg 组内），blend = normal。
 * 中心亮、边缘透明，把视线导向立绘那一侧。
 */
function renderBgGradient(rankKey, options){
  const R = rankOf(rankKey);
  const o = Object.assign({}, DEFAULTS, options || {});
  const s = R.tintStrength;
  const id = 'bgtint_' + R.label;
  const svg =
    `<svg xmlns="http://www.w3.org/2000/svg" width="${o.width}" height="${o.height}" viewBox="0 0 ${o.width} ${o.height}">` +
      `<defs><radialGradient id="${id}" cx="${o.tintCx}" cy="${o.tintCy}" r="${o.tintRx}"` +
        ` gradientUnits="userSpaceOnUse">` +
        `<stop offset="0" stop-color="${hexToRgba(R.color, s)}"/>` +
        `<stop offset="0.55" stop-color="${hexToRgba(R.color, s * 0.45)}"/>` +
        `<stop offset="1" stop-color="${hexToRgba(R.color, 0)}"/>` +
      `</radialGradient></defs>` +
      `<rect width="${o.width}" height="${o.height}" fill="url(#${id})"/>` +
    `</svg>`;
  return { svg: svg, width: o.width, height: o.height, color: R.color, strength: s, rank: R.label };
}

/* ------------------------------------------------------- 2. 立绘辉光 --- */
/**
 * 立绘背后的辉光。垫在 signboard 组最底层，blend = screen。
 * 两段：内圈亮、外圈散开，避免出现一圈生硬的边。
 */
function renderRankGlow(rankKey, options){
  const R = rankOf(rankKey);
  const o = Object.assign({}, DEFAULTS, options || {});
  const s = R.glowStrength;
  const id = 'glow_' + R.label;
  const svg =
    `<svg xmlns="http://www.w3.org/2000/svg" width="${o.width}" height="${o.height}" viewBox="0 0 ${o.width} ${o.height}">` +
      `<defs><radialGradient id="${id}" cx="${o.glowCx}" cy="${o.glowCy}" r="${o.glowRx}"` +
        ` gradientUnits="userSpaceOnUse">` +
        `<stop offset="0" stop-color="${hexToRgba(R.color, s)}"/>` +
        `<stop offset="0.30" stop-color="${hexToRgba(R.color, s * 0.62)}"/>` +
        `<stop offset="0.62" stop-color="${hexToRgba(R.color, s * 0.22)}"/>` +
        `<stop offset="1" stop-color="${hexToRgba(R.color, 0)}"/>` +
      `</radialGradient></defs>` +
      `<ellipse cx="${o.glowCx}" cy="${o.glowCy}" rx="${o.glowRx}" ry="${o.glowRy}" fill="url(#${id})"/>` +
    `</svg>`;
  return { svg: svg, width: o.width, height: o.height, color: R.color, strength: s, rank: R.label };
}

/* ------------------------------------------------------- 3. 强调色 --- */
/**
 * 强调色用在准确率这类大字号上。返回颜色 + 在深色底板上的对比度，
 * 方便调用方判断要不要退回中性色。
 */
function accent(rankKey, panelLum){
  const R = rankOf(rankKey);
  const bg = typeof panelLum === 'number' ? panelLum : 0.005;   // 毛玻璃底板实测亮度
  return { color: R.color, contrast: Math.round(contrastOn(bg, R.color) * 100) / 100, rank: R.label };
}

/** 全部评级一览，给插件做下拉或自检用 */
function table(){
  return Object.keys(RANKS).map(function(k){
    const R = RANKS[k];
    return { key: k, label: R.label, name: R.name, color: R.color,
             accentContrast: Math.round(contrastOn(0.005, R.color) * 100) / 100,
             glowStrength: R.glowStrength, tintStrength: R.tintStrength };
  });
}

const API = { RANKS, FALLBACK, DEFAULTS, rankOf, renderBgGradient, renderRankGlow,
              accent, table, luminance, contrastOn, hexToRgb, hexToRgba };

if (typeof module !== 'undefined' && module.exports) module.exports = API;
if (typeof window !== 'undefined') window.RankTheme = API;
