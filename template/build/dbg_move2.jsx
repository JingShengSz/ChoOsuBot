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
function top(l){ return Math.round(l.bounds[1] * 100) / 100; }

var l = find(target.layers, '_deco_pp_label');
LOG.push('layer=' + l.name + '  parent=' + l.parent.name + '  top=' + top(l));
LOG.push('parent opacity=' + l.parent.opacity + ' blend=' + l.parent.blendMode);
try { LOG.push('parent bounds=' + l.parent.bounds); } catch(e){}
try { LOG.push('textItem.size=' + l.textItem.size + ' font=' + l.textItem.font +
               ' just=' + l.textItem.justification); } catch(e){ LOG.push('text props err'); }
try { LOG.push('useAutoLeading=' + l.textItem.useAutoLeading); } catch(e){}
try { LOG.push('baseline(leading)=' + l.textItem.leading); } catch(e){}

/* raw translate +10, on a layer inside a nested group */
target.activeLayer = l;
var a = top(l);
l.translate(0, 10);
var b = top(l);
LOG.push('raw translate(0,10):  ' + a + ' -> ' + b + '   delta=' + Math.round((b-a)*100)/100);

/* AM move +10 */
a = top(l);
var d1 = new ActionDescriptor();
var ref = new ActionReference();
ref.putEnumerated(cTID('Lyr '), cTID('Ordn'), cTID('Trgt'));
d1.putReference(cTID('null'), ref);
var d2 = new ActionDescriptor();
d2.putUnitDouble(cTID('Hrzn'), cTID('#Pxl'), 0);
d2.putUnitDouble(cTID('Vrtc'), cTID('#Pxl'), 10);
d1.putObject(cTID('T   '), cTID('Ofst'), d2);
executeAction(cTID('move'), d1, DialogModes.NO);
b = top(l);
LOG.push('AM move Ofst (0,10):  ' + a + ' -> ' + b + '   delta=' + Math.round((b-a)*100)/100);

/* what does the GROUP's own translate do? */
var g = l.parent;
var ga = top(g);
g.translate(0, 10);
var gb = top(g);
LOG.push('group translate(0,10): ' + ga + ' -> ' + gb + '   delta=' + Math.round((gb-ga)*100)/100);
g.translate(0, -10);

LOG.join('\n');
