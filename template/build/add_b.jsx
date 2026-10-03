app.displayDialogs = DialogModes.NO;
var doc = app.activeDocument;
var root = doc.layerSets.getByName('TEMPLATE_ROOT');
var gSign = root.layerSets.getByName('signboard');
var log = [];

var SRC = 'D:/DeepSeek Harness/workspace1/_icons/b_rank_alpha.png';
var MATCH_W = 643;          // 与 S 那张同宽（实测 S 的框宽）
var BOX_RIGHT = 1920;       // 框右边缘贴画布右边
var BOX_BOTTOM = 1080;      // 框底边贴画布底边

// ---- 1. 读入抠好的 B 立绘，缩到与 S 同宽 ----
var sd = app.open(new File(SRC));
var sw = sd.width.value, sh = sd.height.value;
var nh = Math.round(sh * (MATCH_W / sw));
sd.resizeImage(UnitValue(MATCH_W,'px'), UnitValue(nh,'px'), null, ResampleMethod.BICUBICSHARPER);
log.push('resized ' + Math.round(sw) + 'x' + Math.round(sh) + ' -> ' + MATCH_W + 'x' + nh);

var srcLayer = sd.layers[0];
var si = srcLayer.bounds;                 // 墨迹边界（透明边距需补偿）
var offX = si[0], offY = si[1];

// ---- 2. 复制进模板的 signboard 组 ----
var nl = srcLayer.duplicate(doc, ElementPlacement.PLACEATBEGINNING);
sd.close(SaveOptions.DONOTSAVECHANGES);
app.activeDocument = doc;
nl.name = 'signboard_b';
try { nl.move(gSign, ElementPlacement.INSIDE); } catch(e){ log.push('move ERR'); }

// ---- 3. 定位：对齐「框」而不是「墨迹」 ----
var boxX = BOX_RIGHT - MATCH_W;
var boxY = BOX_BOTTOM - nh;
var b1 = nl.bounds;
nl.translate((boxX + offX) - b1[0], (boxY + offY) - b1[1]);
var b2 = nl.bounds;
var gx = Math.round(b2[0] - offX), gy = Math.round(b2[1] - offY);
log.push('box at ' + gx + ',' + gy + ' (want ' + boxX + ',' + boxY + ')');
log.push('ink ' + Math.round(b2[2]-b2[0]) + 'x' + Math.round(b2[3]-b2[1]) +
         '  right edge ' + Math.round(b2[2]) + '  bottom ' + Math.round(b2[3]));

// ---- 4. 切换显示：展示 B ----
try { gSign.artLayers.getByName('signboard_s').visible = false; } catch(e){}
nl.visible = true;
log.push('showing signboard_b');

// ---- 5. save + export ----
var out = new File('D:/DeepSeek Harness/workspace1/osu_score_template_v1.psd');
var opt = new PhotoshopSaveOptions();
opt.alphaChannels = true; opt.layers = true; opt.embedColorProfile = true;
doc.saveAs(out, opt, true);
var pf = new File('D:/DeepSeek Harness/workspace1/osu_score_template_v1_skeleton.png');
var po = new PNGSaveOptions(); po.compression = 6; po.interlaced = false;
doc.saveAs(pf, po, true);
log.push('saved + png');

log.join(' | ');
