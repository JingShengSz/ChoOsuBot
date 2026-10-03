/* ArtLayer.translate() is broken on this build: a +1px request moved _deco_pp_label
   by -63px, and the self-correcting loop then diverged to y=-1518.
   Recover and lay out with ActionManager 'move' / 'Ofst' instead, verifying each step. */
app.displayDialogs = DialogModes.NO;
var target = null;
for (var q = 0; q < app.documents.length; q++){
  if (app.documents[q].name.indexOf('osu_score_template_v1') === 0) target = app.documents[q];
}
if (!target) throw new Error('template document not open');
app.activeDocument = target;
var LOG = [];
var cTID = charIDToTypeID;

function find(set, name){
  for (var i = 0; i < set.length; i++){
    var l = set[i];
    if (l.name === name) return l;
    if (l.typename === 'LayerSet'){ var r = find(l.layers, name); if (r) return r; }
  }
  return null;
}
function bb(l){ var b=l.bounds; return [Math.round(b[0]),Math.round(b[1]),Math.round(b[2]),Math.round(b[3])].join(','); }

function amMove(l, dx, dy){
  target.activeLayer = l;
  var d1 = new ActionDescriptor();
  var ref = new ActionReference();
  ref.putEnumerated(cTID('Lyr '), cTID('Ordn'), cTID('Trgt'));
  d1.putReference(cTID('null'), ref);
  var d2 = new ActionDescriptor();
  d2.putUnitDouble(cTID('Hrzn'), cTID('#Pxl'), dx);
  d2.putUnitDouble(cTID('Vrtc'), cTID('#Pxl'), dy);
  d1.putObject(cTID('T   '), cTID('Ofst'), d2);
  executeAction(cTID('move'), d1, DialogModes.NO);
}
function landTop(l, t){
  for (var i = 0; i < 4; i++){
    var dy = t - l.bounds[1];
    if (Math.abs(dy) < 0.5) return true;
    amMove(l, 0, dy);
  }
  return Math.abs(t - l.bounds[1]) < 0.5;
}

var LAYOUT = [
  ['_deco_total_pp_label',       294],
  ['total_pp',                   315],
  ['_deco_pp_label',             371],
  ['pp',                         395],
  ['_deco_pp_max_label',         371],
  ['pp_max',                     395],
  ['_deco_score_label',          476],
  ['score',                      500],
  ['_deco_combo_label',          567],
  ['max_combo',                  591],
  ['_deco_map_combo_label',      567],
  ['map_max_combo',              591],
  ['_deco_accuracy_label',       658],
  ['accuracy',                   682],
  ['_deco_accuracy_lazer_label', 658],
  ['accuracy_lazer',             682]
];

for (var i = 0; i < LAYOUT.length; i++){
  var l = find(target.layers, LAYOUT[i][0]);
  if (!l){ LOG.push('MISS ' + LAYOUT[i][0]); continue; }
  var was = Math.round(l.bounds[1]);
  var ok = landTop(l, LAYOUT[i][1]);
  LOG.push((ok ? 'ok   ' : 'BAD  ') + LAYOUT[i][0] + '  y ' + was + ' -> ' + bb(l));
}

LOG.push('--- final rhythm (value bottom -> next label top) ---');
var SEQ = ['_deco_total_pp_label','total_pp','_deco_pp_label','pp','_deco_score_label','score',
           '_deco_combo_label','max_combo','_deco_accuracy_label','accuracy'];
for (var s = 1; s + 1 < SEQ.length; s += 2){
  var a = find(target.layers, SEQ[s]), b = find(target.layers, SEQ[s+1]);
  if (a && b) LOG.push('  ' + SEQ[s] + ' btm ' + Math.round(a.bounds[3]) +
                       ' -> ' + SEQ[s+1] + ' top ' + Math.round(b.bounds[1]) +
                       '   gap ' + Math.round(b.bounds[1] - a.bounds[3]));
}

var root = target.layerSets.getByName('TEMPLATE_ROOT');
function setGroups(set, want){
  for (var i = 0; i < set.length; i++) if (set[i].typename === 'LayerSet') set[i].visible = want;
}
setGroups(root.layers, true);
find(target.layers, 'bg').visible = true;
target.saveAs(new File('D:/DeepSeek Harness/workspace1/_test/preview_full.png'), new PNGSaveOptions(), true);
LOG.push('exported preview_full.png');
LOG.join('\n');
