app.displayDialogs = DialogModes.NO;
var doc = app.activeDocument;
var root = doc.layerSets.getByName('TEMPLATE_ROOT');
var gStats = root.layerSets.getByName('beatmap_stats');
var log = [];

// bpm 是最初版遗留的暗灰，属性网格里三个数值应当同色
var before = '', after = '';
var b = gStats.artLayers.getByName('bpm');
try { before = b.textItem.color.rgb.hexValue; } catch(e){}
var c = new SolidColor(); c.rgb.hexValue = 'EAEEF6';   // 与 od / hp 一致
b.textItem.color = c;
try { after = b.textItem.color.rgb.hexValue; } catch(e){}
log.push('bpm colour ' + before + ' -> ' + after);

// 复核三个数值现在是否同色同号
var names = ['bpm','od','hp'];
for (var i = 0; i < names.length; i++){
  var t = gStats.artLayers.getByName(names[i]).textItem;
  log.push(names[i] + ' ' + Math.round(t.size.value) + 'px #' + t.color.rgb.hexValue);
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
