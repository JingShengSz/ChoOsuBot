/* The pasted background was moved INSIDE the bg group, which puts it at the TOP --
   so it covered _deco_bg_overlay and no dimming was ever applied.
   Restore the intended stack: _deco_bg_gradient (top) / _deco_bg_overlay / beatmap_bg. */
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
function order(g){
  var s = [];
  for (var i = 0; i < g.layers.length; i++) s.push(g.layers[i].name);
  return s.join(' / ');
}

var bgGroup = find(target.layers, 'bg');
LOG.push('BEFORE  ' + order(bgGroup));

var gradient = find(target.layers, '_deco_bg_gradient');
var overlay  = find(target.layers, '_deco_bg_overlay');
var bgImage  = find(target.layers, 'beatmap_bg');

/* moving to INSIDE puts the layer at index 0 (top); do it in reverse order */
overlay.move(bgGroup, ElementPlacement.INSIDE);
gradient.move(bgGroup, ElementPlacement.INSIDE);
LOG.push('AFTER   ' + order(bgGroup));

bgImage.visible  = true;
overlay.visible  = true;
gradient.visible = true;

/* ---- export at 75% and at 30% so both can be compared ---- */
var root = target.layerSets.getByName('TEMPLATE_ROOT');
function setGroups(set, want){
  for (var i = 0; i < set.length; i++){
    if (set[i].typename === 'LayerSet') set[i].visible = want;
  }
}
setGroups(root.layers, false);
bgGroup.visible = true;

overlay.opacity = 75;
target.saveAs(new File('D:/DeepSeek Harness/workspace1/_test/out_bg75.png'), new PNGSaveOptions(), true);
LOG.push('exported out_bg75.png at overlay ' + overlay.opacity + '%');

overlay.opacity = 30;
target.saveAs(new File('D:/DeepSeek Harness/workspace1/_test/out_bg30.png'), new PNGSaveOptions(), true);
LOG.push('exported out_bg30.png at overlay ' + overlay.opacity + '%');

overlay.opacity = 75;
setGroups(root.layers, true);
bgGroup.visible = false;
target.saveAs(new File('D:/DeepSeek Harness/workspace1/_test/out_info.png'), new PNGSaveOptions(), true);
LOG.push('exported out_info.png; overlay left at ' + overlay.opacity + '%');
LOG.join('\n');
