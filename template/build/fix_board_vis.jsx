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

var board = find(target.layers, 'signboard');

/* 显式按名单设置，不用 !!KEEP[name] 那种隐式 undefined -> false —— 上一版就是这里出的岔 */
var VISIBLE = { signboard_a: true, rank_glow: true };
for (var i = 0; i < board.layers.length; i++){
  var nm = board.layers[i].name;
  board.layers[i].visible = (VISIBLE[nm] === true);
}

var glow = find(target.layers, 'rank_glow');
var kids = board.layers;
if (kids.length > 1 && glow) glow.move(kids[kids.length - 1], ElementPlacement.PLACEAFTER);

var names = [];
for (var i = 0; i < board.layers.length; i++)
  names.push(board.layers[i].name + (board.layers[i].visible ? '*' : ''));
LOG.push('signboard 组: ' + names.join(' / '));

/* 复核 */
var visCount = 0, visNames = [];
for (var i = 0; i < board.layers.length; i++)
  if (board.layers[i].visible){ visCount++; visNames.push(board.layers[i].name); }
LOG.push('可见的: ' + visNames.join(', ') + '  (共 ' + visCount + ' 个)');

var opt = new PhotoshopSaveOptions();
opt.alphaChannels = true; opt.layers = true; opt.embedColorProfile = true;
target.saveAs(new File('D:/Cho Osu Bot/template/osu_score_template_v1.psd'), opt, true);
LOG.push('已保存 PSD');
LOG.join('\n');
