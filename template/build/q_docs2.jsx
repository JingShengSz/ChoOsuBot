app.displayDialogs = DialogModes.NO;
var L = [];
L.push("docs=" + app.documents.length);
for (var i = 0; i < app.documents.length; i++){
  var d = app.documents[i];
  L.push("  " + d.name + "  " + Math.round(d.width) + "x" + Math.round(d.height) + "  layers=" + d.layers.length + "  active=" + (d == app.activeDocument));
}
L.join("\n");
