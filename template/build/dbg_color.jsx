app.displayDialogs = DialogModes.NO;
var target = null;
for (var q = 0; q < app.documents.length; q++){
  if (app.documents[q].name.indexOf('osu_score_template_v1') === 0) target = app.documents[q];
}
app.activeDocument = target;
var LOG = [];
var cTID = charIDToTypeID;

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
var l = find(target.layers, 'beatmap_mapper');
LOG.push('layer=' + l.name + ' kind=' + l.kind + ' visible=' + l.visible + ' hex=' + hexOf(l));
LOG.push('ranges: color=' + hexOf(l) + ' size=' + l.textItem.size + ' font=' + l.textItem.font);
LOG.push('textRange count = ' + (typeof l.textItem.textRange !== 'undefined' ? String(l.textItem.textRange) : 'n/a'));
try { LOG.push('rangeKeys = ' + l.textItem.textRange + ' len=' + l.textItem.textRange.length); } catch(e){ LOG.push('range err ' + e); }

target.activeLayer = l;
LOG.push('after select, activeLayer = ' + target.activeLayer.name + '  same=' + (target.activeLayer == l));

/* --- route 1: DOM --- */
try {
  var c1 = new RGBColor(); c1.red = 140; c1.green = 150; c1.blue = 169;
  l.textItem.color = c1;
  LOG.push('DOM  ok -> ' + hexOf(l));
} catch(e){ LOG.push('DOM  ERR ' + e); }

/* --- route 2: ActionManager setd / TxLr --- */
try {
  var d1 = new ActionDescriptor();
  var ref = new ActionReference();
  ref.putEnumerated(cTID('Lyr '), cTID('Ordn'), cTID('Trgt'));
  d1.putReference(cTID('null'), ref);
  var d2 = new ActionDescriptor();
  d2.putEnumerated(cTID('Clr '), cTID('Clr '), cTID('RGBC'));
  var d3 = new ActionDescriptor();
  d3.putDouble(cTID('Rd  '), 140); d3.putDouble(cTID('Grn '), 150); d3.putDouble(cTID('Bl  '), 169);
  d2.putObject(cTID('Clr '), cTID('RGBC'), d3);
  d1.putObject(cTID('T   '), cTID('TxLr'), d2);
  executeAction(cTID('setd'), d1, DialogModes.NO);
  LOG.push('AM   ok -> ' + hexOf(l));
} catch(e){ LOG.push('AM   ERR ' + e); }

/* --- route 3: ActionManager textStyle range --- */
try {
  var d4 = new ActionDescriptor();
  var ref4 = new ActionReference();
  ref4.putEnumerated(cTID('Lyr '), cTID('Ordn'), cTID('Trgt'));
  d4.putReference(cTID('null'), ref4);
  d4.putBoolean(cTID('Prpr'), true);
  var d5 = new ActionDescriptor();
  var d6 = new ActionDescriptor();
  d6.putDouble(cTID('Rd  '), 140); d6.putDouble(cTID('Grn '), 150); d6.putDouble(cTID('Bl  '), 169);
  d5.putObject(cTID('Clr '), cTID('RGBC'), d6);
  d4.putObject(cTID('T   '), cTID('TxLr'), d5);
  executeAction(cTID('setd'), d4, DialogModes.NO);
  LOG.push('AM2  ok -> ' + hexOf(l));
} catch(e){ LOG.push('AM2  ERR ' + e); }

LOG.join('\n');
