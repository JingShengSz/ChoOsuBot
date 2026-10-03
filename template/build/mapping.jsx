var doc = app.activeDocument;
var root = doc.layerSets.getByName('TEMPLATE_ROOT');

var FREE_W = {
  'beatmap_title':600,'beatmap_artist':600,'beatmap_difficulty':600,
  'beatmap_mapper':600,'beatmap_id':600,
  'star_rating':550,'bpm':550,'od':550,'hp':550,
  'total_pp':520,'pp':240,'pp_max':240,'accuracy':240,'accuracy_lazer':240,
  'score':500,'max_combo':240,'map_max_combo':240,
  'count_max':126,'count_300':126,'count_200':126,'count_100':126,'count_50':126,'count_miss':126,
  'player_name':520,'rank_change':520,'play_date':500
};
var NUMERIC = { total_pp:1,pp:1,pp_max:1,accuracy:1,accuracy_lazer:1,score:1,
  max_combo:1,map_max_combo:1,count_max:1,count_300:1,count_200:1,count_100:1,
  count_50:1,count_miss:1,star_rating:1,bpm:1,od:1,hp:1,rank_change:1 };

var TS='Sakura -sakura- -sakura- -sakura-';
var NS='0123456789,.%xpBPM';
var cache={};
function ppc(f,s,sample){
  var k=f+'|'+s+'|'+sample;
  if (cache[k]!==undefined) return cache[k];
  var l=doc.artLayers.add(); l.kind=LayerKind.TEXT;
  var t=l.textItem;
  t.contents=sample; t.font=f; t.size=new UnitValue(s,'px'); t.position=[0,0];
  var b=null; try{b=l.bounds;}catch(e){}
  var w = b ? (b[2]-b[0]) : 0;
  try{l.remove();}catch(e){}
  cache[k]=Math.round((w/sample.length)*100)/100;
  return cache[k];
}
function esc(s){ return String(s).replace(/\\/g,'\\\\').replace(/"/g,'\\"').replace(/[\r\n\t]/g,' '); }
function N(v){ return (v===null||v===undefined)?'null':Math.round(v*100)/100; }

var rows=[], tc=0, rc=0, hc=0;
for (var g=0; g<root.layerSets.length; g++){
  var gs = root.layerSets[g];
  for (var i=0; i<gs.layers.length; i++){
    var l = gs.layers[i];
    if (l.typename === 'LayerSet') continue;
    if (!l.visible) hc++;
    var o = '{"group":"' + esc(gs.name) + '","name":"' + esc(l.name) + '"';
    if (l.kind === LayerKind.TEXT){
      var t = l.textItem;
      var pos=[0,0], fs=0, fnt='', con='', hex='', just='';
      try{pos=t.position;}catch(e){} try{fs=t.size.value;}catch(e){}
      try{fnt=t.font;}catch(e){} try{con=t.contents;}catch(e){}
      try{hex=t.color.rgb.hexValue;}catch(e){} try{just=String(t.justification);}catch(e){}
      var fw = FREE_W[l.name], mch = 'null';
      if (fw !== undefined && fs > 0){
        var s = NUMERIC[l.name] ? NS : TS;
        var p = ppc(fnt, fs, s);
        if (p > 0) mch = Math.floor(fw / p);
      }
      o += ',"kind":"text","font":"' + esc(fnt) + '","sizePx":' + N(fs) + ',"color":"#' + esc(hex) + '"';
      o += ',"x":' + N(pos[0]) + ',"y":' + N(pos[1]) + ',"justify":"' + esc(just) + '"';
      o += ',"example":"' + esc(con) + '"';
      o += ',"freeWidthPx":' + (fw!==undefined ? fw : 'null') + ',"maxChars":' + mch;
      tc++;
    } else {
      var b2=[0,0,0,0]; try{b2=l.bounds;}catch(e){}
      o += ',"kind":"raster","left":' + N(b2[0]) + ',"top":' + N(b2[1]) + ',"right":' + N(b2[2]) + ',"bottom":' + N(b2[3]);
      rc++;
    }
    o += ',"visible":' + l.visible + '}';
    rows.push(o);
  }
}

var out = '{\n  "template": "osu_score_template_v1",\n  "canvas": "1920x1080 @72dpi RGB",\n'
 + '  "layout": "LEFT column = beatmap info | RIGHT column = player info | bottom full-width = judgement + mods | illustration right (1277-1920)",\n'
 + '  "fonts": "Montserrat Black / Inter 18pt Bold-Medium-Regular",\n'
 + '  "note": "Text x/y is the Photoshop text origin (~baseline), NOT the visual top-left. maxChars = floor(freeWidthPx / measured px-per-char). The PLUGIN must truncate to maxChars and append an ellipsis - Photoshop has no auto-truncation.",\n'
 + '  "layer_count": ' + rows.length + ',\n  "layers": [\n    ' + rows.join(',\n    ') + '\n  ]\n}\n';

var f = new File('D:/DeepSeek Harness/workspace1/layer_mapping.json');
f.encoding='UTF-8'; f.open('w'); f.write(out); f.close();
'bytes=' + out.length + ' text=' + tc + ' raster=' + rc + ' hidden=' + hc
