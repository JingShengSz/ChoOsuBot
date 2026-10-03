var out = [];
try { out.push("docs=" + app.documents.length); } catch(e) { out.push("ERR " + e); }
for (var i = 0; i < app.documents.length; i++) {
  var d = app.documents[i];
  out.push(i + ": " + d.name + " " + d.width + "x" + d.height + " saved=" + d.saved + " active=" + (d == app.activeDocument));
}
out.join("\n");
