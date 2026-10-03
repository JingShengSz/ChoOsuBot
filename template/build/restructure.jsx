app.displayDialogs = DialogModes.NO;
var doc = app.activeDocument;
var root = doc.layerSets.getByName('TEMPLATE_ROOT');
var gStats = root.layerSets.getByName('beatmap_stats');
var gInfo  = root.layerSets.getByName('beatmap_info');
var gPri   = root.layerSets.getByName('primary_stats');
var gSec   = root.layerSets.getByName('secondary_stats');
var gMods  = root.layerSets.getByName('mods_block');
var gPlay  = root.layerSets.getByName('player_info');
var log = [];

var C_WHITE='EAEEF6', C_GREY='8C97A9', C_DIM='5F6878', C_BORDER='2E3543', C_BLOCK='3C4453';
var IR='Inter18pt-Regular', IM='Inter18pt-Medium', IB='Inter18pt-Bold';
function col(h){ var c=new SolidColor(); c.rgb.hexValue=h; return c; }
function rect(x,y,w,h,hex){
  if (w<=0||h<=0) return;
  doc.selection.select([[x,y],[x+w,y],[x+w,y+h],[x,y+h]]);
  doc.selection.fill(col(hex), ColorBlendMode.NORMAL, 100, false);
  doc.selection.deselect();
}
function newRect(g,name,x,y,w,h,hex){
  var l = g.artLayers.add();
  l.name = name;
  doc.activeLayer = l;
  rect(x,y,w,h,hex);
  return l;
}
function mkTxt(g,name,x,y,size,hex,str,font,just,track){
  var l = g.artLayers.add();
  l.name = name;
  l.kind = LayerKind.TEXT;
  var t = l.textItem;
  t.contents = str;
  t.font = font || IR;
  t.size = new UnitValue(size,'px');
  t.color = col(hex);
  if (just) t.justification = just;
  if (track !== undefined) t.tracking = track;
  t.position = [x, y + 0.85*size];
  return l;
}
function setTxt(g,name,x,y,just){
  var l = g.artLayers.getByName(name);
  var t = l.textItem;
  if (just) t.justification = just;
  t.position = [x, y + 0.85*t.size.value];
  return l;
}
function rm(g,name){ try { g.artLayers.getByName(name).remove(); return true; } catch(e){ return false; } }
var JL=Justification.LEFT, JC=Justification.CENTER, JR=Justification.RIGHT;

// ================= 1. obsolete layers =================
var gone = [];
if (rm(gStats,'diff_stats')) gone.push('diff_stats');
var rasterLabels = [ [gPri,'_deco_accuracy_label'], [gPri,'_deco_pp_label'],
  [gSec,'_deco_score_label'], [gSec,'_deco_combo_label'], [gSec,'_deco_judgement_label'],
  [gMods,'_deco_mods_label'] ];
for (var i=0;i<rasterLabels.length;i++){
  if (rm(rasterLabels[i][0], rasterLabels[i][1])) gone.push(rasterLabels[i][1]);
}
log.push('removed ' + gone.length + ' obsolete layers');

// ================= 2. attribute grid (left column) =================
newRect(gStats,'_deco_left_divider', 60, 236, 600, 2, C_BORDER);
newRect(gStats,'_deco_attr_star',  60, 268, 32, 32, C_BLOCK);
newRect(gStats,'_deco_attr_bpm',  360, 268, 32, 32, C_BLOCK);
newRect(gStats,'_deco_attr_od',    60, 356, 32, 32, C_BLOCK);
newRect(gStats,'_deco_attr_hp',   360, 356, 32, 32, C_BLOCK);
mkTxt(gStats,'od', 104, 352, 32, C_WHITE, '9.0', IB, JL);
mkTxt(gStats,'hp', 404, 352, 32, C_WHITE, '6.0', IB, JL);
log.push('attribute grid built');

// ================= 3. new player fields =================
mkTxt(gPri,'total_pp',       720, 288, 30, C_WHITE, '12,345pp', IB, JL);
mkTxt(gPri,'pp_max',         980, 364, 36, C_GREY,  '612pp',   IB, JL);
mkTxt(gPri,'accuracy_lazer', 980, 616, 26, C_GREY,  '98.12%',  IB, JL);
mkTxt(gSec,'map_max_combo',  980, 528, 30, C_GREY,  '2,109x',  IB, JL);

// ================= 4. real text labels =================
var LBL = [
  [gPri,'_deco_total_pp_label',       720, 268, 'TOTAL PP'],
  [gPri,'_deco_pp_label',             720, 344, 'PP'],
  [gPri,'_deco_pp_max_label',         980, 344, 'MAX PP'],
  [gPri,'_deco_accuracy_label',       720, 582, 'ACCURACY'],
  [gPri,'_deco_accuracy_lazer_label', 980, 596, 'LAZER ACC'],
  [gSec,'_deco_score_label',          720, 424, 'SCORE'],
  [gSec,'_deco_combo_label',          720, 508, 'COMBO'],
  [gSec,'_deco_map_combo_label',      980, 508, 'MAP COMBO'],
  [gSec,'_deco_judgement_label',       60, 712, 'JUDGEMENT'],
  [gMods,'_deco_mods_label',           60, 828, 'MODS']
];
for (var k=0;k<LBL.length;k++){
  mkTxt(LBL[k][0], LBL[k][1], LBL[k][2], LBL[k][3], 15, C_DIM, LBL[k][4], IR, JL, 80);
}
log.push('10 text labels created');

// ================= 5. reposition =================
setTxt(gInfo,'beatmap_title',  60,  70, JL);
setTxt(gInfo,'beatmap_artist', 60, 126, JL);
setTxt(gInfo,'beatmap_mapper', 60, 166, JL);
setTxt(gInfo,'beatmap_id',     60, 198, JL);
setTxt(gStats,'star_rating',  104, 264, JL);
setTxt(gStats,'bpm',          404, 264, JL);
setTxt(gStats,'od',           104, 352, JL);
setTxt(gStats,'hp',           404, 352, JL);
setTxt(gPlay,'player_name',   980, 188, JC);
setTxt(gPlay,'rank_change',   980, 224, JC);
setTxt(gPri,'total_pp',       720, 288, JL);
setTxt(gPri,'pp',             720, 364, JL);
setTxt(gPri,'pp_max',         980, 364, JL);
setTxt(gSec,'score',          720, 444, JL);
setTxt(gSec,'max_combo',      720, 528, JL);
setTxt(gSec,'map_max_combo',  980, 528, JL);
setTxt(gPri,'accuracy',       720, 602, JL);
setTxt(gPri,'accuracy_lazer', 980, 616, JL);
setTxt(gPlay,'play_date',     720, 940, JL);

// title font/size for the narrower column
var ti = gInfo.artLayers.getByName('beatmap_title');
ti.textItem.font = IM;
ti.textItem.size = new UnitValue(38,'px');
ti.textItem.position = [60, 70 + 0.85*38];
log.push('repositioned');

// ================= 6. avatar + divider redraw =================
doc.activeLayer = gPlay.artLayers.getByName('player_avatar');
doc.selection.selectAll(); doc.selection.clear(); doc.selection.deselect();
var pts=[], n=48;
for (var q=0;q<n;q++){ var ang=2*Math.PI*q/n; pts.push([980+58*Math.cos(ang), 118+58*Math.sin(ang)]); }
doc.selection.select(pts);
doc.selection.fill(col(C_BLOCK), ColorBlendMode.NORMAL, 100, false);
doc.selection.deselect();
newRect(gPlay,'_deco_player_divider', 720, 256, 520, 2, C_BORDER);
log.push('avatar + divider');

// ================= 7. save =================
var out = new File('D:/DeepSeek Harness/workspace1/osu_score_template_v1.psd');
var opt = new PhotoshopSaveOptions();
opt.alphaChannels = true; opt.layers = true; opt.embedColorProfile = true;
doc.saveAs(out, opt, true);
var pf = new File('D:/DeepSeek Harness/workspace1/osu_score_template_v1_skeleton.png');
var po = new PNGSaveOptions(); po.compression = 6; po.interlaced = false;
doc.saveAs(pf, po, true);
log.push('saved + png');

log.join(' | ');
