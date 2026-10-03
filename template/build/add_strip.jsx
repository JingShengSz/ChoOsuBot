app.displayDialogs = DialogModes.NO;
var target = app.activeDocument;
var root = target.layerSets.getByName('TEMPLATE_ROOT');
var gStats = root.layerSets.getByName('beatmap_stats');
var log = [];

var SVG = 'D:/DeepSeek Harness/workspace1/_icons/fit10_7.32.svg';
var TARGET_W = 600, BOX_X = 60, BOX_Y = 310;

// ---- 0. drop the mis-positioned copy from the previous run ----
try { gStats.artLayers.getByName('star_strip').remove(); log.push('removed bad copy'); }
catch(e){ log.push('no old copy'); }

// ---- 1. open + normalise ----
var sd = app.open(new File(SVG));
var sw = sd.width.value, sh = sd.height.value;
if (Math.abs(sw - TARGET_W) > 0.5) {
  sd.resizeImage(UnitValue(TARGET_W,'px'), UnitValue(Math.round(sh*(TARGET_W/sw)),'px'),
                 null, ResampleMethod.BICUBICSHARPER);
}
var srcLayer = sd.layers[0];
var si = srcLayer.bounds;                    // ink bounds -> gives the padding offset
var offX = si[0], offY = si[1];
log.push('svg ' + Math.round(sd.width.value) + 'x' + Math.round(sd.height.value) +
         ' ink offset ' + Math.round(offX) + ',' + Math.round(offY));

// ---- 2. bring it in, then align so the BOX (not the ink) lands on target ----
var nl = srcLayer.duplicate(target, ElementPlacement.PLACEATBEGINNING);
sd.close(SaveOptions.DONOTSAVECHANGES);
app.activeDocument = target;
nl.name = 'star_strip';
try { nl.move(gStats, ElementPlacement.INSIDE); } catch(e){ log.push('move ERR'); }

var b1 = nl.bounds;
nl.translate((BOX_X + offX) - b1[0], (BOX_Y + offY) - b1[1]);
var b2 = nl.bounds;
var gx = Math.round(b2[0] - offX), gy = Math.round(b2[1] - offY);
log.push('box at ' + gx + ',' + gy + (gx === BOX_X && gy === BOX_Y ? ' OK' : ' EXPECTED ' + BOX_X + ',' + BOX_Y));

// ---- 3. save + export ----
var out = new File('D:/DeepSeek Harness/workspace1/osu_score_template_v1.psd');
var opt = new PhotoshopSaveOptions();
opt.alphaChannels = true; opt.layers = true; opt.embedColorProfile = true;
target.saveAs(out, opt, true);
var pf = new File('D:/DeepSeek Harness/workspace1/osu_score_template_v1_skeleton.png');
var po = new PNGSaveOptions(); po.compression = 6; po.interlaced = false;
target.saveAs(pf, po, true);
log.push('saved + png');

log.join(' | ');
