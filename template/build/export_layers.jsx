app.displayDialogs = DialogModes.NO;
var target = null;
for (var q = 0; q < app.documents.length; q++){
  var n = app.documents[q].name;
  if (n.indexOf("osu_score_template_v1") === 0 && n.indexOf(".psd") > 0) target = app.documents[q];
}
if (!target) throw new Error("PSD not open");
app.activeDocument = target;
function find(set, name){
  for (var i = 0; i < set.length; i++){
    var l = set[i];
    if (l.name === name) return l;
    if (l.typename === "LayerSet"){ var r = find(l.layers, name); if (r) return r; }
  }
  return null;
}
var root = target.layerSets.getByName("TEMPLATE_ROOT");
function setGroups(set, want){
  for (var i = 0; i < set.length; i++) if (set[i].typename === "LayerSet") set[i].visible = want;
}
setGroups(root.layers, true);
find(target.layers, "bg").visible = false;
target.saveAs(new File("D:/DeepSeek Harness/workspace1/_test/layer_info.png"), new PNGSaveOptions(), true);
setGroups(root.layers, true);
find(target.layers, "bg").visible = true;
"exported layer_info.png; active=" + target.name;
