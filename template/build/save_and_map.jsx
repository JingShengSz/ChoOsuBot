app.displayDialogs = DialogModes.NO;
var target = null;
for (var q = 0; q < app.documents.length; q++){
  if (app.documents[q].name.indexOf('osu_score_template_v1') === 0) target = app.documents[q];
}
app.activeDocument = target;

/* ---------- save ---------- */
var root = target.layerSets.getByName('TEMPLATE_ROOT');
for (var i = 0; i < root.layers.length; i++) if (root.layers[i].typename === 'LayerSet') root.layers[i].visible = true;
findVisibleFix();
function findVisibleFix(){}
var bg = null;
for (var i = 0; i < root.layers.length; i++) if (root.layers[i].name === 'bg') bg = root.layers[i];
if (bg) bg.visible = true;

var opt = new PhotoshopSaveOptions();
opt.alphaChannels = true; opt.layers = true; opt.embedColorProfile = true;
target.saveAs(new File('D:/DeepSeek Harness/workspace1/osu_score_template_v1.psd'), opt, true);
target.saveAs(new File('D:/DeepSeek Harness/workspace1/osu_score_template_v1_skeleton.png'), new PNGSaveOptions(), true);

/* ---------- emit the layer map as JSON ---------- */
function hex(l){
  var c = l.textItem.color.rgb;
  var h = function(v){ var s = Math.round(v).toString(16).toUpperCase(); return s.length < 2 ? '0'+s : s; };
  return '#' + h(c.red) + h(c.green) + h(c.blue);
}
function esc(s){
  return String(s).replace(/\\/g,'\\\\').replace(/"/g,'\\"').replace(/\n/g,'\\n').replace(/\r/g,'');
}
function just(j){
  var s = String(j);
  if (s.indexOf('CENTER') >= 0) return 'center';
  if (s.indexOf('RIGHT') >= 0) return 'right';
  return 'left';
}
/* column right edge, used to derive the free width for each sub-column */
function colRight(x){ return x >= 970 ? 1240 : 960; }

var ROWS = [];
function walk(set, path, groupName){
  for (var i = 0; i < set.length; i++){
    var l = set[i];
    if (l.typename === 'LayerSet'){ walk(l.layers, path + '/' + l.name, l.name); continue; }
    if (l.kind !== LayerKind.TEXT) continue;
    var b = l.bounds;
    var x = Math.round(b[0]), y = Math.round(b[1]);
    var size = Math.round(l.textItem.size.as('px') * 100) / 100;
    var free = colRight(x) - x;
    var f = l.textItem.font;
    var cjk = (f.indexOf('Inter') === 0 || f.indexOf('Montserrat') === 0);
    ROWS.push('  {' +
      '"group": "' + esc(groupName) + '", ' +
      '"name": "' + esc(l.name) + '", ' +
      '"kind": "text", ' +
      '"font": "' + esc(f) + '", ' +
      (cjk ? '"cjkFont": "YuGothic-Medium", ' : '') +
      '"sizePx": ' + size + ', ' +
      '"color": "' + hex(l) + '", ' +
      '"x": ' + x + ', "y": ' + y + ', ' +
      '"justify": "' + just(l.textItem.justification) + '", ' +
      '"example": "' + esc(l.textItem.contents) + '", ' +
      '"freeWidthPx": ' + free + ', ' +
      '"maxChars": ' + Math.max(1, Math.floor(free / (size * 0.62))) +
    '}');
  }
}

/* non-text slots */
var SLOTS = [
  ['beatmap_stats', 'star_strip',  'raster', '星级条',   75,  326, 569, 52],
  ['beatmap_stats', 'od_bar',      'raster', 'OD 进度条', 60,  520, 600, 12],
  ['beatmap_stats', 'hp_bar',      'raster', 'HP 进度条', 60,  588, 600, 12],
  ['player_info',   'player_avatar','raster', '头像（椭圆）', 922, 60, 116, 116],
  ['mods_block',    'mod_1..mod_6','raster', 'mod 徽章 48px 高，间距 110，起点 x60', 64, 842, 0, 48],
  ['mods_block',    'mod_N_mult',  'text',   'mod 倍率，由插件填', 210, 900, 0, 13],
  ['secondary_stats','_deco_jicon_count_max','raster','判定图标 56x56', 60, 745, 0, 56],
  ['signboard',     'signboard_*','raster', '立绘，按评级切换可见性', 1277, 0, 643, 1080],
  ['panel',         'panel_glass','raster', '毛玻璃底板（跟随背景生成）', 40, 40, 1216, 980],
  ['panel',         'panel_border','raster','底板描边 1px 白 16%', 40, 40, 1216, 980],
  ['watermark_slot','watermark',   'raster', '水印槽 180x60', 60, 950, 180, 60]
];
function slotRows(){
  var out = [];
  for (var i = 0; i < SLOTS.length; i++){
    var s = SLOTS[i];
    out.push('  {' +
      '"group": "' + s[0] + '", ' +
      '"name": "' + s[1] + '", ' +
      '"kind": "' + s[2] + '", ' +
      '"note": "' + s[3] + '", ' +
      '"x": ' + s[4] + ', "y": ' + s[5] + ', ' +
      '"w": ' + s[6] + ', "h": ' + s[7] +
    '}');
  }
  return out;
}

var out = [];
out.push('{');
out.push('  "canvas": { "width": 1920, "height": 1080, "safeMargin": 60, "resolution": 72, "mode": "RGB/8" },');
out.push('  "backgroundDimmingPct": ' + Math.round(findOpacity() * 10) / 10 + ',');
out.push('  "textLayers": [');
walk(target.layers, '', '');
out.push(ROWS.join(',\n'));
out.push('  ],');
out.push('  "rasterSlots": [');
out.push(slotRows().join(',\n'));
out.push('  ]');
out.push('}');

function findOpacity(){
  function f(set){
    for (var i = 0; i < set.length; i++){
      if (set[i].name === '_deco_bg_overlay') return set[i].opacity;
      if (set[i].typename === 'LayerSet'){ var r = f(set[i].layers); if (r !== null) return r; }
    }
    return null;
  }
  return f(target.layers);
}

var f2 = new File('D:/DeepSeek Harness/workspace1/layer_mapping.json');
f2.encoding = 'UTF-8';
f2.open('w');
f2.write(out.join('\n'));
f2.close();
'saved psd + png + layer_mapping.json   textLayers=' + ROWS.length + '  slots=' + SLOTS.length;
