app.displayDialogs = DialogModes.NO;
var target = app.activeDocument;
var root = target.layerSets.getByName('TEMPLATE_ROOT');
var gSec  = root.layerSets.getByName('secondary_stats');
var gMods = root.layerSets.getByName('mods_block');
var gPlay = root.layerSets.getByName('player_info');
var gWater= root.layerSets.getByName('watermark_slot');
var BASE = 'D:/DeepSeek Harness/workspace1/_icons/out/';
var C_DIM = '5F6878';
var log = [];

function col(h){ var c = new SolidColor(); c.rgb.hexValue = h; return c; }
function rect(x,y,w,h,hex){
  if (w <= 0 || h <= 0) return;
  target.selection.select([[x,y],[x+w,y],[x+w,y+h],[x,y+h]]);
  target.selection.fill(col(hex), ColorBlendMode.NORMAL, 100, false);
  target.selection.deselect();
}
function wipe(g,name){
  target.activeLayer = g.artLayers.getByName(name);
  target.selection.selectAll();
  target.selection.clear();
  target.selection.deselect();
}
function setTxt(g,name,x,y,just){
  var l = g.artLayers.getByName(name);
  var t = l.textItem;
  if (just) t.justification = just;
  t.position = [x, y + 0.85 * t.size.value];
  return l;
}
function bringIn(path,name,boxX,boxY,boxW,boxH,group){
  var src = app.open(new File(path));
  src.resizeImage(UnitValue(boxW,'px'), UnitValue(boxH,'px'), null, ResampleMethod.BICUBICSHARPER);
  var sl = src.layers[0];
  var b0 = sl.bounds, offX = b0[0], offY = b0[1];
  var nl = sl.duplicate(target, ElementPlacement.PLACEATBEGINNING);
  src.close(SaveOptions.DONOTSAVECHANGES);
  app.activeDocument = target;
  nl.name = name;
  try { nl.move(group, ElementPlacement.INSIDE); } catch(e){ log.push(name + ':moveERR'); }
  var b1 = nl.bounds;
  nl.translate((boxX + offX) - b1[0], (boxY + offY) - b1[1]);
  var b2 = nl.bounds;
  var gx = Math.round(b2[0] - offX), gy = Math.round(b2[1] - offY);
  if (gx !== boxX || gy !== boxY) log.push(name + ':OFF(' + gx + ',' + gy + ')');
  return nl;
}

// ---- clear previous icon layers ----
var rm = 0;
for (var g = 0; g < 2; g++){
  var gs = (g === 0) ? gSec : gMods;
  for (var i = gs.layers.length - 1; i >= 0; i--){
    var l = gs.layers[i];
    if (l.typename === 'LayerSet') continue;
    if (l.name.indexOf('_deco_jicon') === 0 || /^mod_[1-6]$/.test(l.name)) {
      try { l.remove(); rm++; } catch(e){}
    }
  }
}
log.push('cleared ' + rm);

// ---- label bars / watermark guide ----
wipe(gSec,'_deco_judgement_label');  rect(60, 712, 180, 12, C_DIM);
wipe(gMods,'_deco_mods_label');      rect(60, 828, 60, 12, C_DIM);
wipe(gWater,'_deco_watermark_guide');rect(60, 950, 180, 60, '3C4453');
setTxt(gWater,'_deco_watermark_hint', 80, 922, null);

// ---- judgement row: full data width, pitch 196, 56px icons ----
var jn = ['count_max','count_300','count_200','count_100','count_50','count_miss'];
for (var a = 0; a < 6; a++){
  bringIn(BASE + jn[a] + '.png', '_deco_jicon_' + jn[a], 60 + a*196, 745, 56, 56, gSec);
}
for (var k = 0; k < 6; k++){
  var c = gSec.artLayers.getByName(jn[k]);
  c.textItem.font = 'Inter18pt-Regular';
  c.textItem.size = new UnitValue(26,'px');
  c.textItem.justification = Justification.LEFT;
  c.textItem.position = [60 + k*196 + 64, 760 + 0.85*26];
}
log.push('judgement row pitch196');

// ---- mod row: second line ----
for (var m = 0; m < 6; m++){
  bringIn(BASE + 'mod_' + (m+1) + '.png', 'mod_' + (m+1), 60 + m*82, 852, 56, 56, gMods);
}
setTxt(gPlay,'play_date', 700, 870, Justification.LEFT);
log.push('mod row y852');

// ---- save ----
var out = new File('D:/DeepSeek Harness/workspace1/osu_score_template_v1.psd');
var opt = new PhotoshopSaveOptions();
opt.alphaChannels = true;
opt.layers = true;
opt.embedColorProfile = true;
target.saveAs(out, opt, true);
log.push('saved');

// ---- export preview png ----
var pf = new File('D:/DeepSeek Harness/workspace1/osu_score_template_v1_skeleton.png');
var po = new PNGSaveOptions();
po.compression = 6;
po.interlaced = false;
target.saveAs(pf, po, true);
log.push('png exported');

log.join(' | ');
