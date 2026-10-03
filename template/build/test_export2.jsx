app.displayDialogs = DialogModes.NO;
var target = app.activeDocument;
var root = target.layerSets.getByName('TEMPLATE_ROOT');
var LOG = [];

function find(set, name){
  for (var i = 0; i < set.length; i++){
    var l = set[i];
    if (l.name === name) return l;
    if (l.typename === 'LayerSet'){ var r = find(l.layers, name); if (r) return r; }
  }
  return null;
}
function bb(l){ var b = l.bounds; return [Math.round(b[0]),Math.round(b[1]),Math.round(b[2]),Math.round(b[3])].join(','); }

/* --- normalise the swapped background name --- */
var bgLayer = find(target.layers, 'beatmap_bg');
if (!bgLayer) {
  var t = find(target.layers, 'beatmap_bg_test');
  if (t) { t.name = 'beatmap_bg'; bgLayer = t; LOG.push('renamed beatmap_bg_test -> beatmap_bg'); }
}
LOG.push('beatmap_bg = ' + (bgLayer ? bb(bgLayer) : 'MISSING'));

var PROBE = ['star_strip','od_bar','hp_bar','bpm','od','hp','beatmap_title','beatmap_artist',
             'beatmap_difficulty','beatmap_mapper','beatmap_id','player_name','score','max_combo',
             'map_max_combo','count_max','count_300','count_miss','accuracy','pp'];
for (var q = 0; q < PROBE.length; q++){
  var pl = find(target.layers, PROBE[q]);
  LOG.push(PROBE[q] + ' b=' + (pl ? bb(pl) : 'MISSING'));
}

/* --- hide design-only guides --- */
var names = ['_deco_watermark_hint','_deco_watermark_guide','doc_bg','_deco_guide_safe_margin_60'];
for (var i = 0; i < names.length; i++){
  var l = find(target.layers, names[i]);
  if (l) { l.visible = false; LOG.push('hid ' + names[i]); } else { LOG.push('miss ' + names[i]); }
}

/* --- export bg only --- */
function setGroups(set, want){
  for (var i = 0; i < set.length; i++){
    var l = set[i];
    if (l.typename === 'LayerSet') l.visible = want;
  }
}
setGroups(root.layers, false);
find(target.layers, 'bg').visible = true;
target.saveAs(new File('D:/DeepSeek Harness/workspace1/_test/out_bg.png'), new PNGSaveOptions(), true);
LOG.push('exported out_bg.png  ' + target.width + 'x' + target.height);

/* --- export info only --- */
setGroups(root.layers, true);
find(target.layers, 'bg').visible = false;
target.saveAs(new File('D:/DeepSeek Harness/workspace1/_test/out_info.png'), new PNGSaveOptions(), true);
LOG.push('exported out_info.png');

LOG.join('\n');
