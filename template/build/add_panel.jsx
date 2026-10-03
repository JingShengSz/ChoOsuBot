app.displayDialogs = DialogModes.NO;
var target = null;
for (var q = 0; q < app.documents.length; q++){
  if (app.documents[q].name.indexOf('osu_score_template_v1') === 0) target = app.documents[q];
}
if (!target) throw new Error('template document not open');
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
function bb(l){ var b = l.bounds; return [Math.round(b[0]),Math.round(b[1]),Math.round(b[2]),Math.round(b[3])].join(','); }
function order(set){ var s=[]; for (var i=0;i<set.length;i++) s.push(set[i].name); return s.join(' / '); }

/* move a layer so its INK TOP lands on targetTop, self-correcting */
function moveTop(l, targetTop){
  for (var i = 0; i < 5; i++){
    var b = l.bounds;
    var dy = targetTop - b[1];
    if (Math.abs(dy) < 0.5) break;
    l.translate(0, dy);
  }
  return bb(l);
}

var root = target.layerSets.getByName('TEMPLATE_ROOT');
var bgGroup = find(target.layers, 'bg');
LOG.push('root before : ' + order(root.layers));

/* ---- 1. panel group, sitting directly above bg ---- */
var old = find(target.layers, 'panel');
if (old) old.remove();

var panel = root.layerSets.add();
panel.name = 'panel';
panel.move(bgGroup, ElementPlacement.PLACEBEFORE);
LOG.push('root after  : ' + order(root.layers));

/* ---- 2. glass + border rasters (full-canvas, already at final position) ---- */
var FILES = [['D:/DeepSeek Harness/workspace1/_test/panel_glass.png',  'panel_glass'],
             ['D:/DeepSeek Harness/workspace1/_test/panel_border.png', 'panel_border']];
for (var k = 0; k < FILES.length; k++){
  var sd = app.open(new File(FILES[k][0]));
  var sl = sd.layers[0];
  var nl = sl.duplicate(target, ElementPlacement.PLACEATBEGINNING);
  sd.close(SaveOptions.DONOTSAVECHANGES);
  app.activeDocument = target;
  nl.move(panel, ElementPlacement.INSIDE);
  nl.name = FILES[k][1];
  nl.visible = true;
  LOG.push(FILES[k][1] + ' b=' + bb(nl));
}
LOG.push('panel children: ' + order(panel.layers) + '   (0 = top)');

/* ---- 3. right column: open the 4px PP/SCORE overlap (+16px from SCORE down) ---- */
var SHIFT = ['_deco_score_label', 'score',
             '_deco_combo_label', 'max_combo',
             '_deco_accuracy_label', 'accuracy',
             '_deco_map_combo_label', 'map_max_combo',
             '_deco_accuracy_lazer_label', 'accuracy_lazer'];
for (var m = 0; m < SHIFT.length; m++){
  var l = find(target.layers, SHIFT[m]);
  if (!l){ LOG.push('MISS ' + SHIFT[m]); continue; }
  var before = bb(l);
  var want = l.bounds[1] + 16;
  var after = moveTop(l, want);
  LOG.push(SHIFT[m] + '  ' + before + ' -> ' + after);
}

/* ---- 4. export the full composite (this is what the PSD really produces) ---- */
function setGroups(set, want){
  for (var i = 0; i < set.length; i++) if (set[i].typename === 'LayerSet') set[i].visible = want;
}
setGroups(root.layers, true);
bgGroup.visible = true;
target.saveAs(new File('D:/DeepSeek Harness/workspace1/_test/preview_full.png'), new PNGSaveOptions(), true);
LOG.push('exported preview_full.png');
LOG.join('\n');
