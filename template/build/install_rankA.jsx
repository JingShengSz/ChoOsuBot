app.displayDialogs = DialogModes.NO;
var target = null;
for (var q = 0; q < app.documents.length; q++){
  var n = app.documents[q].name;
  if (n.indexOf("osu_score_template_v1") === 0 && n.indexOf(".psd") > 0) target = app.documents[q];
}
if (!target) throw new Error("PSD not open");
app.activeDocument = target;
var LOG = [];
function find(set, name){
  for (var i = 0; i < set.length; i++){
    var l = set[i];
    if (l.name === name) return l;
    if (l.typename === "LayerSet"){ var r = find(l.layers, name); if (r) return r; }
  }
  return null;
}
function bb(l){ var b=l.bounds; return [Math.round(b[0]),Math.round(b[1]),Math.round(b[2]),Math.round(b[3])].join(","); }
var board = find(target.layers, "signboard");

/* --- 1. 放进 signboard_a --- */
var oldA = find(target.layers, "signboard_a");
var sd = app.open(new File("D:/DeepSeek Harness/workspace1/_test/sb_a/signboard_A.png"));
var aLayer = sd.layers[0].duplicate(target, ElementPlacement.PLACEATBEGINNING);
sd.close(SaveOptions.DONOTSAVECHANGES);
app.activeDocument = target;
aLayer.name = "signboard_a";
aLayer.move(board, ElementPlacement.INSIDE);
if (oldA && oldA != aLayer) oldA.remove();
LOG.push("signboard_a " + bb(aLayer));

/* --- 2. 只显示 signboard_a + rank_glow --- */
var KEEP = { signboard_a: true, rank_glow: true };
for (var i = 0; i < board.layers.length; i++){
  var l = board.layers[i];
  l.visible = !!KEEP[l.name];
  if (l.visible) LOG.push("show " + l.name + " " + bb(l));
}
/* rank_glow 保持在最底 */
var glow = find(target.layers, "rank_glow");
var kids = board.layers;
if (kids.length > 1) glow.move(kids[kids.length - 1], ElementPlacement.PLACEAFTER);

/* --- 3. 换成 A 的配色 (#6BC24A) --- */
var RANK = "A", SRC = "D:/DeepSeek Harness/workspace1/_test/rank_svg/";
var bgGroup = find(target.layers, "bg");
var gradOld = find(target.layers, "_deco_bg_gradient");
var s1 = app.open(new File(SRC + "tint_" + RANK + ".png"));
var grad = s1.layers[0].duplicate(target, ElementPlacement.PLACEATBEGINNING);
s1.close(SaveOptions.DONOTSAVECHANGES);
app.activeDocument = target;
grad.name = "_deco_bg_gradient";
grad.blendMode = BlendMode.NORMAL;
grad.move(bgGroup, ElementPlacement.INSIDE);
var ov = find(target.layers, "_deco_bg_overlay");
ov.move(bgGroup, ElementPlacement.INSIDE);
grad.move(bgGroup, ElementPlacement.INSIDE);
if (gradOld && gradOld != grad) gradOld.remove();

var glowOld = find(target.layers, "rank_glow");
if (glowOld) glowOld.remove();
var s2 = app.open(new File(SRC + "glow_" + RANK + ".png"));
var gl2 = s2.layers[0].duplicate(target, ElementPlacement.PLACEATBEGINNING);
s2.close(SaveOptions.DONOTSAVECHANGES);
app.activeDocument = target;
gl2.name = "rank_glow";
gl2.blendMode = BlendMode.SCREEN;
gl2.move(board, ElementPlacement.INSIDE);
var k2 = board.layers;
if (k2.length > 1) gl2.move(k2[k2.length - 1], ElementPlacement.PLACEAFTER);
LOG.push("rank_glow " + bb(gl2) + " blend=" + gl2.blendMode);

var acc = find(target.layers, "accuracy");
var sc = new SolidColor();
sc.rgb.red = 107; sc.rgb.green = 194; sc.rgb.blue = 74;   /* #6BC24A */
try { acc.textItem.color = sc; LOG.push("accuracy -> #6BC24A"); } catch(e){ LOG.push("acc ERR " + e); }

/* --- 4. 保存 --- */
var opt = new PhotoshopSaveOptions();
opt.alphaChannels = true; opt.layers = true; opt.embedColorProfile = true;
target.saveAs(new File("D:/DeepSeek Harness/workspace1/osu_score_template_v1.psd"), opt, true);
var root = target.layerSets.getByName("TEMPLATE_ROOT");
for (var i = 0; i < root.layers.length; i++) if (root.layers[i].typename === "LayerSet") root.layers[i].visible = true;
find(target.layers, "bg").visible = true;
target.saveAs(new File("D:/DeepSeek Harness/workspace1/osu_score_template_v1_skeleton.png"), new PNGSaveOptions(), true);
LOG.push("saved");
LOG.join("\n");
