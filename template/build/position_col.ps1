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
if (!l) { "MISS __NAME__"; } else {
  var b = l.bounds;
  var dx = __X__ - b[0], dy = __Y__ - b[1];
  l.translate(dx, dy);
  "ok";
}
'@

foreach ($t in $targets) {
  $js = $tmpl.Replace('__NAME__', $t.n).Replace('__X__', [string]$t.x).Replace('__Y__', [string]$t.y)
  Set-Content -Encoding UTF8 "$M\pos_one.jsx" -Value $js
  try { $null = $ps.DoJavaScript((Get-Content -Raw "$M\pos_one.jsx")) } catch { Write-Output "$($t.n) ERR $($_.Exception.Message)" }
  Start-Sleep -Milliseconds 150
}

# verify in a fresh call
$q = @'
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
var N = ["_deco_total_pp_label","total_pp","_deco_pp_label","pp","_deco_pp_max_label","pp_max",
         "_deco_score_label","score","_deco_combo_label","max_combo","_deco_map_combo_label",
         "map_max_combo","_deco_accuracy_label","accuracy","_deco_accuracy_lazer_label","accuracy_lazer"];
var L = [];
for (var i = 0; i < N.length; i++){
  var l = find(target.layers, N[i]);
  var b = l.bounds;
  L.push(N[i] + "  " + [Math.round(b[0]),Math.round(b[1]),Math.round(b[2]),Math.round(b[3])].join(","));
}
L.join("\n");
'@
Set-Content -Encoding UTF8 "$M\q_pos.jsx" -Value $q
Write-Output $ps.DoJavaScript((Get-Content -Raw "$M\q_pos.jsx"))