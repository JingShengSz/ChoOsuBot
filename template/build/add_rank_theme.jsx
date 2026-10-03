/* 把评级配色装进模板：背景染色 + 立绘辉光。
   默认装 S 的（模板当前可见的立绘就是 signboard_b/s）。
   这两个都是整张 1920x1080 的位图，靠 duplicate 落位，不需要 translate。 */
app.displayDialogs = DialogModes.NO;
var target = null;
for (var q = 0; q < app.documents.length; q++){
  var n = app.documents[q].name;
  if (n.indexOf('osu_score_template_v1') === 0 && n.indexOf('.psd') > 0) target = app.documents[q];
}
if (!target) throw new Error('PSD not open');
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
function order(g){ var s=[]; for (var i=0;i<g.layers.length;i++) s.push(g.layers[i].name); return s.join(' / '); }
function bb(l){ var b=l.bounds; return [Math.round(b[0]),Math.round(b[1]),Math.round(b[2]),Math.round(b[3])].join(','); }

var RANK = 'S';
var SRC = 'D:/DeepSeek Harness/workspace1/_test/rank_svg/';

/* ---- 1. 背景染色：替换空的 _deco_bg_gradient ---- */
var bgGroup = find(target.layers, 'bg');
var oldGrad = find(target.layers, '_deco_bg_gradient');
var sd = app.open(new File(SRC + 'tint_' + RANK + '.png'));
var nl = sd.layers[0].duplicate(target, ElementPlacement.PLACEATBEGINNING);
sd.close(SaveOptions.DONOTSAVECHANGES);
app.activeDocument = target;
nl.name = '_deco_bg_gradient';
nl.blendMode = BlendMode.NORMAL;
nl.move(bgGroup, ElementPlacement.INSIDE);
var gradient = nl;
/* 重新压好 bg 组顺序：渐变 / 压暗 / 背景图 */
var overlay = find(target.layers, '_deco_bg_overlay');
var img     = find(target.layers, 'beatmap_bg');
overlay.move(bgGroup, ElementPlacement.INSIDE);
gradient.move(bgGroup, ElementPlacement.INSIDE);
if (oldGrad && oldGrad != gradient) oldGrad.remove();
LOG.push('bg order   : ' + order(bgGroup));
LOG.push('_deco_bg_gradient ' + bb(gradient) + '  blend=' + gradient.blendMode);

/* ---- 2. 立绘辉光：垫在 signboard 组最底层 ---- */
var board = find(target.layers, 'signboard');
var oldGlow = find(target.layers, 'rank_glow');
if (oldGlow) oldGlow.remove();
var sd2 = app.open(new File(SRC + 'glow_' + RANK + '.png'));
var g2 = sd2.layers[0].duplicate(target, ElementPlacement.PLACEATBEGINNING);
sd2.close(SaveOptions.DONOTSAVECHANGES);
app.activeDocument = target;
g2.name = 'rank_glow';
g2.blendMode = BlendMode.SCREEN;
g2.move(board, ElementPlacement.INSIDE);
/* 移到组的最底层 */
var kids = board.layers;
if (kids.length > 1) g2.move(kids[kids.length - 1], ElementPlacement.PLACEAFTER);
LOG.push('signboard  : ' + order(board));
LOG.push('rank_glow  ' + bb(g2) + '  blend=' + g2.blendMode);

/* ---- 3. 强调色：准确率数字 ---- */
var acc = find(target.layers, 'accuracy');
if (acc){
  var sc = new SolidColor();
  sc.rgb.red = 255; sc.rgb.green = 185; sc.rgb.blue = 61;   /* S = #FFB93D */
  try { acc.textItem.color = sc; LOG.push('accuracy color -> #FFB93D'); }
  catch(e){ LOG.push('accuracy color ERR ' + e); }
}

/* ---- 4. 保存 ---- */
var opt = new PhotoshopSaveOptions();
opt.alphaChannels = true; opt.layers = true; opt.embedColorProfile = true;
target.saveAs(new File('D:/DeepSeek Harness/workspace1/osu_score_template_v1.psd'), opt, true);
var root = target.layerSets.getByName('TEMPLATE_ROOT');
for (var i = 0; i < root.layers.length; i++) if (root.layers[i].typename === 'LayerSet') root.layers[i].visible = true;
find(target.layers, 'bg').visible = true;
target.saveAs(new File('D:/DeepSeek Harness/workspace1/osu_score_template_v1_skeleton.png'), new PNGSaveOptions(), true);
LOG.push('saved psd + skeleton');
LOG.join('\n');
