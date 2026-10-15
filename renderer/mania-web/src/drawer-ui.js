/** Exact critically damped spring; retargeting keeps current position and velocity. */
export function stepDrawerSpring(position,velocity,target,dt) {
  const omega=24,delta=position-target,c=velocity+omega*delta,decay=Math.exp(-omega*dt);
  return {position:target+(delta+c*dt)*decay,velocity:(velocity-omega*c*dt)*decay};
}

/** Presentation of the drawer; playback state remains in main.js. */
export class DrawerUI {
  constructor() {
    this.drawer=document.getElementById('drawer');
    this.toggle=document.getElementById('drawerToggle');
    this.reduced=matchMedia('(prefers-reduced-motion: reduce)');
    this.position=1;this.velocity=0;this.target=1;this.frame=0;this.open=false;
    this.ranges=[...this.drawer.querySelectorAll('input[type=range]')];
    for(const range of this.ranges)range.addEventListener('input',()=>this.updateRange(range));
    const file=document.getElementById('fOsk');
    file.addEventListener('change',()=>{
      const label=document.getElementById('drawerSkinFile');
      label.textContent=file.files[0]?.name||'也支持 .zip 皮肤包';label.title=file.files[0]?.name||'';
    });
    const syncEntry=()=>{this.toggle.hidden=!document.getElementById('sourceScene').hidden;};
    new MutationObserver(syncEntry).observe(document.getElementById('sourceScene'),{attributes:true,attributeFilter:['hidden']});
    syncEntry();this.ranges.forEach(range=>this.updateRange(range));
    this.reduced.addEventListener('change',()=>{if(this.reduced.matches)this.finish();});
  }
  updateRange(range) {
    const min=Number(range.min)||0,max=Number(range.max)||100;
    const fill=Math.max(0,Math.min(100,(Number(range.value)-min)/Math.max(1,max-min)*100));
    range.style.setProperty('--range-fill',fill+'%');
  }
  paint(){this.drawer.style.transform=`translateY(${this.position*100}%)`;}
  finish(){cancelAnimationFrame(this.frame);this.frame=0;this.position=this.target;this.velocity=0;this.paint();}
  setOpen(open) {
    this.open=open;this.target=open?0:1;this.drawer.inert=!open;
    this.drawer.setAttribute('aria-hidden',String(!open));
    this.toggle.setAttribute('aria-expanded',String(open));this.toggle.classList.toggle('is-open',open);
    if(open)this.ranges.forEach(range=>this.updateRange(range));
    if(this.reduced.matches){this.finish();return;}
    if(this.frame)return;
    let last=performance.now();
    const tick=now=>{
      const dt=Math.min(.064,Math.max(0,(now-last)/1000));last=now;
      Object.assign(this,stepDrawerSpring(this.position,this.velocity,this.target,dt));this.paint();
      if(Math.abs(this.position-this.target)<.0005&&Math.abs(this.velocity)<.01)this.finish();
      else this.frame=requestAnimationFrame(tick);
    };
    this.frame=requestAnimationFrame(tick);
  }
}
