app.displayDialogs = DialogModes.NO;
var target = null;
for (var q = 0; q < app.documents.length; q++){
  if (app.documents[q].name.indexOf('osu_score_template_v1') === 0) target = app.documents[q];
}
if (!target) throw new Error('template document not open');
app.activeDocument = target;
var LOG = ['active = ' + target.name];

function find(set, name){
  for (var i = 0; i < set.length; i++){
    var l = set[i];
    if (l.name === name) return l;
    if (l.typename === 'LayerSet'){ var r = find(l.layers, name); if (r) return r; }
  }
  return null;
}
function bb(l){ var b = l.bounds; return [Math.round(b[0]),Math.round(b[1]),Math.round(b[2]),Math.round(b[3])].join(','); }

var title  = find(target.layers, 'beatmap_title');
var artist = find(target.layers, 'beatmap_artist');

title.textItem.contents  = '\u8133\u5473\u564c\u30ea\u30b8\u30c3\u30c9\u30ac\u30fc\u30eb';
artist.textItem.contents = '\u68ee\u7f85\u4e07\u8c61';

var CAND = [
  ['inter',  'Inter18pt-Medium'],
  ['yugoth', 'YuGothic-Medium'],
  ['notosc', 'NotoSansSC-Medium'],
  ['yahei',  'MicrosoftYaHei']
];

for (var i = 0; i < CAND.length; i++){
  var tag = CAND[i][0], fontName = CAND[i][1];
  var got = '?';
  try {
    title.textItem.font  = fontName;
    artist.textItem.font = fontName;
    got = title.textItem.font;
  } catch(e){ LOG.push(tag + ' FONT ERR ' + e); }
  LOG.push(tag + ' requested=' + fontName + ' got=' + got +
           '  title=' + bb(title) + '  artist=' + bb(artist));
  target.saveAs(new File('D:/DeepSeek Harness/workspace1/_test/title_' + tag + '.png'),
                new PNGSaveOptions(), true);
}

LOG.join('\n');
