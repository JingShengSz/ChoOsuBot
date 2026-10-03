app.displayDialogs = DialogModes.NO;
var doc = app.activeDocument;
var root = doc.layerSets.getByName('TEMPLATE_ROOT');
var gStats = root.layerSets.getByName('beatmap_stats');
var gInfo  = root.layerSets.getByName('beatmap_info');
var gPri   = root.layerSets.getByName('primary_stats');
var gSec   = root.layerSets.getByName('secondary_stats');
var gPlay  = root.layerSets.getByName('player_info');
var log = [];

var C_BORDER = '2E3543';
var UNIFIED_Y = 280;     // 两条分隔线统一到这个 y

function col(h){ var c=new SolidColor(); c.rgb.hexValue=h; return c; }
function rect(x,y,w,h,hex){
  doc.selection.select([[x,y],[x+w,y],[x+w,y+h],[x,y+h]]);
  doc.selection.fill(col(hex), ColorBlendMode.NORMAL, 100, false);
  doc.selection.deselect();
}
function repaint(g,name,x,y,w,h,hex){
  doc.activeLayer = g.artLayers.getByName(name);
  doc.selection.selectAll(); doc.selection.clear(); doc.selection.deselect();
  rect(x,y,w,h,hex);
}
function shiftTxt(g,name,dy){
  var t = g.artLayers.getByName(name).textItem;
  var p = t.position;
  t.position = [p[0], p[1] + dy];
}

// ---- 1. 两条线对齐到同一条水平线 ----
repaint(gStats,'_deco_left_divider',   60, UNIFIED_Y, 600, 2, C_BORDER);
repaint(gPlay, '_deco_player_divider', 720, UNIFIED_Y, 520, 2, C_BORDER);
log.push('dividers unified at y=' + UNIFIED_Y);

// ---- 2. 右栏在线条以下的内容整体下移，让出线条位置 ----
var DY = 24;
var below = [
  [gPri,'_deco_total_pp_label'],[gPri,'total_pp'],
  [gPri,'_deco_pp_label'],[gPri,'pp'],
  [gPri,'_deco_pp_max_label'],[gPri,'pp_max'],
  [gPri,'_deco_accuracy_label'],[gPri,'accuracy'],
  [gPri,'_deco_accuracy_lazer_label'],[gPri,'accuracy_lazer'],
  [gSec,'_deco_score_label'],[gSec,'score'],
  [gSec,'_deco_combo_label'],[gSec,'max_combo'],
  [gSec,'_deco_map_combo_label'],[gSec,'map_max_combo']
];
for (var i=0;i<below.length;i++){
  try { shiftTxt(below[i][0], below[i][1], DY); }
  catch(e){ log.push(below[i][1] + ':ERR'); }
}
log.push('shifted ' + below.length + ' layers down by ' + DY);

// ---- 3. 复核：确认没有碰撞 ----
function boundsOf(g,name){
  var b = null; try { b = g.artLayers.getByName(name).bounds; } catch(e){}
  return b ? [Math.round(b[0]),Math.round(b[1]),Math.round(b[2]),Math.round(b[3])] : null;
}
var checks = [
  ['id vs left-divider',  boundsOf(gInfo,'beatmap_id'),   'L'],
  ['rank_change',         boundsOf(gPlay,'rank_change'),   'R'],
  ['total_pp label',      boundsOf(gPri,'_deco_total_pp_label'), 'R'],
  ['lazer acc value',     boundsOf(gPri,'accuracy_lazer'), 'R'],
  ['judgement label',     boundsOf(gSec,'_deco_judgement_label'), 'L']
];
for (var c=0;c<checks.length;c++){
  var b = checks[c][1];
  log.push(checks[c][0] + ' y=' + (b ? b[1] + '..' + b[3] : 'n/a'));
}

// ---- 4. save + export ----
var out = new File('D:/DeepSeek Harness/workspace1/osu_score_template_v1.psd');
var opt = new PhotoshopSaveOptions();
opt.alphaChannels = true; opt.layers = true; opt.embedColorProfile = true;
doc.saveAs(out, opt, true);
var pf = new File('D:/DeepSeek Harness/workspace1/osu_score_template_v1_skeleton.png');
var po = new PNGSaveOptions(); po.compression = 6; po.interlaced = false;
doc.saveAs(pf, po, true);
log.push('saved + png');

log.join(' | ');
