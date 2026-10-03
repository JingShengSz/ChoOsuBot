app.displayDialogs = DialogModes.NO;
var d = app.open(new File("D:/Cho Osu Bot/template/osu_score_template_v1.psd"));
"  PSD 打开 OK: " + d.name + " " + Math.round(d.width) + "x" + Math.round(d.height) + "  组数=" + d.layerSets.getByName("TEMPLATE_ROOT").layers.length;
