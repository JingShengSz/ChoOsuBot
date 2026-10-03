var d = app.activeDocument;
var L = [];
function find(set, name, path){
  for (var i=0;i<set.length;i++){
    var l=set[i];
    var p = path + "/" + l.name;
    if (l.name === name) { L.push("FOUND " + p); return l; }
    if (l.typename === "LayerSet"){ var r = find(l.layers, name, p); if (r) return r; }
  }
  return null;
}
var ov = find(d.layers, "_deco_bg_overlay", "");
L.push("overlay opacity = " + ov.opacity);
L.push("overlay blend   = " + ov.blendMode);
try { L.push("overlay kind    = " + ov.kind); } catch(e){}
var bg = find(d.layers, "beatmap_bg", "");
L.push("beatmap_bg kind = " + bg.kind + " opacity=" + bg.opacity);
L.push("doc mode=" + d.mode + " bits=" + d.bitsPerChannel + " res=" + d.resolution);
L.push("doc_bg vis=" + d.layers[2].name);
L.join("\n");
