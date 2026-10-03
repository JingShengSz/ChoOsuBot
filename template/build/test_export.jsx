app.displayDialogs = DialogModes.NO;
var target = app.activeDocument;
var root = target.layerSets.getByName('TEMPLATE_ROOT');
var LOG = [];

function find(set, name, path){
  for (var i = 0; i < set.length; i++){
    var l = set[i], p = path + '/' + l.name;
    if (l.name === name) return l;
    if (l.typename === 'LayerSet'){ var r = find(l.layers, name, p); if (r) return r; }
  }
  return null;
}
function setText(name, val){
  var l = find(target.layers, name, '');
  if (!l) { LOG.push('MISS ' + name); return; }
  try {
    l.textItem.contents = val;
    var b = l.bounds;
    LOG.push(name + ' = "' + val + '"  b=' +
             [Math.round(b[0]),Math.round(b[1]),Math.round(b[2]),Math.round(b[3])].join(','));
  } catch(e){ LOG.push('ERR ' + name + ' : ' + e); }
}

/* ---------- 1. real beatmap data (sayobot / bid 5493536) ---------- */
setText('beatmap_title',       'Noumiso Rigid Girl');
setText('beatmap_artist',      'ShinRa-Bansho');
setText('beatmap_difficulty',  'Rigid-Brained Girl');
setText('beatmap_mapper',      'mapped by J-99');
setText('beatmap_id',          '#5493536');
setText('bpm',                 '181');
setText('od',                  '8.5');
setText('hp',                  '8.5');
setText('star_rating',         '3.88');

/* ---------- 2. player / score (PLACEHOLDERS - score page needs sign-in) ---------- */
setText('player_name',         'F6A8AF');
setText('rank_change',         '+1,204');
setText('play_date',           '2026-04-18');
setText('total_pp',            '12,345pp');
setText('pp',                  '512pp');
setText('pp_max',              '612pp');
setText('accuracy',            '99.87%');
setText('accuracy_lazer',      '98.12%');
setText('score',               '1,000,000');
setText('max_combo',           '2,985x');
setText('map_max_combo',       '3,243x');        /* REAL: map max combo */
setText('count_max',           '3104');
setText('count_300',           '128');
setText('count_200',           '8');
setText('count_100',           '2');
setText('count_50',            '0');
setText('count_miss',          '1');

/* ---------- 3. swap in the real background ---------- */
try {
  var src = app.open(new File('D:/DeepSeek Harness/workspace1/_test/bg_raw/Myon.jpg'));
  src.selection.selectAll();
  src.selection.copy();
  src.close(SaveOptions.DONOTSAVECHANGES);
  app.activeDocument = target;

  var oldBg = find(target.layers, 'beatmap_bg', '');
  var bgGroup = find(target.layers, 'bg', '');
  target.activeLayer = oldBg;
  target.paste();
  var newBg = target.activeLayer;
  newBg.name = 'beatmap_bg_test';
  var nb = newBg.bounds;
  LOG.push('pasted bg b=' + [Math.round(nb[0]),Math.round(nb[1]),Math.round(nb[2]),Math.round(nb[3])].join(','));
  if (Math.round(nb[0]) !== 0 || Math.round(nb[1]) !== 0) {
    newBg.translate(-nb[0], -nb[1]);
    nb = newBg.bounds;
    LOG.push('after translate b=' + [Math.round(nb[0]),Math.round(nb[1]),Math.round(nb[2]),Math.round(nb[3])].join(','));
  }
  oldBg.remove();
  newBg.move(bgGroup, ElementPlacement.INSIDE);
  LOG.push('bg swapped');
} catch(e){ LOG.push('BG ERR ' + e); }

/* ---------- 4. bake the SR-3.88 strip + OD/HP bars ---------- */
function swapRaster(layerName, pngPath, x, y){
  try {
    var l = find(target.layers, layerName, '');
    if (!l) { LOG.push('MISS raster ' + layerName); return; }
    var parent = l.parent;
    var s = app.open(new File(pngPath));
    var sl = s.layers[0];
    var sb = sl.bounds;
    var nx = sl.duplicate(target, ElementPlacement.PLACEATBEGINNING);
    s.close(SaveOptions.DONOTSAVECHANGES);
    app.activeDocument = target;
    nx.name = layerName + '_t';
    nx.move(parent, ElementPlacement.INSIDE);
    var b1 = nx.bounds;
    // ink offset inside the source canvas
    nx.translate((x + sb[0]) - b1[0], (y + sb[1]) - b1[1]);
    var b2 = nx.bounds;
    LOG.push(layerName + ' placed b=' + [Math.round(b2[0]),Math.round(b2[1]),Math.round(b2[2]),Math.round(b2[3])].join(','));
    l.remove();
    nx.name = layerName;
  } catch(e){ LOG.push('RASTER ERR ' + layerName + ' : ' + e); }
}
swapRaster('star_strip', 'D:/DeepSeek Harness/workspace1/_test/svg/strip.png', 60, 310);
swapRaster('od_bar',     'D:/DeepSeek Harness/workspace1/_test/svg/od.png',    60, 520);
swapRaster('hp_bar',     'D:/DeepSeek Harness/workspace1/_test/svg/hp.png',    60, 588);

/* ---------- 5. hide the design-only guides ---------- */
['_deco_watermark_hint', '_deco_watermark_guide'].forEach(function(n){
  var l = find(target.layers, n, ''); if (l) l.visible = false;
});
find(target.layers, 'doc_bg', '').visible = false;
find(target.layers, '_deco_guide_safe_margin_60', '').visible = false;

/* ---------- 6. export bg-only, then info-only ---------- */
function setVisible(set, want, path){
  for (var i = 0; i < set.length; i++){
    var l = set[i];
    if (l.typename === 'LayerSet') l.visible = want;
  }
}
setVisible(root.layers, false, '');
find(target.layers, 'bg', '').visible = true;
target.saveAs(new File('D:/DeepSeek Harness/workspace1/_test/out_bg.png'), new PNGSaveOptions(), true);
LOG.push('exported out_bg.png');

setVisible(root.layers, true, '');
find(target.layers, 'bg', '').visible = false;
target.saveAs(new File('D:/DeepSeek Harness/workspace1/_test/out_info.png'), new PNGSaveOptions(), true);
LOG.push('exported out_info.png');

LOG.join('\n');
