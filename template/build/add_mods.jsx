app.displayDialogs = DialogModes.NO;
var doc = app.activeDocument;
var root = doc.layerSets.getByName('TEMPLATE_ROOT');
var gMods = root.layerSets.getByName('mods_block');
var gPlay = root.layerSets.getByName('player_info');
var log = [];

var DIR = 'D:/DeepSeek Harness/workspace1/_mods/placed/';
var SLOTS = ['mod_1','mod_2','mod_3','mod_4','mod_5','mod_6'];
var BADGE_H = 48, PITCH = 110, X0 = 60, Y0 = 842;
var MULT_Y = Y0 + BADGE_H + 8;
var C_GREY = '8C97A9';
var IR = 'Inter18pt-Regular';

function col(h){ var c = new SolidColor(); c.rgb.hexValue = h; return c; }
function mkTxt(g,name,x,y,size,hex,str,font,just,track){
  var l = g.artLayers.add(); l.name = name; l.kind = LayerKind.TEXT;
  var t = l.textItem;
  t.contents = str; t.font = font || IR;
  t.size = new UnitValue(size,'px'); t.color = col(hex);
  if (just) t.justification = just;
  if (track !== undefined) t.tracking = track;
  t.position = [x, y + 0.85*size];
  return l;
}

// ---- 1. 清掉旧槽位 ----
for (var k = 0; k < 6; k++){
  try { gMods.artLayers.getByName('mod_' + (k+1)).remove(); } catch(e){}
  try { gMods.artLayers.getByName('mod_' + (k+1) + '_mult').remove(); } catch(e){}
}
log.push('old cleared');

// ---- 2. 置入徽章：源画布已是 1920x1080 且位置到位，复制即对齐 ----
for (var i = 0; i < 6; i++){
  var sd = app.open(new File(DIR + SLOTS[i] + '.png'));
  var nl = sd.layers[0].duplicate(doc, ElementPlacement.PLACEATBEGINNING);
  sd.close(SaveOptions.DONOTSAVECHANGES);
  app.activeDocument = doc;
  nl.name = SLOTS[i];
  try { nl.move(gMods, ElementPlacement.INSIDE); } catch(e){ log.push(SLOTS[i] + ':move ERR'); }
  var b = nl.bounds;
  var cx = (b[0]+b[2])/2, cy = (b[1]+b[3])/2;
  var wantX = X0 + i*PITCH + PITCH/2, wantY = Y0 + BADGE_H/2;
  log.push(SLOTS[i] + ' c(' + Math.round(cx) + ',' + Math.round(cy) + ')' +
           (Math.abs(cx-wantX) < 1.5 && Math.abs(cy-wantY) < 1.5 ? ' OK' : ' WANT(' + wantX + ',' + wantY + ')'));
}

// ---- 3. 倍率文字层 ----
for (var m = 0; m < 6; m++){
  var ml = mkTxt(gMods, 'mod_' + (m+1) + '_mult', X0 + m*PITCH + PITCH/2, MULT_Y,
                 16, C_GREY, 'x1.5', IR, Justification.CENTER, 40);
  ml.visible = (m === 1);
}
log.push('mult layers ok');

// ---- 4. play_date 让开 ----
var pd = gPlay.artLayers.getByName('play_date');
pd.textItem.position = [760, 858 + 0.85*pd.textItem.size.value];
log.push('play_date -> 760,858');

// ---- 5. save ----
var out = new File('D:/DeepSeek Harness/workspace1/osu_score_template_v1.psd');
var opt = new PhotoshopSaveOptions();
opt.alphaChannels = true; opt.layers = true; opt.embedColorProfile = true;
doc.saveAs(out, opt, true);
var pf = new File('D:/DeepSeek Harness/workspace1/osu_score_template_v1_skeleton.png');
var po = new PNGSaveOptions(); po.compression = 6; po.interlaced = false;
doc.saveAs(pf, po, true);
log.push('saved + png');

log.join(' | ');
