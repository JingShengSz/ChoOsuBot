app.displayDialogs = DialogModes.NO;
var target = null;
for (var q = 0; q < app.documents.length; q++){
  if (app.documents[q].name.indexOf('osu_score_template_v1') === 0) target = app.documents[q];
}
if (!target) throw new Error('template document not open');
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
function hexOf(l){
  var c = l.textItem.color.rgb;
  var h = function(v){ var s = Math.round(v).toString(16).toUpperCase(); return s.length < 2 ? '0'+s : s; };
  return '#' + h(c.red) + h(c.green) + h(c.blue);
}
function setHex(l, hex){
  var c = new RGBColor();
  c.red   = parseInt(hex.substr(1,2), 16);
  c.green = parseInt(hex.substr(3,2), 16);
  c.blue  = parseInt(hex.substr(5,2), 16);
  try { target.activeLayer = l; } catch(e0){}
  l.textItem.color = c;
}

/* ---- 1. walk every text layer, report colour, lift the tertiary grey ---- */
var OLD = '#5F6878', NEW = '#8C96A9', changed = 0, total = 0;
function walk(set, path){
  for (var i = 0; i < set.length; i++){
    var l = set[i], p = path + '/' + l.name;
    if (l.typename === 'LayerSet'){ walk(l.layers, p); continue; }
    if (l.kind !== LayerKind.TEXT) continue;
    total++;
    var h = hexOf(l);
    if (h === OLD){
      try { setHex(l, NEW); changed++; LOG.push('LIFT ' + p + '  ' + OLD + ' -> ' + NEW); }
      catch(e){ LOG.push('FAIL ' + p + ' : ' + e); }
    }
    else LOG.push('keep ' + p + '  ' + h);
  }
}
walk(target.layers, '');
LOG.push('--- text layers=' + total + ' lifted=' + changed);

/* ---- 2. background darkening 30% -> 75% ---- */
var ov = find(target.layers, '_deco_bg_overlay');
LOG.push('overlay opacity ' + ov.opacity + ' -> 75');
ov.opacity = 75;

/* ---- 3. re-export the two plates ---- */
function setGroups(set, want){
  for (var i = 0; i < set.length; i++){
    if (set[i].typename === 'LayerSet') set[i].visible = want;
  }
}
var root = target.layerSets.getByName('TEMPLATE_ROOT');
var bgGroup = find(target.layers, 'bg');

setGroups(root.layers, false);
bgGroup.visible = true;
target.saveAs(new File('D:/DeepSeek Harness/workspace1/_test/out_bg75.png'), new PNGSaveOptions(), true);
LOG.push('exported out_bg75.png');

setGroups(root.layers, true);
bgGroup.visible = false;
target.saveAs(new File('D:/DeepSeek Harness/workspace1/_test/out_info.png'), new PNGSaveOptions(), true);
LOG.push('exported out_info.png');

LOG.join('\n');
