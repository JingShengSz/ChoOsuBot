app.displayDialogs = DialogModes.NO;
var doc = app.activeDocument;
var root = doc.layerSets.getByName('TEMPLATE_ROOT');
var gStats = root.layerSets.getByName('beatmap_stats');
var gInfo  = root.layerSets.getByName('beatmap_info');
var log = [];

var C_BORDER='2E3543', C_BLOCK='3C4453';
var IR='Inter18pt-Regular', IM='Inter18pt-Medium', IB='Inter18pt-Bold';
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
function setTxt(g,name,x,y,size,font,just){
  var l = g.artLayers.getByName(name);
  var t = l.textItem;
  if (size) t.size = new UnitValue(size,'px');
  if (font) t.font = font;
  if (just) t.justification = just;
  t.position = [x, y + 0.85 * t.size.value];
  return l;
}
function rm(g,name){ try { g.artLayers.getByName(name).remove(); return true; } catch(e){ return false; } }
var JL=Justification.LEFT;

// ---- 1. stale dividers from the old horizontal beatmap block ----
var g = [];
if (rm(gInfo,'_deco_info_divider'))   g.push('_deco_info_divider');
if (rm(gInfo,'_deco_info_divider_2')) g.push('_deco_info_divider_2');
log.push('removed: ' + g.join(','));

// ---- 2. left column: stack the 8 fields down the full height ----
setTxt(gInfo,'beatmap_title',      60,  70, 36, IM, JL);
setTxt(gInfo,'beatmap_artist',     60, 130, 28, IM, JL);
setTxt(gInfo,'beatmap_difficulty', 60, 180, 22, IM, JL);   // was left floating mid-canvas
setTxt(gInfo,'beatmap_mapper',     60, 218, 18, IR, JL);
setTxt(gInfo,'beatmap_id',         60, 248, 18, IR, JL);
repaint(gStats,'_deco_left_divider', 60, 288, 600, 2, C_BORDER);

// attribute icons: 2x2 -> 1x4 vertical, so the column fills its height
repaint(gStats,'_deco_attr_star', 60, 320, 32, 32, C_BLOCK);
repaint(gStats,'_deco_attr_bpm',  60, 388, 32, 32, C_BLOCK);
repaint(gStats,'_deco_attr_od',   60, 456, 32, 32, C_BLOCK);
repaint(gStats,'_deco_attr_hp',   60, 524, 32, 32, C_BLOCK);
setTxt(gStats,'star_rating', 106, 316, 32, IB, JL);
setTxt(gStats,'bpm',         106, 384, 32, IB, JL);
setTxt(gStats,'od',          106, 452, 32, IB, JL);
setTxt(gStats,'hp',          106, 520, 32, IB, JL);
log.push('left column stacked');

// ---- 3. the star icon now carries the "star" meaning -> drop the asterisk ----
try { gStats.artLayers.getByName('star_rating').textItem.contents = '7.42'; } catch(e){}
try { gStats.artLayers.getByName('bpm').textItem.contents = '222.22'; } catch(e){}
log.push('placeholder text trimmed');

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
