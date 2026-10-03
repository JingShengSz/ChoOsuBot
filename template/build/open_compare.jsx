app.displayDialogs = DialogModes.NO;
var FILES = [
  'D:/DeepSeek Harness/workspace1/panel_options/compare_all.png',
  'D:/DeepSeek Harness/workspace1/panel_options/A_no_panel.png',
  'D:/DeepSeek Harness/workspace1/panel_options/B_static.png',
  'D:/DeepSeek Harness/workspace1/panel_options/C_frosted.png'
];
var LOG = [];
for (var i = 0; i < FILES.length; i++){
  try {
    var d = app.open(new File(FILES[i]));
    app.activeDocument = d;
    try { app.runMenuItem(stringIDToTypeID('fitOnScreen')); }
    catch(e1){ try { app.runMenuItem(charIDToTypeID('FtOn')); } catch(e2){ LOG.push('fit n/a'); } }
    LOG.push('opened ' + d.name + ' ' + d.width + 'x' + d.height);
  } catch(e){ LOG.push('ERR ' + FILES[i] + ' : ' + e); }
}
LOG.push('total docs = ' + app.documents.length);
LOG.join('\n');
