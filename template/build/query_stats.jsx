var doc = app.activeDocument;
var root = doc.layerSets.getByName('TEMPLATE_ROOT');
var g = root.layerSets.getByName('beatmap_stats');
var out = [];
var items = [];
for (var i = 0; i < g.layers.length; i++){
  var l = g.layers[i];
  if (l.typename === 'LayerSet') continue;
  var b = null; try { b = l.bounds; } catch(e){}
  items.push({ n: l.name, y0: b ? b[1] : -1, y1: b ? b[3] : -1,
               x0: b ? Math.round(b[0]) : -1, x1: b ? Math.round(b[2]) : -1,
               vis: l.visible });
}
items.sort(function(a,b){ return a.y0 - b.y0; });
for (var k = 0; k < items.length; k++){
  var it = items[k];
  out.push(it.n + (it.vis ? '' : '(H)') + ' y' + Math.round(it.y0) + '..' + Math.round(it.y1) +
           ' x' + it.x0 + '..' + it.x1);
}
'beatmap_stats (top->bottom by y): ' + out.join('  |  ');
