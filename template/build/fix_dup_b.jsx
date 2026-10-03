app.displayDialogs = DialogModes.NO;
var target = null;
for (var q = 0; q < app.documents.length; q++){
  var n = app.documents[q].name;
  if (n.indexOf('osu_score_template_v1') === 0 && n.indexOf('.psd') > 0) target = app.documents[q];
}
app.activeDocument = target;
function find(set, name){
  for (var i = 0; i < set.length; i++){
    var l = set[i];
    if (l.name === name) return l;
    if (l.typename === 'LayerSet'){ var r = find(l.layers, name); if (r) return r; }
  }
  return null;
}
var L = [];

/* signboard 组里有两个同名 signboard_b —— 一个是真立绘，一个是灰占位。
   把占位那个改名，避免插件按名字取错。 */
var board = find(target.layers, 'signboard');
var seen = 0;
for (var i = 0; i < board.layers.length; i++){
  var l = board.layers[i];
  if (l.name === 'signboard_b'){
    seen++;
    if (seen === 2){ l.name = 'signboard_b_placeholder'; L.push('renamed dup signboard_b -> signboard_b_placeholder (idx ' + i + ')'); }
  }
}
var names = [];
for (var i = 0; i < board.layers.length; i++) names.push(board.layers[i].name);
L.push('signboard: ' + names.join(' / '));

var opt = new PhotoshopSaveOptions();
opt.alphaChannels = true; opt.layers = true; opt.embedColorProfile = true;
target.saveAs(new File('D:/DeepSeek Harness/workspace1/osu_score_template_v1.psd'), opt, true);
var root = target.layerSets.getByName('TEMPLATE_ROOT');
for (var i = 0; i < root.layers.length; i++) if (root.layers[i].typename === 'LayerSet') root.layers[i].visible = true;
find(target.layers, 'bg').visible = true;
target.saveAs(new File('D:/DeepSeek Harness/workspace1/osu_score_template_v1_skeleton.png'), new PNGSaveOptions(), true);
L.push('saved');
L.join('\n');
