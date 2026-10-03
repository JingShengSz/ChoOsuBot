app.displayDialogs = DialogModes.NO;
var target = null;
for (var q = 0; q < app.documents.length; q++){
  if (app.documents[q].name.indexOf('osu_score_template_v1') === 0) target = app.documents[q];
}
app.activeDocument = target;
var cTID = charIDToTypeID;
var LOG = [];

LOG.push('resolution      = ' + target.resolution);
LOG.push('pixelAspectRatio= ' + target.pixelAspectRatio);
try { LOG.push('rulerUnits      = ' + app.preferences.rulerUnits); } catch(e){ LOG.push('rulerUnits n/a'); }
try { LOG.push('typeUnits       = ' + app.preferences.typeUnits); } catch(e){}

var root = target.layerSets.getByName('TEMPLATE_ROOT');
var t = root.artLayers.add();
t.kind = LayerKind.TEXT;
t.name = 'PROBE';
t.textItem.contents = 'PROBE';
t.textItem.size = 20;
t.textItem.font = 'Inter18pt-Regular';
var sc = new SolidColor();
sc.rgb.red = 255; sc.rgb.green = 0; sc.rgb.blue = 0;
t.textItem.color = sc;

function top(l){ return Math.round(l.bounds[1] * 100) / 100; }
function tryIt(label, fn){
  var a = top(t);
  target.activeLayer = t;
  try { fn(); } catch(e){ LOG.push(label + ' THREW ' + e); return; }
  var b = top(t);
  LOG.push(label + ': top ' + a + ' -> ' + b + '   (asked +100, got ' + Math.round((b - a) * 100) / 100 + ')');
}

tryIt('raw     translate(0,100)      ', function(){ t.translate(0, 100); });
tryIt('UnitValue translate px       ', function(){ t.translate(new UnitValue(0,'px'), new UnitValue(100,'px')); });
tryIt('AM move Ofst #Pxl (0,100)    ', function(){
  var d1 = new ActionDescriptor();
  var ref = new ActionReference();
  ref.putEnumerated(cTID('Lyr '), cTID('Ordn'), cTID('Trgt'));
  d1.putReference(cTID('null'), ref);
  var d2 = new ActionDescriptor();
  d2.putUnitDouble(cTID('Hrzn'), cTID('#Pxl'), 0);
  d2.putUnitDouble(cTID('Vrtc'), cTID('#Pxl'), 100);
  d1.putObject(cTID('T   '), cTID('Ofst'), d2);
  executeAction(cTID('move'), d1, DialogModes.NO);
});
tryIt('AM move Ofst Pxl (0,100)     ', function(){
  var d1 = new ActionDescriptor();
  var ref = new ActionReference();
  ref.putEnumerated(cTID('Lyr '), cTID('Ordn'), cTID('Trgt'));
  d1.putReference(cTID('null'), ref);
  var d2 = new ActionDescriptor();
  d2.putUnitDouble(cTID('Hrzn'), cTID('Pxl '), 0);
  d2.putUnitDouble(cTID('Vrtc'), cTID('Pxl '), 100);
  d1.putObject(cTID('T   '), cTID('Ofst'), d2);
  executeAction(cTID('move'), d1, DialogModes.NO);
});

LOG.push('probe final bounds = ' + [Math.round(t.bounds[0]),Math.round(t.bounds[1]),Math.round(t.bounds[2]),Math.round(t.bounds[3])].join(','));
t.remove();
LOG.push('probe removed');
LOG.join('\n');
