app.displayDialogs = DialogModes.NO;
var LOG = [];

/* close every document that is not the working PSD */
for (var i = app.documents.length - 1; i >= 0; i--){
  var d = app.documents[i];
  if (d.name.indexOf('osu_score_template_v1') === 0) continue;
  var n = d.name;
  d.close(SaveOptions.DONOTSAVECHANGES);
  LOG.push('closed ' + n);
}

var FILES = [
  'D:/DeepSeek Harness/workspace1/_test/panel_out/compare_all.png',
  'D:/DeepSeek Harness/workspace1/_test/panel_out/B_static.png',
  'D:/DeepSeek Harness/workspace1/_test/panel_out/detail_B_2x.png',
  'D:/DeepSeek Harness/workspace1/_test/panel_out/A_no_panel.png',
  'D:/DeepSeek Harness/workspace1/_test/panel_out/C_frosted.png'
];
for (var k = 0; k < FILES.length; k++){
  try {
    var nd = app.open(new File(FILES[k]));
    app.activeDocument = nd;
    try { app.runMenuItem(stringIDToTypeID('fitOnScreen')); } catch(e1){}
    LOG.push('opened ' + nd.name + ' ' + nd.width + 'x' + nd.height);
  } catch(e){ LOG.push('ERR ' + FILES[k] + ' : ' + e); }
}
LOG.join('\n');
