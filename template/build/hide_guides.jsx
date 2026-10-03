app.displayDialogs = DialogModes.NO;
var target = null;
for (var q = 0; q < app.documents.length; q++){
  if (app.documents[q].name.indexOf('osu_score_template_v1') === 0) target = app.documents[q];
}
app.activeDocument = target;
function find(set, name){
  for (var i = 0; i < set.length; i++){
    var l = set[i];
    if (l.name === name) return l;
    if (l.typename === 'LayerSet'){ var r = find(l.layers, name); if (r) return r; }
  }
  return null;
}
var L = [];
var names = ['_deco_watermark_hint','_deco_watermark_guide'];
for (var i = 0; i < names.length; i++){
  var l = find(target.layers, names[i]);
  if (l) { l.visible = false; L.push('hid ' + names[i] + ' -> now ' + l.visible); }
}
var root = target.layerSets.getByName('TEMPLATE_ROOT');
function setGroups(set, want){
  for (var i = 0; i < set.length; i++) if (set[i].typename === 'LayerSet') set[i].visible = want;
}
var bgGroup = find(target.layers, 'bg');
setGroups(root.layers, true); bgGroup.visible = false;
target.saveAs(new File('D:/DeepSeek Harness/workspace1/_test/out_info.png'), new PNGSaveOptions(), true);
L.push('exported out_info.png; overlay=' + find(target.layers,'_deco_bg_overlay').opacity);
L.join('\n');
