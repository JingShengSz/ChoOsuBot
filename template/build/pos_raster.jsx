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
var l = find(target.layers, "hp_bar");
var b0 = l.bounds;
var was = [Math.round(b0[0]),Math.round(b0[1])].join(",");
l.translate(-(60 - b0[0]), -(588 - b0[1]));
var b1 = l.bounds;
"hp_bar|" + was + "|" + [Math.round(b1[0]),Math.round(b1[1]),Math.round(b1[2]),Math.round(b1[3])].join(",");
