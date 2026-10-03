app.displayDialogs = DialogModes.NO;
/* Dump exact INK bounds for every text layer, plus the bg-overlay opacity.
   ExtendScript has no JSON object, so emit a plain line-based sidecar that
   Python merges into layer_mapping.json. */
var target = null;
for (var q = 0; q < app.documents.length; q++){
  var n = app.documents[q].name;
  if (n.indexOf("osu_score_template_v1") === 0 && n.indexOf(".psd") > 0) target = app.documents[q];
}
if (!target) throw new Error("模板 PSD 没打开");
app.activeDocument = target;

function find(set, name){
  for (var i = 0; i < set.length; i++){
    var l = set[i];
    if (l.name === name) return l;
    if (l.typename === "LayerSet"){ var r = find(l.layers, name); if (r) return r; }
  }
  return null;
}

var ROWS = [];
var JUST = [];
function walk(set){
  for (var i = 0; i < set.length; i++){
    var l = set[i];
    if (l.typename === "LayerSet"){ walk(l.layers); continue; }
    if (l.kind !== LayerKind.TEXT) continue;
    var b = l.bounds;
    var j = String(l.textItem.justification);
    var jc = j.indexOf("CENTER") >= 0 ? "center" : (j.indexOf("RIGHT") >= 0 ? "right" : "left");
    ROWS.push(l.name + "|" + Math.round(b[0]) + "|" + Math.round(b[1]) + "|" +
              Math.round(b[2]) + "|" + Math.round(b[3]) + "|" + jc);
  }
}
walk(target.layers);
ROWS.push("#textLayers=" + ROWS.length);

/* 背景压暗层的不透明度 */
var ov = find(target.layers, "_deco_bg_overlay");
ROWS.push("#overlayOpacity=" + ov.opacity);
var gr = find(target.layers, "_deco_bg_gradient");
ROWS.push("#gradientBlend=" + gr.blendMode);
var glow = find(target.layers, "rank_glow");
ROWS.push("#glowBlend=" + (glow ? glow.blendMode : "none"));

/* 底板几何 */
var pg = find(target.layers, "panel_glass");
var pb = find(target.layers, "panel_border");
if (pg) { var b1 = pg.bounds;
  ROWS.push("#panelGlass=" + [Math.round(b1[0]),Math.round(b1[1]),Math.round(b1[2]),Math.round(b1[3])].join(",")); }
if (pb) { var b2 = pb.bounds;
  ROWS.push("#panelBorder=" + [Math.round(b2[0]),Math.round(b2[1]),Math.round(b2[2]),Math.round(b2[3])].join(",")); }

var f = new File("D:/Cho Osu Bot/scratch/ink_bounds.txt");
f.encoding = "UTF-8";
f.open("w");
f.write(ROWS.join("\n"));
f.close();
"saved " + ROWS.length + " rows to ink_bounds.txt";
