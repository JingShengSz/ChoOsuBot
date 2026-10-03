/* 装 Rank SS 和 Rank F 立绘。
   - signboard_ss 已存在（灰占位）→ 替换
   - signboard_f 不存在 → 新建
   PNG 都是整张 1920x1080，靠 duplicate 落位，不做 translate。 */
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

var JOBS = [
  ['D:/Cho Osu Bot/scratch/sb_ss/signboard_SS.png', 'signboard_ss'],
  ['D:/Cho Osu Bot/scratch/sb_f/signboard_F.png',   'signboard_f']
];
for (var j = 0; j < JOBS.length; j++){
  var path = JOBS[j][0], layerName = JOBS[j][1];
  var old = find(target.layers, layerName);
  var sd = app.open(new File(path));
  var nl = sd.layers[0].duplicate(target, ElementPlacement.PLACEATBEGINNING);
  sd.close(SaveOptions.DONOTSAVECHANGES);
  app.activeDocument = target;
  nl.name = layerName;
  nl.move(board, ElementPlacement.INSIDE);
  if (old && old !== nl) old.remove();
  LOG.push(layerName + (old ? ' (替换占位)' : ' (新建)') + '  ' + bb(nl));
}

/* 只留 A 可见 */
var KEEP = { signboard_a: true, rank_glow: true };
for (var i = 0; i < board.layers.length; i++){
  board.layers[i].visible = !!KEEP[board.layers[i].name];
}
var glow = find(target.layers, 'rank_glow');
var kids = board.layers;
if (kids.length > 1 && glow) glow.move(kids[kids.length - 1], ElementPlacement.PLACEAFTER);

var names = [];
for (var i = 0; i < board.layers.length; i++)
  names.push(board.layers[i].name + (board.layers[i].visible ? '*' : ''));
LOG.push('signboard 组: ' + names.join(' / '));

var opt = new PhotoshopSaveOptions();
opt.alphaChannels = true; opt.layers = true; opt.embedColorProfile = true;
target.saveAs(new File('D:/Cho Osu Bot/template/osu_score_template_v1.psd'), opt, true);
LOG.push('已保存 PSD');
LOG.join('\n');
