app.displayDialogs = DialogModes.NO;
var target = null;
for (var q = 0; q < app.documents.length; q++){
  if (app.documents[q].name.indexOf('osu_score_template_v1') === 0) target = app.documents[q];
}
if (!target) throw new Error('template document not open');
app.activeDocument = target;
var LOG = [];
var OLD = '#5F6878', NEW = '#8C96A9', TARGET = [140, 150, 169];

function hexOf(l){
  var c = l.textItem.color.rgb;
  var h = function(v){ var s = Math.round(v).toString(16).toUpperCase(); return s.length < 2 ? '0'+s : s; };
  return '#' + h(c.red) + h(c.green) + h(c.blue);
}
function find(set, name){
  for (var i = 0; i < set.length; i++){
    var l = set[i];
    if (l.name === name) return l;
    if (l.typename === 'LayerSet'){ var r = find(l.layers, name); if (r) return r; }
  }
  return null;
}

var changed = 0, failed = 0, total = 0, other = [];
function walk(set, path){
  for (var i = 0; i < set.length; i++){
    var l = set[i], p = path + '/' + l.name;
    if (l.typename === 'LayerSet'){ walk(l.layers, p); continue; }
    if (l.kind !== LayerKind.TEXT) continue;
    total++;
    var h = hexOf(l);
    if (h !== OLD && h !== '#FF0000'){ other.push(h + '  ' + p); continue; }
    try {
      var sc = new SolidColor();
      sc.rgb.red = TARGET[0]; sc.rgb.green = TARGET[1]; sc.rgb.blue = TARGET[2];
      l.textItem.color = sc;
      if (hexOf(l) === NEW){ changed++; LOG.push('LIFT ' + p + '  ' + h + ' -> ' + hexOf(l)); }
      else { failed++; LOG.push('STUCK ' + p + ' = ' + hexOf(l)); }
    } catch(e){ failed++; LOG.push('FAIL ' + p + ' : ' + e); }
  }
}
walk(target.layers, '');
LOG.push('--- text layers=' + total + '  recoloured=' + changed + '  failed=' + failed);
LOG.push('--- untouched colours:');
for (var z = 0; z < other.length; z++) LOG.push('    ' + other[z]);

var ov = find(target.layers, '_deco_bg_overlay');
LOG.push('overlay opacity = ' + ov.opacity + '%');

function setGroups(set, want){
  for (var i = 0; i < set.length; i++){
    if (set[i].typename === 'LayerSet') set[i].visible = want;
  }
}
var root = target.layerSets.getByName('TEMPLATE_ROOT');
var bgGroup = find(target.layers, 'bg');
setGroups(root.layers, false); bgGroup.visible = true;
target.saveAs(new File('D:/DeepSeek Harness/workspace1/_test/out_bg75.png'), new PNGSaveOptions(), true);
setGroups(root.layers, true); bgGroup.visible = false;
target.saveAs(new File('D:/DeepSeek Harness/workspace1/_test/out_info.png'), new PNGSaveOptions(), true);
LOG.push('exported out_bg75.png + out_info.png');
LOG.join('\n');
