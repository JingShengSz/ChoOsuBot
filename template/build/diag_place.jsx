app.displayDialogs = DialogModes.NO;
var doc = app.activeDocument;
var root = doc.layerSets.getByName('TEMPLATE_ROOT');
var gMods = root.layerSets.getByName('mods_block');
var log = [];
function B(l){ var b = l.bounds; return '[' + Math.round(b[0]) + ',' + Math.round(b[1]) + ' ' +
  Math.round(b[2]) + ',' + Math.round(b[3]) + ']'; }

log.push('doc ' + doc.width.value + 'x' + doc.height.value);

var sd = app.open(new File('D:/DeepSeek Harness/workspace1/_mods/ready/mod_hd.png'));
log.push('src opened: ' + sd.name + '  ' + sd.width.value + 'x' + sd.height.value);
var sl = sd.layers[0];
log.push('src layer bounds ' + B(sl));

sd.resizeImage(UnitValue(103,'px'), UnitValue(48,'px'), null, ResampleMethod.BICUBICSHARPER);
log.push('src after resize: ' + sd.width.value + 'x' + sd.height.value + '  layer ' + B(sl));

var nl = sl.duplicate(doc, ElementPlacement.PLACEATBEGINNING);
log.push('dup in target, before move: ' + B(nl));

sd.close(SaveOptions.DONOTSAVECHANGES);
app.activeDocument = doc;
log.push('after src close, active doc = ' + app.activeDocument.name);
log.push('dup bounds after close: ' + B(nl));

nl.move(gMods, ElementPlacement.INSIDE);
log.push('after move into mods_block: ' + B(nl));

nl.translate(100, 100);
log.push('after translate(100,100): ' + B(nl));

try { nl.remove(); log.push('test layer removed'); } catch(e){ log.push('rm ERR'); }

log.join(' | ');
