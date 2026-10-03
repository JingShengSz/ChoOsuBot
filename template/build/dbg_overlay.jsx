app.displayDialogs = DialogModes.NO;
var target = null;
for (var q = 0; q < app.documents.length; q++){
  if (app.documents[q].name.indexOf('osu_score_template_v1') === 0) target = app.documents[q];
}
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
var bgGroup = find(target.layers, 'bg');
LOG.push('bg group: ' + bgGroup.layers.length + ' children (index 0 = TOP)');
for (var i = 0; i < bgGroup.layers.length; i++){
  var l = bgGroup.layers[i];
  var b = l.bounds;
  LOG.push('  [' + i + '] ' + l.name +
           '  kind=' + l.kind +
           '  vis=' + l.visible +
           '  opacity=' + Math.round(l.opacity * 100) / 100 +
           '  blend=' + l.blendMode +
           '  b=' + [Math.round(b[0]),Math.round(b[1]),Math.round(b[2]),Math.round(b[3])].join(','));
  if (l.kind === LayerKind.SOLIDFILL || l.kind === LayerKind.GRADIENTFILL){
    try { LOG.push('        fillLayer detected'); } catch(e){}
  }
}

/* does the overlay actually change the render? probe at several opacities */
var ov = find(target.layers, '_deco_bg_overlay');
var OPS = [0, 30, 75, 100];
for (var k = 0; k < OPS.length; k++){
  ov.opacity = OPS[k];
  var dup = target.duplicate('probe', true);
  app.activeDocument = dup;
  dup.crop([0, 0, 120, 120]);
  dup.flatten();
  dup.saveAs(new File('D:/DeepSeek Harness/workspace1/_test/probe_' + OPS[k] + '.png'),
             new PNGSaveOptions(), true);
  dup.close(SaveOptions.DONOTSAVECHANGES);
  app.activeDocument = target;
  LOG.push('probe at opacity ' + OPS[k] + ' exported');
}
ov.opacity = 75;
LOG.push('overlay restored to ' + ov.opacity);
LOG.join('\n');
