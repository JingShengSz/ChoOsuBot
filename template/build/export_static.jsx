app.displayDialogs = DialogModes.NO;
/* 给 Pillow 渲染器抽模板里的「静态内容」。

为什么需要：走 Photoshop 那条路时，模板自带的 _deco_* 标签、判定图标、属性图标
都是现成的，插件不用管。PIL 渲染器只画插件提供的东西，所以这些全丢了
（第一版对比里 PIL 少了 TOTAL PP / JUDGEMENT 等一堆标签和图标）。

这里导出两样：
  1. static_overlay.png —— 除了「插件会控制的东西」以外的一切，透明底全画布
  2. signboards/signboard_s.png、signboard_b.png —— 立绘单独全画布导出

要隐藏的「动态」内容：
  组：bg / panel / signboard
  位图层：player_avatar / star_strip / od_bar / hp_bar / mod_1..6
  文字层：插件 to_layers() 会写的那些 + mod_N_mult
*/

var OUT = "D:/Cho Osu Bot/template/assets/";
var d = app.open(new File("D:/Cho Osu Bot/template/osu_score_template_v1.psd"));

function find(set, name){
  for (var i = 0; i < set.length; i++){
    var l = set[i];
    if (l.name === name) return l;
    if (l.typename === "LayerSet"){ var r = find(l.layers, name); if (r) return r; }
  }
  return null;
}

/* 插件控制的文字层名（= card.py to_layers() 的键 + mod 倍率） */
var DYN_TEXT = {};
var names = ["beatmap_title","beatmap_artist","beatmap_difficulty","beatmap_mapper","beatmap_id",
             "bpm","od","hp","star_rating","player_name","total_pp","rank_change","play_date",
             "score","pp","pp_max","accuracy","accuracy_lazer","max_combo","map_max_combo",
             "count_max","count_300","count_200","count_100","count_50","count_miss",
             "server_tag",
             "mod_1_mult","mod_2_mult","mod_3_mult","mod_4_mult","mod_5_mult","mod_6_mult"];
for (var i = 0; i < names.length; i++) DYN_TEXT[names[i]] = true;

var DYN_RASTER = {};
var rnames = ["player_avatar","star_strip","od_bar","hp_bar","rank_glow",
              "mod_1","mod_2","mod_3","mod_4","mod_5","mod_6"];
for (var i = 0; i < rnames.length; i++) DYN_RASTER[rnames[i]] = true;

var HIDE_GROUPS = { bg: true, panel: true, signboard: true };

var saved = [];
function snapshot(set){
  for (var i = 0; i < set.length; i++){
    var l = set[i];
    saved.push([l, l.visible]);
    if (l.typename === "LayerSet") snapshot(l.layers);
  }
}
snapshot(d.layers);

function setVis(set, parentHidden){
  for (var i = 0; i < set.length; i++){
    var l = set[i];
    if (l.typename === "LayerSet"){
      if (HIDE_GROUPS[l.name] === true){ l.visible = false; setVis(l.layers, true); }
      else { setVis(l.layers, parentHidden); }
      continue;
    }
    if (parentHidden) continue;
    if (l.name === "doc_bg"){ l.visible = false; continue; }
    if (DYN_TEXT[l.name] === true){ l.visible = false; continue; }
    if (DYN_RASTER[l.name] === true){ l.visible = false; continue; }
    /* 其余层**保持模板原样** —— 之前这里写的是 l.visible = true，
       把模板故意藏起来的东西（_deco_watermark_hint 之类的设计提示、
       还有别的一些隐藏层）全放出来了，结果 PIL 出的图上多出一块
       白色残影和一行 "watermark slot 180x60"。参照物是模板本身，
       所以原样保留才对。 */
  }
}
setVis(d.layers, false);

var png = new PNGSaveOptions();
png.compression = 6;
d.saveAs(new File(OUT + "static_overlay.png"), png, true);

/* ---- 立绘单独导出 ---- */
function exportSignboard(name){
  var board = find(d.layers, "signboard");
  if (!board) return name + ": 找不到 signboard 组";
  var found = null;
  for (var i = 0; i < board.layers.length; i++){
    if (board.layers[i].name === name) found = board.layers[i];
  }
  if (!found) return name + ": 不存在";

  /* 关键：必须把 TEMPLATE_ROOT 下**其他所有组也关掉**。
     只关 signboard 组内的兄弟层是不够的 —— 那样 player_info / beatmap_stats /
     mods_block 等组仍然可见，会把整套数据界面（小标签、图标、分隔线）
     一起烤进 signboard_*.png。结果就是每张立绘素材都带着一份完整界面，
     render.py 把它们叠上去之后 9 个评级看起来一模一样。 */
  var root = find(d.layers, "TEMPLATE_ROOT");
  var reShow = [];
  for (var g = 0; g < root.layers.length; g++){
    var grp = root.layers[g];
    if (grp.typename === "LayerSet" && grp !== board){
      reShow.push([grp, grp.visible]);
      grp.visible = false;
    }
  }

  board.visible = true;
  for (var i = 0; i < board.layers.length; i++){
    board.layers[i].visible = (board.layers[i].name === name);
  }
  d.saveAs(new File(OUT + "signboards/" + name + ".png"), png, true);
  board.visible = false;

  for (var r = 0; r < reShow.length; r++){ reShow[r][0].visible = reShow[r][1]; }

  return name + ": 导出 " +
    [Math.round(found.bounds[0]),Math.round(found.bounds[1]),
     Math.round(found.bounds[2]),Math.round(found.bounds[3])].join(",");
}
var r1 = exportSignboard("signboard_s");
var r2 = exportSignboard("signboard_b");
var r3 = exportSignboard("signboard_c");
var r4 = exportSignboard("signboard_ss");
var r5 = exportSignboard("signboard_f");
var r6 = exportSignboard("signboard_d");
var r7 = exportSignboard("signboard_a");

/* ---- 还原可见性 ---- */
for (var i = 0; i < saved.length; i++){ saved[i][0].visible = saved[i][1]; }

"static_overlay.png 已导出\n" + r1 + "\n" + r2 + "\n" + r3 + "\n" + r4 + "\n" + r5 + "\n" + r6 + "\n" + r7;
