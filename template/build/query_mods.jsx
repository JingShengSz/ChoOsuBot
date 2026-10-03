var doc = app.activeDocument;
var root = doc.layerSets.getByName('TEMPLATE_ROOT');
var gMods = root.layerSets.getByName('mods_block');
var out = [];
for (var i = 0; i < gMods.layers.length; i++){
  var l = gMods.layers[i];
  if (l.typename === 'LayerSet') continue;
  var b = null; try { b = l.bounds; } catch(e){}
  out.push(l.name + (l.visible ? '' : '(H)') + ' @' +
    (b ? Math.round(b[0]) + ',' + Math.round(b[1]) + ' ' +
         Math.round(b[2]) + ',' + Math.round(b[3]) : 'n/a'));
}
'mods_block: ' + out.join('  |  ');
