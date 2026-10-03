/* The 14 tertiary-grey text layers cannot be recoloured in place:
   textItem.color throws 1200, and setd/TxLr silently no-ops.
   So rebuild each one from its own metadata and swap it in. */
app.displayDialogs = DialogModes.NO;
var target = null;
for (var q = 0; q < app.documents.length; q++){
  if (app.documents[q].name.indexOf('osu_score_template_v1') === 0) target = app.documents[q];
}
if (!target) throw new Error('template document not open');
app.activeDocument = target;
var LOG = [];
var OLD = '#5F6878', NEW = '#8C96A9';

function walk(set, path, out){
  for (var i = 0; i < set.length; i++){
    var l = set[i], p = path + '/' + l.name;
    if (l.typename === 'LayerSet'){ walk(l.layers, p, out); continue; }
    if (l.kind !== LayerKind.TEXT) continue;
    var c = l.textItem.color.rgb;
    var h = function(v){ var s = Math.round(v).toString(16).toUpperCase(); return s.length < 2 ? '0'+s : s; };
    if ('#' + h(c.red) + h(c.green) + h(c.blue) !== OLD) continue;
    out.push({ old: l, path: p, parent: l.parent });
  }
}
var hits = [];
walk(target.layers, '', hits);
LOG.push('found ' + hits.length + ' layers at ' + OLD);

for (var k = 0; k < hits.length; k++){
  var o = hits[k].old;
  var meta = {
    contents: o.textItem.contents,
    font:     o.textItem.font,
    size:     o.textItem.size,
    just:     o.textItem.justification,
    autoLead: o.textItem.useAutoLeading,
    visible:  o.visible,
    bounds:   o.bounds,
    name:     o.name
  };
  try { meta.tracking = o.textItem.tracking; } catch(e){}
  try { meta.leading = o.textItem.leading; } catch(e){}

  var nl = hits[k].parent.artLayers.add();
  nl.kind = LayerKind.TEXT;
  nl.name = meta.name + '_NEW';
  nl.textItem.contents = meta.contents;
  nl.textItem.font = meta.font;
  nl.textItem.size = meta.size;
  try { nl.textItem.justification = meta.just; } catch(e){ LOG.push('just ERR ' + meta.name); }
  try { nl.textItem.useAutoLeading = meta.autoLead; } catch(e){}
  try { if (meta.tracking !== undefined) nl.textItem.tracking = meta.tracking; } catch(e){}
  var c2 = new RGBColor();
  c2.red = 140; c2.green = 150; c2.blue = 169;
  nl.textItem.color = c2;

  var nb = nl.bounds;
  var dx = meta.bounds[0] - nb[0];
  var dy = meta.bounds[1] - nb[1];
  if (Math.round(dx) !== 0 || Math.round(dy) !== 0) nl.translate(dx, dy);
  var fb = nl.bounds;
  LOG.push(meta.name + '  old=' + [Math.round(meta.bounds[0]),Math.round(meta.bounds[1]),Math.round(meta.bounds[2]),Math.round(meta.bounds[3])].join(',') +
           '  new=' + [Math.round(fb[0]),Math.round(fb[1]),Math.round(fb[2]),Math.round(fb[3])].join(',') +
           '  shift=' + Math.round(dx) + ',' + Math.round(dy));

  o.remove();
  nl.name = meta.name;
  nl.visible = meta.visible;
}
LOG.push('--- rebuilt ' + hits.length + ' layers -> ' + NEW);

/* re-export both plates */
var root = target.layerSets.getByName('TEMPLATE_ROOT');
function setGroups(set, want){
  for (var i = 0; i < set.length; i++){
    if (set[i].typename === 'LayerSet') set[i].visible = want;
  }
}
function find(set, name){
  for (var i = 0; i < set.length; i++){
    var l = set[i];
    if (l.name === name) return l;
    if (l.typename === 'LayerSet'){ var r = find(l.layers, name); if (r) return r; }
  }
  return null;
}
var bgGroup = find(target.layers, 'bg');
LOG.push('overlay opacity = ' + find(target.layers, '_deco_bg_overlay').opacity);

setGroups(root.layers, false); bgGroup.visible = true;
target.saveAs(new File('D:/DeepSeek Harness/workspace1/_test/out_bg75.png'), new PNGSaveOptions(), true);
setGroups(root.layers, true); bgGroup.visible = false;
target.saveAs(new File('D:/DeepSeek Harness/workspace1/_test/out_info.png'), new PNGSaveOptions(), true);
LOG.push('exported both plates');

LOG.join('\n');
