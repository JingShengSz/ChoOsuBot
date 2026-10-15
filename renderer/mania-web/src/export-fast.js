export async function selectVideoConfig(base,Encoder=globalThis.VideoEncoder){
  for(const codec of ['avc1.64002a','avc1.4d002a','avc1.42002a']){
    try{
      const candidate={...base,codec,hardwareAcceleration:'prefer-hardware',latencyMode:'quality'};
      const supported=await Encoder.isConfigSupported(candidate);
      if(supported.supported)return {...supported.config,...candidate};
    }catch{}
  }
  const fallback={...base,hardwareAcceleration:'no-preference'};
  const supported=await Encoder.isConfigSupported(fallback);
  if(!supported.supported)throw new Error('当前浏览器不支持所选尺寸的 H.264 编码');
  return {...supported.config,...fallback};
}

export function yieldToUI(){
  if(globalThis.scheduler?.yield)return globalThis.scheduler.yield();
  if(typeof MessageChannel!=='undefined')return new Promise(resolve=>{
    const channel=new MessageChannel();channel.port1.onmessage=()=>{channel.port1.close();channel.port2.close();resolve();};channel.port2.postMessage(null);
  });
  return new Promise(resolve=>setTimeout(resolve,0));
}

export function waitForEncoder(encoder){
  return new Promise(resolve=>{
    const done=()=>{encoder.removeEventListener('dequeue',done);clearTimeout(timer);resolve();};
    const timer=setTimeout(done,16);encoder.addEventListener('dequeue',done,{once:true});
  });
}

// Keep skin/HUD coordinates in 1920x1080 while drawing directly into output pixels.
export function resizeExportCanvas(canvas,hud,renderer,width,height){
  const saved=[canvas.width,canvas.height,hud.width,hud.height,renderer.logicalWidth,renderer.logicalHeight];
  renderer.logicalWidth=1920;renderer.logicalHeight=1080;
  canvas.width=width;canvas.height=height;hud.width=width;hud.height=height;
  return ()=>{
    [canvas.width,canvas.height,hud.width,hud.height,renderer.logicalWidth,renderer.logicalHeight]=saved;
    hud.getContext('2d').setTransform(1,0,0,1,0,0);
  };
}
