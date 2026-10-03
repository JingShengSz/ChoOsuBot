app.displayDialogs = DialogModes.NO;
var target = null;
for (var q = 0; q < app.documents.length; q++){
  var n = app.documents[q].name;
  if (n.indexOf('osu_score_template_v1') === 0 && n.indexOf('.psd') > 0) target = app.documents[q];
}
app.activeDocument = target;
var LOG = [];

function find(set, name){
  for (var i = 0; i < set.length; i++){
    var l = set[i];
    if (l.name === name) return l;
    if (l.typename === 'LayerSet'){ var r = find(l.layers, name); if (r) return r; }
  }
  return null;
}
function bb(l){ var b=l.bounds; return [Math.round(b[0]),Math.round(b[1]),Math.round(b[2]),Math.round(b[3])].join(','); }

/* ---- 1. 立绘图层：只留真实存在的 signboard_b，其余占位一律关掉 ---- */
var KEEP = { signboard_b: true, rank_glow: true };
var board = find(target.layers, 'signboard');
for (var i = 0; i < board.layers.length; i++){
  var l = board.layers[i];
  l.visible = !!KEEP[l.name];
  LOG.push((l.visible ? 'show ' : 'hide ') + l.name + '  ' + bb(l));
}

/* ---- 2. 评级配色对齐到 B（蓝），和可见的立绘一致 ---- */
var RANK = 'B', ACCENT = [74, 155, 232];   /* #4A9BE8 */
var SRC = 'D:/DeepSeek Harness/workspace1/_test/rank_svg/';

var bgGroup = find(target.layers, 'bg');
var gradOld = find(target.layers, '_deco_bg_gradient');
var sd = app.open(new File(SRC + 'tint_' + RANK + '.png'));
var grad = sd.layers[0].duplicate(target, ElementPlacement.PLACEATBEGINNING);
sd.close(SaveOptions.DONOTSAVECHANGES);
app.activeDocument = target;
grad.name = '_deco_bg_gradient';
grad.blendMode = BlendMode.NORMAL;
grad.move(bgGroup, ElementPlacement.INSIDE);
var overlay = find(target.layers, '_deco_bg_overlay');
var image   = find(target.layers, 'beatmap_bg');
overlay.move(bgGroup, ElementPlacement.INSIDE);
grad.move(bgGroup, ElementPlacement.INSIDE);
if (gradOld && gradOld != grad) gradOld.remove();
var gord = []; for (var i = 0; i < bgGroup.layers.length; i++) gord.push(bgGroup.layers[i].name);
LOG.push('bg order: ' + gord.join(' / '));

var glowOld = find(target.layers, 'rank_glow');
if (glowOld) glowOld.remove();
var sd2 = app.open(new File(SRC + 'glow_' + RANK + '.png'));
var glow = sd2.layers[0].duplicate(target, ElementPlacement.PLACEATBEGINNING);
sd2.close(SaveOptions.DONOTSAVECHANGES);
app.activeDocument = target;
glow.name = 'rank_glow';
glow.blendMode = BlendMode.SCREEN;
glow.move(board, ElementPlacement.INSIDE);
var kids = board.layers;
if (kids.length > 1) glow.move(kids[kids.length - 1], ElementPlacement.PLACEAFTER);
var bord = []; for (var i = 0; i < board.layers.length; i++) bord.push(board.layers[i].name);
LOG.push('signboard: ' + bord.join(' / '));

var acc = find(target.layers, 'accuracy');
var sc = new SolidColor();
sc.rgb.red = ACCENT[0]; sc.rgb.green = ACCENT[1]; sc.rgb.blue = ACCENT[2];
try { acc.textItem.color = sc; LOG.push('accuracy -> #4A9BE8'); } catch(e){ LOG.push('acc ERR ' + e); }

/* ---- 3. 保存 ---- */
var opt = new PhotoshopSaveOptions();
opt.alphaChannels = true; opt.layers = true; opt.embedColorProfile = true;
target.saveAs(new File('D:/DeepSeek Harness/workspace1/osu_score_template_v1.psd'), opt, true);
var root = target.layerSets.getByName('TEMPLATE_ROOT');
for (var i = 0; i < root.layers.length; i++) if (root.layers[i].typename === 'LayerSet') root.layers[i].visible = true;
find(target.layers, 'bg').visible = true;
target.saveAs(new File('D:/DeepSeek Harness/workspace1/osu_score_template_v1_skeleton.png'), new PNGSaveOptions(), true);
LOG.push('saved');
LOG.join('\n');
