export const HUD_PARTS = {
  combo: {name:'连击',x:20,y:20,w:360,h:70},
  title: {name:'难度名称',x:1300,y:20,w:600,h:32},
  bpm: {name:'BPM',x:1620,y:55,w:280,h:32},
  progress: {name:'歌曲进度',x:1500,y:100,w:400,h:30},
  accuracy: {name:'准确率',x:1380,y:998,w:520,h:40},
  cps: {name:'每秒按键',x:1600,y:968,w:300,h:30},
  judge: {name:'判定统计',x:24,y:386,w:240,h:250},
  error: {name:'判定条',x:710,y:1042,w:500,h:30},
};
const KEY='mania-hud-layout-v1';
const clamp=(n,min,max)=>Math.max(min,Math.min(max,n));
export function cleanLayout(input={}) {
  const layout={};
  for(const [id,b] of Object.entries(HUD_PARTS)) {
    const defaults=id==='error'?{...b,x:585,y:1027,w:750,h:45}:b;
    const v=input?.[id]||{};
    const num=(key,min,max)=>clamp(Number.isFinite(Number(v[key]))?Number(v[key]):defaults[key],min,max);
    const w=num('w',30,1920),h=num('h',12,1080);
    layout[id]={x:num('x',0,1920-w),y:num('y',0,1080-h),w,h,
      visible:v.visible!==false,opacity:clamp(Number.isFinite(v.opacity)?v.opacity:1,id==='error'?0:.1,1),
      text:typeof v.text==='string'?v.text.slice(0,500):'',
      color:/^#[0-9a-f]{6}$/i.test(v.color||'')?v.color:''};
    if(id==='error'){
      layout[id].beamScale=clamp(Number.isFinite(Number(v.beamScale))?Number(v.beamScale):1,.5,4);
      layout[id].beamOpacity=clamp(Number.isFinite(Number(v.beamOpacity))?Number(v.beamOpacity):1,0,1);
    }
  }
  return layout;
}

export class HudLayout {
  constructor(onChange) {
    this.onChange=onChange;
    try {this.layout=cleanLayout(JSON.parse(localStorage.getItem(KEY)||'{}'));}
    catch {this.layout=cleanLayout();}
    this.editing=false;this.selected='combo';
    this.overlay=document.getElementById('hudLayoutOverlay');
    this.panel=document.getElementById('hudLayoutPanel');
    this.panel.innerHTML=`<div class="edit-heading"><strong>画面组件</strong><button id="closeHudEdit" class="secondary">完成</button></div>
      <p class="edit-hint">拖动虚线框移动，拖动右下角调整大小。自动保存。</p>
      <label>组件<select id="hudPart">${Object.entries(HUD_PARTS).map(([id,b])=>`<option value="${id}">${b.name}</option>`).join('')}</select></label>
      <div class="edit-grid">${[['x','横向位置'],['y','纵向位置'],['w','宽度'],['h','高度']].map(([id,name])=>`<label>${name}<input type="number" id="hud-${id}" step="1"></label>`).join('')}</div>
      <label class="edit-check"><input type="checkbox" id="hud-visible">显示组件</label>
      <label class="edit-range"><span id="hud-opacity-label">组件不透明度</span><output id="hud-opacity-value"></output><input type="range" id="hud-opacity" min="10" max="100"></label>
      <label id="hud-beam-control" class="edit-range" hidden><span>光柱大小</span><output id="hud-beam-value"></output><input type="range" id="hud-beam-scale" min="0.5" max="4" step="0.1"><small>单独调整判定标记的宽度和高度</small></label>
      <label id="hud-beam-opacity-control" class="edit-range" hidden><span>光柱不透明度</span><output id="hud-beam-opacity-value"></output><input type="range" id="hud-beam-opacity" min="0" max="100" step="1"><small>只调整光柱，保留判定条和平均三角形</small></label>
      <label>自定义文字（留空显示实时数据）<textarea id="hud-text" rows="3" maxlength="500"></textarea></label>
      <label class="edit-check"><input type="checkbox" id="hud-use-color">自定义文字颜色<input type="color" id="hud-color" value="#ffffff"></label>
      <div class="edit-actions"><button id="resetHudPart" class="secondary">重置此组件</button><button id="resetHudAll" class="secondary">重置全部</button></div>`;
    const $=id=>document.getElementById(id);
    $('hudPart').onchange=()=>{this.selected=$('hudPart').value;this.refresh();};
    for(const key of ['x','y','w','h']) $('hud-'+key).oninput=()=>this.patch({[key]:+$('hud-'+key).value});
    $('hud-visible').onchange=()=>this.patch({visible:$('hud-visible').checked});
    $('hud-opacity').oninput=()=>this.patch({opacity:+$('hud-opacity').value/100});
    $('hud-beam-scale').oninput=()=>this.patch({beamScale:+$('hud-beam-scale').value});
    $('hud-beam-opacity').oninput=()=>this.patch({beamOpacity:+$('hud-beam-opacity').value/100});
    $('hud-text').oninput=()=>this.patch({text:$('hud-text').value});
    $('hud-use-color').onchange=()=>this.patch({color:$('hud-use-color').checked?$('hud-color').value:''});
    $('hud-color').oninput=()=>{if($('hud-use-color').checked)this.patch({color:$('hud-color').value});};
    $('resetHudPart').onclick=()=>{this.layout[this.selected]=cleanLayout()[this.selected];this.changed();};
    $('resetHudAll').onclick=()=>{this.layout=cleanLayout();this.changed();};
    $('closeHudEdit').onclick=()=>this.setEditing(false);
    this.panel.querySelector('.edit-heading').onpointerdown=e=>{
      if(e.target.closest('button'))return;
      e.preventDefault();const bar=e.currentTarget,rect=this.panel.getBoundingClientRect(),px=e.clientX,py=e.clientY;
      bar.setPointerCapture(e.pointerId);
      const move=ev=>{this.panel.style.left=clamp(rect.left+ev.clientX-px,0,Math.max(0,innerWidth-rect.width))+'px';this.panel.style.top=clamp(rect.top+ev.clientY-py,0,Math.max(0,innerHeight-40))+'px';};
      const end=()=>{bar.removeEventListener('pointermove',move);bar.removeEventListener('pointerup',end);bar.removeEventListener('pointercancel',end);};
      bar.addEventListener('pointermove',move);bar.addEventListener('pointerup',end);bar.addEventListener('pointercancel',end);
    };
    for(const [id,b] of Object.entries(HUD_PARTS)) {
      const box=document.createElement('div');box.className='hud-edit-box';box.dataset.part=id;
      box.innerHTML=`<span>${b.name}</span><button class="hud-resize" aria-label="调整${b.name}大小"></button>`;
      this.overlay.appendChild(box);
      box.onpointerdown=e=>{
        if(e.button!==0)return;e.preventDefault();this.selected=id;this.refresh();
        const start={...this.layout[id]}, px=e.clientX,py=e.clientY;
        const resizing=e.target.classList.contains('hud-resize');
        box.setPointerCapture(e.pointerId);
        const move=ev=>{
          const rect=this.overlay.getBoundingClientRect();
          const dx=(ev.clientX-px)*1920/rect.width,dy=(ev.clientY-py)*1080/rect.height;
          this.patch(resizing?{w:start.w+dx,h:start.h+dy}:{x:start.x+dx,y:start.y+dy});
        };
        const end=()=>{box.removeEventListener('pointermove',move);box.removeEventListener('pointerup',end);box.removeEventListener('pointercancel',end);};
        box.addEventListener('pointermove',move);box.addEventListener('pointerup',end);box.addEventListener('pointercancel',end);
      };
    }
    new ResizeObserver(()=>this.resize()).observe(document.getElementById('stage'));
    this.refresh();
  }
  patch(values){this.layout=cleanLayout({...this.layout,[this.selected]:{...this.layout[this.selected],...values}});this.changed();}
  changed(){try{localStorage.setItem(KEY,JSON.stringify(this.layout));}catch{}this.refresh();this.onChange();}
  setEditing(enabled){this.editing=!!enabled;this.overlay.hidden=!enabled;this.panel.hidden=!enabled;document.getElementById('btnEditHud').setAttribute('aria-pressed',String(!!enabled));this.resize();}
  resize(){const r=document.getElementById('stage').getBoundingClientRect(),s=Math.min(r.width/1920,r.height/1080);Object.assign(this.overlay.style,{width:1920*s+'px',height:1080*s+'px',left:(r.width-1920*s)/2+'px',top:(r.height-1080*s)/2+'px'});}
  refresh(){
    const v=this.layout[this.selected],$=id=>document.getElementById(id);
    $('hudPart').value=this.selected;
    for(const key of ['x','y','w','h']){const el=$('hud-'+key);if(document.activeElement!==el)el.value=Math.round(v[key]);}
    $('hud-visible').checked=v.visible;
    $('hud-opacity').min=this.selected==='error'?'0':'10';
    $('hud-opacity').value=v.opacity*100;
    $('hud-opacity-label').textContent=this.selected==='error'?'判定条不透明度':'组件不透明度';
    $('hud-opacity-value').textContent=Math.round(v.opacity*100)+'%';
    $('hud-beam-control').hidden=this.selected!=='error';
    $('hud-beam-opacity-control').hidden=this.selected!=='error';
    if(this.selected==='error'){
      $('hud-beam-scale').value=v.beamScale;$('hud-beam-value').textContent=v.beamScale.toFixed(1)+'×';
      $('hud-beam-opacity').value=Math.round(v.beamOpacity*100);$('hud-beam-opacity-value').textContent=Math.round(v.beamOpacity*100)+'%';
    }
    for(const key of ['hud-opacity','hud-beam-scale','hud-beam-opacity']){
      const el=$(key),fill=(Number(el.value)-Number(el.min))/(Number(el.max)-Number(el.min))*100;
      el.style.setProperty('--range-fill',fill+'%');
    }
    if(document.activeElement!==$('hud-text'))$('hud-text').value=v.text;
    $('hud-use-color').checked=!!v.color;if(v.color)$('hud-color').value=v.color;
    for(const box of this.overlay.children){const l=this.layout[box.dataset.part];Object.assign(box.style,{left:l.x/19.2+'%',top:l.y/10.8+'%',width:l.w/19.2+'%',height:l.h/10.8+'%',opacity:l.visible?1:.4});box.classList.toggle('selected',box.dataset.part===this.selected);}
  }
  text(id,value){return this.layout[id].text||value;}
  color(id,value){return this.layout[id].color||value;}
  // The error meter applies opacity separately to its plate and hit markers.
  draw(ctx,id,paint){const b=HUD_PARTS[id],v=this.layout[id];if(!v.visible)return;ctx.save();if(id!=='error')ctx.globalAlpha*=v.opacity;ctx.translate(v.x,v.y);ctx.scale(v.w/b.w,v.h/b.h);ctx.translate(-b.x,-b.y);paint();ctx.restore();}
}
