/* 往模板加一个 server_tag 文字层 —— 卡片上区分官服 / SB 私服。
 *
 * 位置：谱面 ID 那一行的右边（beatmap_id 墨迹是 x60..147, y249..264），
 *       所以放在 (170, 249)，同一基线，不抢任何现有元素的位置。
 *
 * 默认文字留空（官服那侧由插件填「官方」），颜色先给官服的中性灰。
 *
 * 注意：一次 DoJavaScript 只 translate 一次，不做自校正循环 ——
 * 这个版本的 translate 会取反，循环会发散。 */
app.displayDialogs = DialogModes.NO;
var target = null;
for (var q = 0; q < app.documents.length; q++){
  var n = app.documents[q].name;
  if (n.indexOf('osu_score_template_v1') === 0 && n.indexOf('.psd') > 0) target = app.documents[q];
}
if (!target) throw new Error('PSD 没打开');
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

var TARGET_X = 170, TARGET_Y = 249;

var group = find(target.layers, 'beatmap_info');
if (!group) throw new Error('找不到 beatmap_info 组');

var existing = find(target.layers, 'server_tag');
var nl;
if (existing) {
  nl = existing;
  LOG.push('复用已存在的 server_tag');
} else {
  nl = group.artLayers.add();
  nl.kind = LayerKind.TEXT;
  nl.name = 'server_tag';
  LOG.push('新建 server_tag');
}

nl.textItem.contents = '官方';
nl.textItem.font = 'Inter18pt-Regular';
nl.textItem.size = 18;
var sc = new SolidColor();
sc.rgb.red = 140; sc.rgb.green = 150; sc.rgb.blue = 169;   /* #8C96A9 三级灰 */
nl.textItem.color = sc;

/* 落位：读一次 bounds，translate 一次 */
var b = nl.bounds;
var dx = TARGET_X - b[0];
var dy = TARGET_Y - b[1];
if (Math.round(dx) !== 0 || Math.round(dy) !== 0) {
  nl.translate(dx, dy);
}
LOG.push('落位 -> ' + bb(nl) + '  (期望左上 ' + TARGET_X + ',' + TARGET_Y + ')');
LOG.push('字体=' + nl.textItem.font + ' 字号=' + nl.textItem.size + ' 颜色=#8C96A9');
nl.visible = true;

var root = target.layerSets.getByName('TEMPLATE_ROOT');
for (var i = 0; i < root.layers.length; i++){
  if (root.layers[i].typename === 'LayerSet') root.layers[i].visible = true;
}
find(target.layers, 'bg').visible = true;

var opt = new PhotoshopSaveOptions();
opt.alphaChannels = true; opt.layers = true; opt.embedColorProfile = true;
target.saveAs(new File('D:/Cho Osu Bot/template/osu_score_template_v1.psd'), opt, true);
LOG.push('已保存 PSD');
LOG.join('\n');
