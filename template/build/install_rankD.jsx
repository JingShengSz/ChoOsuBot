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

var board = find(target.layers, 'signboard');

var stale = find(target.layers, 'signboard_d');
var sd = app.open(new File('D:/Cho Osu Bot/scratch/sb_d/signboard_D.png'));
var nl = sd.layers[0].duplicate(target, ElementPlacement.PLACEATBEGINNING);
sd.close(SaveOptions.DONOTSAVECHANGES);
app.activeDocument = target;
nl.name = 'signboard_d';
nl.move(board, ElementPlacement.INSIDE);
if (stale && stale !== nl) stale.remove();
LOG.push('signboard_d' + (stale ? '  替换占位' : '  新建') + '  ' + bb(nl));

/* 只留 A 可见 */
var KEEP = { signboard_a: true, rank_glow: true };
for (var i = 0; i < board.layers.length; i++){
  board.layers[i].visible = !!KEEP[board.layers[i].name];
}
var glow = find(target.layers, 'rank_glow');
var kids = board.layers;
if (kids.length > 1 && glow) glow.move(kids[kids.length - 1], ElementPlacement.PLACEAFTER);

/* 顺便把已经不需要的 X 系单独立绘从组里去掉（规则改成 S/SS 复用后它们永远用不上） */
var DROP = ['signboard_xh', 'signboard_sh'];
for (var k = 0; k < DROP.length; k++){
  var d = find(target.layers, DROP[k]);
  if (d){ d.remove(); LOG.push('删除不再使用的 ' + DROP[k]); }
}

var names = [];
for (var i = 0; i < board.layers.length; i++)
  names.push(board.layers[i].name + (board.layers[i].visible ? '*' : ''));
LOG.push('signboard 组: ' + names.join(' / '));

var opt = new PhotoshopSaveOptions();
opt.alphaChannels = true; opt.layers = true; opt.embedColorProfile = true;
target.saveAs(new File('D:/Cho Osu Bot/template/osu_score_template_v1.psd'), opt, true);
LOG.push('已保存 PSD');
LOG.join('\n');
