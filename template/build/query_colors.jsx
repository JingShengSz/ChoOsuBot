var doc = app.activeDocument;
var root = doc.layerSets.getByName('TEMPLATE_ROOT');
var out = [];
var groups = ['beatmap_stats','beatmap_info','primary_stats'];
for (var g = 0; g < groups.length; g++){
  var gs = root.layerSets.getByName(groups[g]);
  for (var i = 0; i < gs.layers.length; i++){
    var l = gs.layers[i];
    if (l.typename === 'LayerSet' || l.kind !== LayerKind.TEXT) continue;
    if (l.name.indexOf('_deco_') === 0) continue;
    var t = l.textItem;
    var hex = '', sz = 0, fnt = '';
    try { hex = t.color.rgb.hexValue; } catch(e){}
    try { sz = Math.round(t.size.value); } catch(e){}
    try { fnt = t.font; } catch(e){}
    out.push(l.name + ' ' + sz + 'px #' + hex + ' ' + fnt.replace('18pt-',''));
  }
}
out.join('   |   ');
