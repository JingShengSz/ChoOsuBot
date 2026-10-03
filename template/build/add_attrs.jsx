app.displayDialogs = DialogModes.NO;
var doc = app.activeDocument;
var root = doc.layerSets.getByName('TEMPLATE_ROOT');
var gStats = root.layerSets.getByName('beatmap_stats');
var log = [];

var DIR = 'D:/DeepSeek Harness/workspace1/_attrs/placed/';
var JOBS = [
  ['_deco_attr_bpm', 422],
  ['_deco_attr_od',  490],
  ['_deco_attr_hp',  558]
];

for (var i = 0; i < JOBS.length; i++){
  var nm = JOBS[i][0], wantY = JOBS[i][1];

  // 先删掉旧的灰色占位块
  try { gStats.artLayers.getByName(nm).remove(); log.push(nm + ':placeholder removed'); } catch(e){}

  var sd = app.open(new File(DIR + nm + '.png'));
  var nl = sd.layers[0].duplicate(doc, ElementPlacement.PLACEATBEGINNING);
  sd.close(SaveOptions.DONOTSAVECHANGES);
  app.activeDocument = doc;
  nl.name = nm;
  try { nl.move(gStats, ElementPlacement.INSIDE); } catch(e){ log.push(nm + ':move ERR'); }

  var b = nl.bounds;
  var cy = (b[1] + b[3]) / 2;
  log.push(nm + ' @' + Math.round(b[0]) + ',' + Math.round(b[1]) +
           ' ' + Math.round(b[2]-b[0]) + 'x' + Math.round(b[3]-b[1]) +
           (Math.abs(cy - wantY) < 1.5 ? ' OK' : ' WANT y' + wantY));
}

// 存盘 + 导出
var out = new File('D:/DeepSeek Harness/workspace1/osu_score_template_v1.psd');
var opt = new PhotoshopSaveOptions();
opt.alphaChannels = true; opt.layers = true; opt.embedColorProfile = true;
doc.saveAs(out, opt, true);
var pf = new File('D:/DeepSeek Harness/workspace1/osu_score_template_v1_skeleton.png');
var po = new PNGSaveOptions(); po.compression = 6; po.interlaced = false;
doc.saveAs(pf, po, true);
log.push('saved + png');

log.join(' | ');
