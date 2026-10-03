app.displayDialogs = DialogModes.NO;
var target = null;
for (var q = 0; q < app.documents.length; q++){
  if (app.documents[q].name.indexOf('osu_score_template_v1') === 0) target = app.documents[q];
}
app.activeDocument = target;
var cTID = charIDToTypeID;
var LOG = [];

function find(set, name){
  for (var i = 0; i < set.length; i++){
    var l = set[i];
    if (l.name === name) return l;
    if (l.typename === 'LayerSet'){ var r = find(l.layers, name); if (r) return r; }
  }
  return null;
}
var l = find(target.layers, 'beatmap_mapper');
target.activeLayer = l;

/* AM only, paint it pure red */
var d1 = new ActionDescriptor();
var ref = new ActionReference();
ref.putEnumerated(cTID('Lyr '), cTID('Ordn'), cTID('Trgt'));
d1.putReference(cTID('null'), ref);
var d2 = new ActionDescriptor();
d2.putEnumerated(cTID('Clr '), cTID('Clr '), cTID('RGBC'));
var d3 = new ActionDescriptor();
d3.putDouble(cTID('Rd  '), 255); d3.putDouble(cTID('Grn '), 0); d3.putDouble(cTID('Bl  '), 0);
d2.putObject(cTID('Clr '), cTID('RGBC'), d3);
d1.putObject(cTID('T   '), cTID('TxLr'), d2);
executeAction(cTID('setd'), d1, DialogModes.NO);
LOG.push('AM executed, readback = #' + (function(){
  var c = l.textItem.color.rgb;
  var h=function(v){var s=Math.round(v).toString(16).toUpperCase();return s.length<2?'0'+s:s;};
  return h(c.red)+h(c.green)+h(c.blue);
})());

/* export a small crop of that layer through a duplicated doc, so no full export is needed */
var dup = target.duplicate('colour_probe', true);
app.activeDocument = dup;
dup.crop([40, 200, 640, 280]);
dup.flatten();
dup.saveAs(new File('D:/DeepSeek Harness/workspace1/_test/colour_probe.png'), new PNGSaveOptions(), true);
dup.close(SaveOptions.DONOTSAVECHANGES);
app.activeDocument = target;
LOG.push('probe exported');
LOG.join('\n');
