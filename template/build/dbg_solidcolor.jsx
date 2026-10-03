app.displayDialogs = DialogModes.NO;
var target = null;
for (var q = 0; q < app.documents.length; q++){
  if (app.documents[q].name.indexOf('osu_score_template_v1') === 0) target = app.documents[q];
}
app.activeDocument = target;
var LOG = [];

/* --- 1. remove the half-made layers from the aborted rebuild --- */
function purgeNew(set, path){
  for (var i = set.length - 1; i >= 0; i--){
    var l = set[i], p = path + '/' + l.name;
    if (l.typename === 'LayerSet'){ purgeNew(l.layers, p); continue; }
    if (l.name.indexOf('_NEW') >= 0){ LOG.push('purged ' + p); l.remove(); }
  }
}
purgeNew(target.layers, '');

/* --- 2. test SolidColor on a real layer --- */
function find(set, name){
  for (var i = 0; i < set.length; i++){
    var l = set[i];
    if (l.name === name) return l;
    if (l.typename === 'LayerSet'){ var r = find(l.layers, name); if (r) return r; }
  }
  return null;
}
var l = find(target.layers, 'beatmap_mapper');
LOG.push('before = #' + (function(){ var c=l.textItem.color.rgb;
  var h=function(v){var s=Math.round(v).toString(16).toUpperCase();return s.length<2?'0'+s:s;};
  return h(c.red)+h(c.green)+h(c.blue); })());
try {
  var sc = new SolidColor();
  sc.rgb.red = 255; sc.rgb.green = 0; sc.rgb.blue = 0;
  l.textItem.color = sc;
  LOG.push('SolidColor ok -> #' + (function(){ var c=l.textItem.color.rgb;
    var h=function(v){var s=Math.round(v).toString(16).toUpperCase();return s.length<2?'0'+s:s;};
    return h(c.red)+h(c.green)+h(c.blue); })());
} catch(e){ LOG.push('SolidColor ERR ' + e); }

/* pixel proof */
var dup = target.duplicate('probe', true);
app.activeDocument = dup;
dup.crop([40, 200, 640, 280]);
dup.flatten();
dup.saveAs(new File('D:/DeepSeek Harness/workspace1/_test/colour_probe.png'), new PNGSaveOptions(), true);
dup.close(SaveOptions.DONOTSAVECHANGES);
app.activeDocument = target;
LOG.push('probe exported');
LOG.join('\n');
