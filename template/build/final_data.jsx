app.displayDialogs = DialogModes.NO;
var target = null;
for (var q = 0; q < app.documents.length; q++){
  if (app.documents[q].name.indexOf('osu_score_template_v1') === 0) target = app.documents[q];
}
if (!target) throw new Error('template document not open');
app.activeDocument = target;
var LOG = ['active = ' + target.name];

function find(set, name){
  for (var i = 0; i < set.length; i++){
    var l = set[i];
    if (l.name === name) return l;
    if (l.typename === 'LayerSet'){ var r = find(l.layers, name); if (r) return r; }
  }
  return null;
}
function bb(l){ var b = l.bounds; return [Math.round(b[0]),Math.round(b[1]),Math.round(b[2]),Math.round(b[3])].join(','); }
function txt(name, val){
  var l = find(target.layers, name);
  if (!l || l.kind !== LayerKind.TEXT){ LOG.push('MISS TEXT ' + name); return null; }
  l.textItem.contents = val;
  LOG.push(name + ' = "' + val + '"  b=' + bb(l));
  return l;
}
function font(name, f){
  var l = find(target.layers, name);
  if (!l) { LOG.push('MISS ' + name); return; }
  try { l.textItem.font = f; LOG.push(name + ' font -> ' + l.textItem.font); }
  catch(e){ LOG.push('FONT ERR ' + name + ' : ' + e); }
}

/* ---- beatmap (real) ---- */
txt('beatmap_title',      '\u8133\u5473\u564c\u30ea\u30b8\u30c3\u30c9\u30ac\u30fc\u30eb');   /* 脳味噌リジッドガール */
txt('beatmap_artist',     '\u68ee\u7f85\u4e07\u8c61');                                       /* 森羅万象 */
txt('beatmap_difficulty', '[4K] Rigid-Brained Girl');
txt('beatmap_mapper',     'mapped by J-99');
txt('beatmap_id',         '#5493536');
txt('bpm',                '181');
txt('od',                 '8.5');
txt('hp',                 '8.5');
txt('star_rating',        '3.88');
font('beatmap_title',  'YuGothic-Medium');
font('beatmap_artist', 'YuGothic-Medium');

/* ---- player + score (from the score page screenshot) ---- */
txt('player_name',        'F6A8AF');
txt('play_date',          '2026-05-05');
txt('rank_change',        '#165');
txt('pp',                 '148pp');
txt('score',              '984,196');
txt('max_combo',          '2,922x');
txt('map_max_combo',      '2,922x');    /* corrected: real max combo is 2922, not 3243 */
txt('accuracy',           '99.89%');    /* stable scale, computed from the judgements */
txt('accuracy_lazer',     '99.53%');    /* lazer 305-scale, as shown on the page */
txt('count_max',          '2295');
txt('count_300',          '617');
txt('count_200',          '10');
txt('count_100',          '0');
txt('count_50',           '0');
txt('count_miss',         '0');

/* ---- still unknown: total_pp / pp_max keep their placeholders ---- */

/* ---- no mods on this play -> hide the whole mod row ---- */
var MODS = ['mod_1','mod_2','mod_3','mod_4','mod_5','mod_6',
            'mod_1_mult','mod_2_mult','mod_3_mult','mod_4_mult','mod_5_mult','mod_6_mult'];
for (var m = 0; m < MODS.length; m++){
  var ml = find(target.layers, MODS[m]);
  if (ml) ml.visible = false; else LOG.push('MISS ' + MODS[m]);
}
LOG.push('mod row hidden');

/* ---- re-export the info layer (bg group stays hidden from the earlier run) ---- */
var bgGroup = find(target.layers, 'bg');
LOG.push('bg visible = ' + bgGroup.visible);
bgGroup.visible = false;
target.saveAs(new File('D:/DeepSeek Harness/workspace1/_test/out_info.png'), new PNGSaveOptions(), true);
LOG.push('exported out_info.png');

LOG.join('\n');
