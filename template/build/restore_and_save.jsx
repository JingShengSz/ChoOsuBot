/* Restore the template's placeholder state, swap the raster placeholders back to
   the demo values (SR 7.42 / OD 9.0 / HP 6.0), then save the PSD. */
app.displayDialogs = DialogModes.NO;
var target = null;
for (var q = 0; q < app.documents.length; q++){
  if (app.documents[q].name.indexOf('osu_score_template_v1') === 0) target = app.documents[q];
}
if (!target) throw new Error('template not open');
app.activeDocument = target;
var LOG = [];

function find(set, name){
  for (var i = 0; i < set.length; i++){
    var l = set[i];
    if (l.name === name) return l;
    if (l.typename === 'LayerSet'){ var r = find(l.layers, name); if (r) return r; }
  }
  return null;
}
function txt(name, v){
  var l = find(target.layers, name);
  if (!l){ LOG.push('MISS ' + name); return; }
  l.textItem.contents = v;
}
function font(name, f){
  var l = find(target.layers, name);
  if (l) try { l.textItem.font = f; } catch(e){ LOG.push('font err ' + name); }
}

/* ---- 1. placeholder text ---- */
txt('beatmap_title',      'FREEDOM DiVE');
txt('beatmap_artist',     'xi');
txt('beatmap_difficulty', 'FOUR DIMENSIONS');
txt('beatmap_mapper',     'mapped by Nakagawa-Kanon');
txt('beatmap_id',         '#1234567');
txt('bpm',                '222.22');
txt('od',                 '9.0');
txt('hp',                 '6.0');
txt('star_rating',        '7.42');
font('beatmap_title',  'Inter18pt-Medium');
font('beatmap_artist', 'Inter18pt-Medium');
txt('player_name',        'Cookiezi');
txt('rank_change',        '+1,204');
txt('play_date',          '2026-10-02');
txt('total_pp',           '12,345pp');
txt('pp',                 '512pp');
txt('pp_max',             '612pp');
txt('accuracy',           '99.87%');
txt('accuracy_lazer',     '98.12%');
txt('score',              '1,000,000');
txt('max_combo',          '1,847x');
txt('map_max_combo',      '2,109x');
txt('count_max',          '2103');
txt('count_300',          '1847');
txt('count_200',          '0');
txt('count_100',          '12');
txt('count_50',           '2');
txt('count_miss',         '0');

/* ---- 2. star_rating stays hidden, mods come back ---- */
var sr = find(target.layers, 'star_rating'); if (sr) sr.visible = false;
var MODS = ['mod_1','mod_2','mod_3','mod_4','mod_5','mod_6'];
for (var m = 0; m < MODS.length; m++){ var ml = find(target.layers, MODS[m]); if (ml) ml.visible = true; }
var mm = find(target.layers, 'mod_2_mult'); if (mm) mm.visible = true;

/* ---- 3. raster placeholders: strip 7.42, OD 9.0, HP 6.0 ---- */
function swapRaster(layerName, pngPath, x, y){
  var l = find(target.layers, layerName);
  if (!l){ LOG.push('MISS raster ' + layerName); return; }
  var parent = l.parent;
  var s = app.open(new File(pngPath));
  var sl = s.layers[0];
  var sb = sl.bounds;
  var nl = sl.duplicate(target, ElementPlacement.PLACEATBEGINNING);
  s.close(SaveOptions.DONOTSAVECHANGES);
  app.activeDocument = target;
  nl.move(parent, ElementPlacement.INSIDE);
  nl.name = layerName;
  var b = nl.bounds;
  nl.translate(-((x + sb[0]) - b[0]), -((y + sb[1]) - b[1]));
  l.remove();
  var b2 = nl.bounds;
  LOG.push(layerName + '  ' + [Math.round(b2[0]),Math.round(b2[1]),Math.round(b2[2]),Math.round(b2[3])].join(','));
}
swapRaster('star_strip', 'D:/DeepSeek Harness/workspace1/_test/svg/ph_strip.png', 60, 310);
swapRaster('od_bar',     'D:/DeepSeek Harness/workspace1/_test/svg/ph_od.png',    60, 520);
swapRaster('hp_bar',     'D:/DeepSeek Harness/workspace1/_test/svg/ph_hp.png',    60, 588);

/* ---- 4. placeholder background ---- */
var oldBg = find(target.layers, 'beatmap_bg');
var bgGroup = find(target.layers, 'bg');
var s2 = app.open(new File('D:/DeepSeek Harness/workspace1/_test/beatmap_bg_placeholder.png'));
var s2l = s2.layers[0];
var nb = s2l.duplicate(target, ElementPlacement.PLACEATBEGINNING);
s2.close(SaveOptions.DONOTSAVECHANGES);
app.activeDocument = target;
nb.name = 'beatmap_bg';
nb.move(bgGroup, ElementPlacement.INSIDE);
oldBg.remove();
/* re-assert the stack: gradient / overlay / beatmap_bg */
var gradient = find(target.layers, '_deco_bg_gradient');
var overlay  = find(target.layers, '_deco_bg_overlay');
var img      = find(target.layers, 'beatmap_bg');
overlay.move(bgGroup, ElementPlacement.INSIDE);
gradient.move(bgGroup, ElementPlacement.INSIDE);
var ord = [];
for (var i = 0; i < bgGroup.layers.length; i++) ord.push(bgGroup.layers[i].name);
LOG.push('bg order: ' + ord.join(' / '));
LOG.push('overlay opacity: ' + overlay.opacity);

/* ---- 5. save ---- */
var out = new File('D:/DeepSeek Harness/workspace1/osu_score_template_v1.psd');
var opt = new PhotoshopSaveOptions();
opt.alphaChannels = true; opt.layers = true; opt.embedColorProfile = true;
target.saveAs(out, opt, true);
LOG.push('SAVED ' + out.fsName);

var root = target.layerSets.getByName('TEMPLATE_ROOT');
for (var i = 0; i < root.layers.length; i++) if (root.layers[i].typename === 'LayerSet') root.layers[i].visible = true;
target.saveAs(new File('D:/DeepSeek Harness/workspace1/osu_score_template_v1_skeleton.png'), new PNGSaveOptions(), true);
LOG.push('SAVED skeleton png');

var order = [];
for (var i = 0; i < root.layers.length; i++) order.push(root.layers[i].name);
LOG.push('TEMPLATE_ROOT (0 = top): ' + order.join(' / '));
LOG.join('\n');
