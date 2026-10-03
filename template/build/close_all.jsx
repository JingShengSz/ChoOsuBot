app.displayDialogs = DialogModes.NO;
var L = [];
for (var i = app.documents.length - 1; i >= 0; i--){
  var d = app.documents[i], n = d.name;
  d.close(SaveOptions.DONOTSAVECHANGES);
  L.push("closed " + n);
}
L.join("\n");
