app.displayDialogs = DialogModes.NO;
var LOG = [];
for (var i = app.documents.length - 1; i >= 0; i--){
  var d = app.documents[i];
  if (d.name.indexOf('osu_score_template_v1') === 0) continue;
  var n = d.name; d.close(SaveOptions.DONOTSAVECHANGES); LOG.push('closed ' + n);
}
var D = 'D:/DeepSeek Harness/workspace1/panel_options_75/';
var FILES = ['C_30_vs_75.png','compare_all.png','C_frosted.png','detail_C_2x.png','detail_C_right_2x.png','B_static.png','A_no_panel.png'];
for (var k = 0; k < FILES.length; k++){
  try {
    var nd = app.open(new File(D + FILES[k]));
    app.activeDocument = nd;
    try { app.runMenuItem(stringIDToTypeID('fitOnScreen')); } catch(e1){}
    LOG.push('opened ' + nd.name);
  } catch(e){ LOG.push('ERR ' + FILES[k]); }
}
LOG.join('\n');
