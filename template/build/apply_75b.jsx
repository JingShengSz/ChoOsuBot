app.displayDialogs = DialogModes.NO;
var target = null;
for (var q = 0; q < app.documents.length; q++){
  if (app.documents[q].name.indexOf('osu_score_template_v1') === 0) target = app.documents[q];
}
if (!target) throw new Error('template document not open');
app.activeDocument = target;
var LOG = [];

var cTID = charIDToTypeID, sTID = stringIDToTypeID;

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
/* set the ACTIVE text layer's colour through ActionManager - the DOM setter
   throws 1200 (internal error) on layers created with a character override. */
function amColor(hex){
  var d1 = new ActionDescriptor();
  var ref = new ActionReference();
  ref.putEnumerated(cTID('Lyr '), cTID('Ordn'), cTID('Trgt'));
  d1.putReference(cTID('null'), ref);
  var d2 = new ActionDescriptor();
  d2.putEnumerated(cTID('Clr '), cTID('Clr '), cTID('RGBC'));
  var d3 = new ActionDescriptor();
  d3.putDouble(cTID('Rd  '), parseInt(hex.substr(1,2), 16));
  d3.putDouble(cTID('Grn '), parseInt(hex.substr(3,2), 16));
  d3.putDouble(cTID('Bl  '), parseInt(hex.substr(5,2), 16));
  d2.putObject(cTID('Clr '), cTID('RGBC'), d3);
  d1.putObject(cTID('T   '), cTID('TxLr'), d2);
  executeAction(cTID('setd'), d1, DialogModes.NO);
}

var OLD = '#5F6878', NEW = '#8C96A9', changed = 0, failed = 0, total = 0;
function walk(set, path){
  for (var i = 0; i < set.length; i++){
    var l = set[i], p = path + '/' + l.name;
    if (l.typename === 'LayerSet'){ walk(l.layers, p); continue; }
    if (l.kind !== LayerKind.TEXT) continue;
    total++;
    if (hexOf(l) !== OLD) continue;
    try {
      target.activeLayer = l;
      amColor(NEW);
      var now = hexOf(l);
      if (now === NEW){ changed++; LOG.push('LIFT ' + p + '  ' + OLD + ' -> ' + now); }
      else { failed++; LOG.push('STUCK ' + p + '  still ' + now); }
    } catch(e){ failed++; LOG.push('FAIL ' + p + ' : ' + e); }
  }
}
walk(target.layers, '');
LOG.push('--- text layers=' + total + '  lifted=' + changed + '  failed=' + failed);

var ov = find(target.layers, '_deco_bg_overlay');
LOG.push('overlay opacity ' + ov.opacity);
ov.opacity = 75;

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
LOG.push('exported out_bg75.png (overlay ' + ov.opacity + '%)');

setGroups(root.layers, true);
bgGroup.visible = false;
target.saveAs(new File('D:/DeepSeek Harness/workspace1/_test/out_info.png'), new PNGSaveOptions(), true);
LOG.push('exported out_info.png');

LOG.join('\n');
