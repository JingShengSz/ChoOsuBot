app.displayDialogs = DialogModes.NO;
var f = new File("D:/Cho Osu Bot/template/osu_score_template_v1.psd");
var d = app.open(f);
var L = [];
L.push("opened " + d.name + "  " + Math.round(d.width) + "x" + Math.round(d.height));
var root = d.layerSets.getByName("TEMPLATE_ROOT");
var names = [];
for (var i = 0; i < root.layers.length; i++) names.push(root.layers[i].name);
L.push("groups: " + names.join(" / "));
function find(set, name){
  for (var i = 0; i < set.length; i++){
    var l = set[i];
    if (l.name === name) return l;
    if (l.typename === "LayerSet"){ var r = find(l.layers, name); if (r) return r; }
  }
  return null;
}
var b = find(d.layers, "signboard_a"); var g = find(d.layers, "rank_glow");
L.push("signboard_a vis=" + (b ? b.visible : "MISSING") + "   rank_glow vis=" + (g ? g.visible : "MISSING"));
L.push("path: " + d.path.fsName);
L.join("\n");
