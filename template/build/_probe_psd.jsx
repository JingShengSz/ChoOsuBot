app.displayDialogs = DialogModes.NO;
var d = app.open(new File("D:/Cho Osu Bot/template/osu_score_template_v1.psd"));
function find(set, name){
  for (var i = 0; i < set.length; i++){
    var l = set[i];
    if (l.name === name) return l;
    if (l.typename === "LayerSet"){ var r = find(l.layers, name); if (r) return r; }
  }
  return null;
}
var L = [];
var board = find(d.layers, "signboard");
for (var i = 0; i < board.layers.length; i++){
  var l = board.layers[i];
  var b = l.bounds;
  L.push("  signboard[" + i + "] " + l.name + "  vis=" + l.visible + "  b=" + [Math.round(b[0]),Math.round(b[1]),Math.round(b[2]),Math.round(b[3])].join(","));
}
var rb = find(d.layers, "rank_block");
L.push("rank_block:");
for (var i = 0; i < rb.layers.length; i++){
  var l = rb.layers[i];
  L.push("  rank[" + i + "] " + l.name + "  vis=" + l.visible);
}
var bg = find(d.layers, "bg");
L.push("bg:");
for (var i = 0; i < bg.layers.length; i++) L.push("  " + bg.layers[i].name + " vis=" + bg.layers[i].visible + " blend=" + bg.layers[i].blendMode);
var mb = find(d.layers, "mods_block");
L.push("mods_block:");
for (var i = 0; i < mb.layers.length; i++) L.push("  " + mb.layers[i].name + " vis=" + mb.layers[i].visible);
var ps = find(d.layers, "player_avatar");
L.push("player_avatar: " + (ps ? ("kind=" + ps.kind + " b=" + ps.bounds) : "MISSING"));
d.close(SaveOptions.DONOTSAVECHANGES);
L.join("\n");
