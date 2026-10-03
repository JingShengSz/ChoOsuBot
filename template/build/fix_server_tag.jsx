/* 修 server_tag 的字体和位置。
 *
 * 两个坑：
 *  1. 字体：内容含中文时 PS 会**静默替换**成 CJK 字体（实测 Inter18pt-Regular ->
 *     AdobeHeitiStd-Regular）。所以直接指定 YuGothic-Medium。
 *  2. 位置：这个版本的 translate 会**取反**（要 +1px 给 -63px），所以这里显式取负，
 *     并且只调一次 —— 不做自校正循环，那会发散。 */
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
var l = find(target.layers, 'server_tag');
if (!l) throw new Error('找不到 server_tag');

/* 1. 字体换成 CJK 可用的 */
l.textItem.font = 'YuGothic-Medium';
LOG.push('font -> ' + l.textItem.font + '  (期望 YuGothic-Medium)');

/* 2. 位置：一次 translate，显式取负 */
var b = l.bounds;
var needX = TARGET_X - b[0];
var needY = TARGET_Y - b[1];
LOG.push('当前 ' + bb(l) + '  需要位移(' + Math.round(needX) + ',' + Math.round(needY) + ')');
if (Math.round(needX) !== 0 || Math.round(needY) !== 0) {
  l.translate(-needX, -needY);   // 取负 —— 这个版本的 translate 方向是反的
  LOG.push('translate(-' + Math.round(needX) + ',-' + Math.round(needY) + ') 之后 ' + bb(l));
}

/* 3. 颜色确认 */
var c = l.textItem.color.rgb;
var h = function(v){ var s = Math.round(v).toString(16).toUpperCase(); return s.length < 2 ? '0'+s : s; };
LOG.push('color = #' + h(c.red) + h(c.green) + h(c.blue));
LOG.push('contents = ' + l.textItem.contents + '  size = ' + l.textItem.size);

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
