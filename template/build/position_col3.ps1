$M = 'D:\Cho Osu Bot\template\build'
$ps = New-Object -ComObject Photoshop.Application

$targets = @(
  @{n='_deco_total_pp_label';       x=720; y=294},
  @{n='total_pp';                   x=721; y=315},
  @{n='_deco_pp_label';             x=720; y=371},
  @{n='pp';                         x=722; y=395},
  @{n='_deco_pp_max_label';         x=981; y=371},
  @{n='pp_max';                     x=981; y=395},
  @{n='_deco_score_label';          x=720; y=476},
  @{n='score';                      x=722; y=500},
  @{n='_deco_combo_label';          x=720; y=567},
  @{n='max_combo';                  x=722; y=591},
  @{n='_deco_map_combo_label';      x=981; y=567},
  @{n='map_max_combo';              x=981; y=591},
  @{n='_deco_accuracy_label';       x=720; y=658},
  @{n='accuracy';                   x=722; y=682},
  @{n='_deco_accuracy_lazer_label'; x=981; y=658},
  @{n='accuracy_lazer';             x=981; y=682}
)

$tmpl = @'
app.displayDialogs = DialogModes.NO;
var target = null;
for (var q = 0; q < app.documents.length; q++){
  if (app.documents[q].name.indexOf("osu_score_template_v1") === 0) target = app.documents[q];
}
app.activeDocument = target;
function find(set, name){
  for (var i = 0; i < set.length; i++){
    var l = set[i];
    if (l.name === name) return l;
    if (l.typename === "LayerSet"){ var r = find(l.layers, name); if (r) return r; }
  }
  return null;
}
var l = find(target.layers, "__NAME__");
var b0 = l.bounds;
var raw = [Math.round(b0[0]),Math.round(b0[1])].join(",");
var dx = __X__ - b0[0], dy = __Y__ - b0[1];
l.translate(-dx, -dy);
var b1 = l.bounds;
"__NAME__|" + raw + "|" + [Math.round(b1[0]),Math.round(b1[1]),Math.round(b1[2]),Math.round(b1[3])].join(",");
'@

foreach ($t in $targets) {
  $js = $tmpl.Replace('__NAME__', $t.n).Replace('__X__', [string]$t.x).Replace('__Y__', [string]$t.y)
  Set-Content -Encoding UTF8 "$M\pos_one.jsx" -Value $js
  try { Write-Output $ps.DoJavaScript((Get-Content -Raw "$M\pos_one.jsx")) }
  catch { Write-Output "$($t.n) ERR $($_.Exception.Message)" }
  Start-Sleep -Milliseconds 150
}