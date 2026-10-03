var f = new File("D:/DeepSeek Harness/workspace1/osu_score_template_v1.psd");
app.open(f);
var d = app.activeDocument;
var L = [];
function b(o){ try { var x=o.bounds; return [Math.round(x[0]),Math.round(x[1]),Math.round(x[2]),Math.round(x[3])].join(",");} catch(e){ return "n/a"; } }
function walk(set, ind){
  for (var i = 0; i < set.length; i++){
    var l = set[i];
    var t = (l.typename === "LayerSet") ? "GROUP" : (l.kind ? String(l.kind) : "?");
    var line = ind + "[" + i + "] " + l.name + "  <" + t + ">  vis=" + l.visible + "  b=" + b(l);
    if (l.typename === "ArtLayer" && l.kind === LayerKind.TEXT) { try { line += "  txt='" + l.textItem.contents + "' sz=" + l.textItem.size + " font=" + l.textItem.font; } catch(e){} }
    L.push(line);
    if (l.typename === "LayerSet" && ind.length < 4) walk(l.layers, ind + "   ");
  }
}
L.push("ACTIVE: " + d.name + "  " + d.width + "x" + d.height);
walk(d.layers, "");
L.join("\n");
