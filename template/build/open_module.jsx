app.displayDialogs = DialogModes.NO;
var LOG = [];
for (var i = app.documents.length - 1; i >= 0; i--){
  var d = app.documents[i];
  if (d.name.indexOf('osu_score_template_v1') === 0) continue;
  var n = d.name; d.close(SaveOptions.DONOTSAVECHANGES); LOG.push('closed ' + n);
}
var F = [
  'D:/DeepSeek Harness/workspace1/osu-score-card/template/osu_score_template_v1_skeleton.png',
  'D:/DeepSeek Harness/workspace1/osu-score-card/design/FINAL_C_75_realdata.png',
  'D:/DeepSeek Harness/workspace1/osu-score-card/design/FINAL_right_column_2x.png',
  'D:/DeepSeek Harness/workspace1/osu-score-card/design/panel_options_75/C_30_vs_75.png'
];
for (var k = 0; k < F.length; k++){
  try {
    var nd = app.open(new File(F[k]));
    app.activeDocument = nd;
    try { app.runMenuItem(stringIDToTypeID('fitOnScreen')); } catch(e1){}
    LOG.push('opened ' + nd.name);
  } catch(e){ LOG.push('ERR ' + F[k]); }
}
LOG.join('\n');
