$M = 'D:\Cho Osu Bot\template\build'
$ps = New-Object -ComObject Photoshop.Application

$rows = @(
  @{n='_deco_total_pp_label';        p='primary_stats';   t='TOTAL PP';   f='Inter18pt-Regular'; s=15; c='#8C96A9'; x=720; y=294},
  @{n='total_pp';                    p='primary_stats';   t='12,345pp';   f='Inter18pt-Bold';    s=30; c='#EAEEF6'; x=721; y=315},
  @{n='_deco_pp_label';              p='primary_stats';   t='PP';         f='Inter18pt-Regular'; s=15; c='#8C96A9'; x=721; y=371},
  @{n='pp';                          p='primary_stats';   t='148pp';      f='Inter18pt-Bold';    s=62; c='#EAEEF6'; x=722; y=395},
  @{n='_deco_pp_max_label';          p='primary_stats';   t='MAX PP';     f='Inter18pt-Regular'; s=15; c='#8C96A9'; x=981; y=371},
  @{n='pp_max';                      p='primary_stats';   t='612pp';      f='Inter18pt-Bold';    s=36; c='#8C97A9'; x=981; y=395},
  @{n='_deco_score_label';           p='secondary_stats'; t='SCORE';      f='Inter18pt-Regular'; s=15; c='#8C96A9'; x=720; y=476},
  @{n='score';                       p='secondary_stats'; t='984,196';    f='Inter18pt-Bold';    s=46; c='#EAEEF6'; x=722; y=500},
  @{n='_deco_combo_label';           p='secondary_stats'; t='COMBO';      f='Inter18pt-Regular'; s=15; c='#8C96A9'; x=720; y=567},
  @{n='max_combo';                   p='secondary_stats'; t='2,922x';     f='Inter18pt-Bold';    s=46; c='#8C97A9'; x=722; y=591},
  @{n='_deco_map_combo_label';       p='secondary_stats'; t='MAP COMBO';  f='Inter18pt-Regular'; s=15; c='#8C96A9'; x=981; y=567},
  @{n='map_max_combo';               p='secondary_stats'; t='2,922x';     f='Inter18pt-Bold';    s=30; c='#8C97A9'; x=981; y=591},
  @{n='_deco_accuracy_label';        p='primary_stats';   t='ACCURACY';   f='Inter18pt-Regular'; s=15; c='#8C96A9'; x=720; y=658},
  @{n='accuracy';                    p='primary_stats';   t='99.89%';     f='Inter18pt-Bold';    s=62; c='#EAEEF6'; x=722; y=682},
  @{n='_deco_accuracy_lazer_label';  p='primary_stats';   t='LAZER ACC';  f='Inter18pt-Regular'; s=15; c='#8C96A9'; x=981; y=658},
  @{n='accuracy_lazer';              p='primary_stats';   t='99.53%';     f='Inter18pt-Bold';    s=26; c='#8C97A9'; x=981; y=682}
)

$tmpl = @'
app.displayDialogs = DialogModes.NO;
var target = null;
for (var q = 0; q < app.documents.length; q++){
  if (app.documents[q].name.indexOf("osu_score_template_v1") === 0) target = app.documents[q];
}
if (!target) throw new Error("template not open");
app.activeDocument = target;
function find(set, name){
  for (var i = 0; i < set.length; i++){
    var l = set[i];
    if (l.name === name) return l;
    if (l.typename === "LayerSet"){ var r = find(l.layers, name); if (r) return r; }
  }
  return null;
}
var NAME="__NAME__", PARENT="__PARENT__", TEXT="__TEXT__", FONT="__FONT__";
var SIZE=__SIZE__, HEX="__HEX__", TX=__X__, TY=__Y__;
var old = find(target.layers, NAME);
var parent = find(target.layers, PARENT);
if (old) {
  if (old.parent && old.parent.name === PARENT) { old.remove(); }
  else { old.parent.remove(); }
}
var nl = parent.artLayers.add();
nl.kind = LayerKind.TEXT;
nl.name = NAME;
nl.textItem.contents = TEXT;
nl.textItem.font = FONT;
nl.textItem.size = SIZE;
var sc = new SolidColor();
sc.rgb.red   = parseInt(HEX.substr(1,2),16);
sc.rgb.green = parseInt(HEX.substr(3,2),16);
sc.rgb.blue  = parseInt(HEX.substr(5,2),16);
nl.textItem.color = sc;
var b = nl.bounds;
nl.translate(TX - b[0], TY - b[1]);
var b2 = nl.bounds;
NAME + "  parent=" + parent.name + "  b=" + [Math.round(b2[0]),Math.round(b2[1]),Math.round(b2[2]),Math.round(b2[3])].join(",");
'@

foreach ($r in $rows) {
  $js = $tmpl
  $js = $js.Replace('__NAME__',   $r.n)
  $js = $js.Replace('__PARENT__', $r.p)
  $js = $js.Replace('__TEXT__',   $r.t)
  $js = $js.Replace('__FONT__',   $r.f)
  $js = $js.Replace('__SIZE__',   [string]$r.s)
  $js = $js.Replace('__HEX__',    $r.c)
  $js = $js.Replace('__X__',      [string]$r.x)
  $js = $js.Replace('__Y__',      [string]$r.y)
  Set-Content -Encoding UTF8 "$M\rebuild_one.jsx" -Value $js
  try { Write-Output $ps.DoJavaScript((Get-Content -Raw "$M\rebuild_one.jsx")) }
  catch { Write-Output "$($r.n)  ERR $($_.Exception.Message)" }
}