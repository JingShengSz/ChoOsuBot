app.displayDialogs = DialogModes.NO;
app.preferences.rulerUnits = Units.PIXELS;
var source = app.activeDocument;
var target = source.duplicate('osu_score_rankSS_preview', false);
function find(ls, name) {
 for(var i=0;i<ls.length;i++) {
  if(ls[i].name===name) return ls[i];
  if(ls[i].typename==='LayerSet') {var r=find(ls[i].layers,name); if(r)return r;}
 }
 return null;
}
function importLayer(path, name, group) {
 var d=app.open(new File(path));
 var l=d.layers[0].duplicate(target,ElementPlacement.PLACEATBEGINNING);
 d.close(SaveOptions.DONOTSAVECHANGES); app.activeDocument=target;
 l.name=name; l.move(group,ElementPlacement.INSIDE); return l;
}
var board=find(target.layers,'signboard');
var d=app.open(new File('D:/Cho Osu Bot/template/assets/signboards/character_SS_paper.png'));
d.resizeImage(UnitValue(643,'px'),null,72,ResampleMethod.BICUBIC);
d.resizeCanvas(UnitValue(1920,'px'),UnitValue(1080,'px'),AnchorPosition.BOTTOMRIGHT);
d.saveAs(new File('D:/Cho Osu Bot/template/assets/signboards/signboard_SS.png'),new PNGSaveOptions(),true);
var charLayer=d.layers[0].duplicate(target,ElementPlacement.PLACEATBEGINNING);
d.close(SaveOptions.DONOTSAVECHANGES);app.activeDocument=target;
charLayer.name='signboard_ss_paper';charLayer.move(board,ElementPlacement.INSIDE);
for(var i=0;i<board.layers.length;i++)board.layers[i].visible=(board.layers[i]===charLayer);
var glow=importLayer('D:/Cho Osu Bot/template/assets/rank_svg/glow_SS.png','rank_glow_ss',board);
glow.blendMode=BlendMode.SCREEN;
glow.move(board.layers[board.layers.length-1],ElementPlacement.PLACEAFTER);
var bg=find(target.layers,'bg');
var old=find(target.layers,'_deco_bg_gradient'); if(old)old.visible=false;
var tint=importLayer('D:/Cho Osu Bot/template/assets/rank_svg/tint_SS.png','_deco_bg_gradient_ss',bg);
var color=new SolidColor();color.rgb.hexValue='FFCB3D';
find(target.layers,'accuracy').textItem.color=color;
var root=find(target.layers,'TEMPLATE_ROOT');
for(var i=0;i<root.layers.length;i++)if(root.layers[i].typename==='LayerSet')root.layers[i].visible=true;
var opt=new PhotoshopSaveOptions();opt.layers=true;opt.embedColorProfile=true;opt.alphaChannels=true;
target.saveAs(new File('D:/Cho Osu Bot/template/osu_score_rankSS_preview.psd'),opt,false);
target.saveAs(new File('D:/Cho Osu Bot/design/FINAL_SS_paper_preview.png'),new PNGSaveOptions(),true);
return {documentId:target.id,characterBounds:charLayer.bounds.toString(),preview:'D:/Cho Osu Bot/design/FINAL_SS_paper_preview.png'};
