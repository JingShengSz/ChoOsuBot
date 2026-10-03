$M = 'D:\Cho Osu Bot\template\build'
$ps = New-Object -ComObject Photoshop.Application

$targets = @(
  @{n='star_strip'; x=75;  y=326},
  @{n='od_bar';     x=60;  y=520},
  @{n='hp_bar';     x=60;  y=588}
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
var was = [Math.round(b0[0]),Math.round(b0[1])].join(",");
l.translate(-(__X__ - b0[0]), -(__Y__ - b0[1]));
var b1 = l.bounds;
"__NAME__|" + was + "|" + [Math.round(b1[0]),Math.round(b1[1]),Math.round(b1[2]),Math.round(b1[3])].join(",");
'@

foreach ($t in $targets) {
  $js = $tmpl.Replace('__NAME__', $t.n).Replace('__X__', [string]$t.x).Replace('__Y__', [string]$t.y)
  Set-Content -Encoding UTF8 "$M\pos_raster.jsx" -Value $js
  try { Write-Output $ps.DoJavaScript((Get-Content -Raw "$M\pos_raster.jsx")) }
  catch { Write-Output "$($t.n) ERR $($_.Exception.Message)" }
  Start-Sleep -Milliseconds 200
}