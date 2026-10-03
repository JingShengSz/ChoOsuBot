app.displayDialogs = DialogModes.NO;
var target = null;
for (var q = 0; q < app.documents.length; q++){
  if (app.documents[q].name.indexOf("osu_score_template_v1") === 0) target = app.documents[q];
}
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
for (var i = 0; i < root.layers.length; i++) if (root.layers[i].typename === "LayerSet") root.layers[i].visible = true;
find(target.layers, "bg").visible = true;
target.saveAs(new File("D:/DeepSeek Harness/workspace1/_test/preview_full.png"), new PNGSaveOptions(), true);
"exported";
