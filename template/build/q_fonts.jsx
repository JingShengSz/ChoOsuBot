var f = app.fonts, L = [], pats = ['Yu Gothic','Noto','Source Han','Meiryo','MS Gothic','YaHei','SimHei','MSung','Malgun','Hiragino','DengXian','SimSun'];
for (var i = 0; i < f.length; i++){
  var n = f[i].name, ps = f[i].postScriptName;
  for (var j = 0; j < pats.length; j++){
    if (n.indexOf(pats[j]) >= 0 || ps.indexOf(pats[j]) >= 0) { L.push(n + '  |  ' + ps + '  |  ' + f[i].family); break; }
  }
}
'CJK-ish fonts found: ' + L.length + '\n' + L.join('\n');
