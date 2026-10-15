const FILE_TYPES = {fOsr:/\.(osr|mr|mrv)$/i, fMap:/\.(osz|mcz|zip)$/i};
const STAGES = [['source','正在读取输入'],['skin','正在准备皮肤'],['chart','正在加载谱面'],['audio','正在准备音频与背景']];

function fileSize(bytes) {
  return bytes < 1024 * 1024 ? `${Math.max(1,Math.ceil(bytes/1024))} KB` : `${(bytes/1024/1024).toFixed(1)} MB`;
}

/** Entry UI only: files still flow through the existing replay/package loaders. */
export class SourceUI {
  constructor() {
    this.$ = id => document.getElementById(id);
    for (const id of Object.keys(FILE_TYPES)) {
      const input=this.$(id), drop=input.closest('.source-drop');
      input.addEventListener('change',()=>this.refreshFiles());
      drop.addEventListener('keydown',event=>{
        if (event.key==='Enter'||event.key===' ') {event.preventDefault();input.click();}
      });
      let dragDepth=0;
      drop.addEventListener('dragenter',event=>{event.preventDefault();dragDepth++;drop.classList.add('is-dragging');});
      drop.addEventListener('dragover',event=>{event.preventDefault();event.dataTransfer.dropEffect='copy';});
      drop.addEventListener('dragleave',()=>{if(--dragDepth<=0){dragDepth=0;drop.classList.remove('is-dragging');}});
      drop.addEventListener('drop',event=>{
        event.preventDefault();dragDepth=0;drop.classList.remove('is-dragging');
        const files=[...event.dataTransfer.files];
        if (files.length!==1 || !FILE_TYPES[id].test(files[0].name)) {
          this.fileError(id,id==='fOsr'?'请放入一个 .osr、.mr 或 .mrv 回放。':'请放入一个 .osz、.mcz 或 .zip 谱面包。');return;
        }
        const transfer=new DataTransfer();transfer.items.add(files[0]);input.files=transfer.files;
        input.dispatchEvent(new Event('change',{bubbles:true}));
      });
    }
    this.$('bidInput').addEventListener('input',()=>this.refreshFiles());
    this.$('btnClearMap').addEventListener('click',()=>{
      this.$('fMap').value='';this.$('fMap').dispatchEvent(new Event('change',{bubbles:true}));
    });
    this.$('btnClearOsr').addEventListener('click',()=>{this.$('fOsr').value='';this.refreshFiles();});
    this.refreshFiles();
  }
  fileError(id,message='') {
    const el=this.$(id==='fOsr'?'replayFileError':'mapFileError');
    el.textContent=message;el.hidden=!message;
    this.$(id).setAttribute('aria-invalid',String(!!message));
  }
  refreshFiles() {
    for(const [id,prefix,clear,placeholder,types] of [
      ['fOsr','replay','btnClearOsr','选择或拖入回放','.osr / .mr / .mrv'],
      ['fMap','map','btnClearMap','选择或拖入谱面包','.osz / .mcz / .zip']]) {
      const input=this.$(id),file=input.files[0],valid=!file||FILE_TYPES[id].test(file.name);
      const name=this.$(prefix+'FileName');name.textContent=file?.name||placeholder;name.title=file?.name||'';
      this.$(prefix+'FileMeta').textContent=file?`${fileSize(file.size)} · ${file.name.split('.').pop().toUpperCase()}`:types;
      input.closest('.source-drop').classList.toggle('has-file',!!file&&valid);
      this.$(clear).hidden=!file;
      this.fileError(id,valid?'':`文件格式不支持，请选择 ${types}。`);
    }
    const replay=this.$('fOsr').files[0],pack=this.$('fMap').files[0],bid=this.$('bidInput').value.trim();
    const needsPack=!!replay&&/\.(mr|mrv)$/i.test(replay.name)&&!pack;
    this.$('sourcePairHint').classList.toggle('needs-package',needsPack);
    this.$('sourcePairHint').textContent=needsPack?'这个 Malody 回放需要配套谱面包，请在右侧选择。':'Malody 回放需要配套谱面包，包内包含谱面和音频。';
    this.$('sourceSummary').textContent=replay?'回放预览':pack?'本地谱面自动播放':bid?'在线谱面自动播放':'等待选择谱面';
    const detail=[replay?.name,pack?.name,!pack&&bid?`谱面 #${bid}`:null].filter(Boolean).join(' + ');
    this.$('sourceSummaryDetail').textContent=detail||'在线谱面 ID 或本地文件';
  }
  setStage(id) {
    const index=STAGES.findIndex(stage=>stage[0]===id);if(index<0)return;
    this.$('loadingTitle').textContent=STAGES[index][1];
    this.$('sourceLoading').dataset.stage=id;
    this.$('sourceLoading').querySelectorAll('[data-step]').forEach((el,i)=>{
      el.classList.toggle('is-done',i<index);
      if(i===index)el.setAttribute('aria-current','step');else el.removeAttribute('aria-current');
    });
  }
}
