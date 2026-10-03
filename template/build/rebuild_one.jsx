app.displayDialogs = DialogModes.NO;
var target = null;
for (var q = 0; q < app.documents.length; q++){
  if (app.documents[q].name.indexOf("osu_score_template_v1") === 0) target = app.documents[q];
}
if (!target) throw new Error("template not open");
app.activeDocument = target;
function find(set, name){
  for (var i = 0; i < set.length; i++){
    var l = set[i];
    if (l.name === name) return l;
    if (l.typename === "LayerSet"){ var r = find(l.layers, name); if (r) return r; }
  }
  return null;
}
var NAME="accuracy_lazer", PARENT="primary_stats", TEXT="99.53%", FONT="Inter18pt-Bold";
var SIZE=26, HEX="#8C97A9", TX=981, TY=682;
var old = find(target.layers, NAME);
var parent = find(target.layers, PARENT);
if (old) {
  if (old.parent && old.parent.name === PARENT) { old.remove(); }
  else { old.parent.remove(); }
}
var nl = parent.artLayers.add();
nl.kind = LayerKind.TEXT;
nl.name = NAME;
nl.textItem.contents = TEXT;
nl.textItem.font = FONT;
nl.textItem.size = SIZE;
var sc = new SolidColor();
sc.rgb.red   = parseInt(HEX.substr(1,2),16);
sc.rgb.green = parseInt(HEX.substr(3,2),16);
sc.rgb.blue  = parseInt(HEX.substr(5,2),16);
nl.textItem.color = sc;
var b = nl.bounds;
nl.translate(TX - b[0], TY - b[1]);
var b2 = nl.bounds;
NAME + "  parent=" + parent.name + "  b=" + [Math.round(b2[0]),Math.round(b2[1]),Math.round(b2[2]),Math.round(b2[3])].join(",");
