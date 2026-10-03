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
var N = ["_deco_total_pp_label","total_pp","_deco_pp_label","pp","_deco_pp_max_label","pp_max",
         "_deco_score_label","score","_deco_combo_label","max_combo","_deco_map_combo_label",
         "map_max_combo","_deco_accuracy_label","accuracy","_deco_accuracy_lazer_label","accuracy_lazer"];
var L = [];
for (var i = 0; i < N.length; i++){
  var l = find(target.layers, N[i]);
  var b = l.bounds;
  L.push(N[i] + "  " + [Math.round(b[0]),Math.round(b[1]),Math.round(b[2]),Math.round(b[3])].join(","));
}
L.join("\n");
