// Immutable indexes: results do not depend on playback direction or frame order.
export function upperBound(rows,time,key='time') {
  let lo=0,hi=rows.length;
  while(lo<hi){const mid=(lo+hi)>>>1;if(rows[mid][key]<=time)lo=mid+1;else hi=mid;}
  return lo;
}
export function lowerBound(rows,time,key='time') {
  let lo=0,hi=rows.length;
  while(lo<hi){const mid=(lo+hi)>>>1;if(rows[mid][key]<time)lo=mid+1;else hi=mid;}
  return lo;
}
export function timeWindow(rows,start,end) {
  return rows.slice(lowerBound(rows,start),upperBound(rows,end));
}

export class NoteIndex {
  constructor(notes){
    this.notes=notes;this.blockSize=64;this.blockEnds=[];this.maxHold=0;
    notes.forEach((n,i)=>{
      const end=n.isHold?n.endTime:n.time;
      const block=Math.floor(i/this.blockSize);
      this.blockEnds[block]=Math.max(this.blockEnds[block]??-Infinity,end);
      this.maxHold=Math.max(this.maxHold,end-n.time);
    });
  }
  *visible(start,end){
    const from=lowerBound(this.notes,start-this.maxHold),to=upperBound(this.notes,end);
    for(let i=from;i<to;){
      const block=Math.floor(i/this.blockSize),limit=Math.min(to,(block+1)*this.blockSize);
      if(this.blockEnds[block]<start){i=limit;continue;}
      for(;i<limit;i++){
        const note=this.notes[i];
        if((note.isHold?note.endTime:note.time)>=start)yield note;
      }
    }
  }
}

export class ReplayIndex {
  constructor(beatmap,match,replay,keys){
    this.beatmap=beatmap;this.match=match;this.replay=replay;this.keys=keys;
    this.notes=new NoteIndex(beatmap.hitObjects);
    this.heads=new Map();
    for(const o of match?.objs||[]){const key=`${o.col}:${o.time}`;if(!this.heads.has(key))this.heads.set(key,o);}
    this.down=Array.from({length:keys},()=>[]);this.up=Array.from({length:keys},()=>[]);
    for(const p of replay?.presses||[])this.down[p.key%keys].push(p);
    for(const p of replay?.releases||[])this.up[p.key%keys].push(p);
    this.prefixCounts=[new Uint32Array(6)];
    const slots={perfect:0,great:1,good:2,ok:3,meh:4,miss:5};
    for(const j of match?.judgements||[]){const next=this.prefixCounts.at(-1).slice();next[slots[j.result]]++;this.prefixCounts.push(next);}
    this.offsets=[];let n=0,mean=0,m2=0;
    for(const o of match?.objs||[]){
      if(!o.matched)continue;
      const x=o.error/(replay?.rate||1),delta=x-mean;
      mean+=delta/++n;m2+=delta*(x-mean);this.offsets.push({time:o.time,n,m2});
    }
  }
  counts(time){
    const values=this.prefixCounts[upperBound(this.match?.judgements||[],time)];
    return Object.fromEntries(['max','g300','g200','g100','g50','miss'].map((key,i)=>[key,values[i]]));
  }
  combo(time){const rows=this.match?.comboTrail||[];return rows[upperBound(rows,time)-1]?.combo||0;}
  cps(time,rate=this.replay?.rate||1){const rows=this.replay?.presses||this.beatmap.hitObjects,span=1000*rate;return upperBound(rows,time)-upperBound(rows,time-span);}
  ur(time){const row=this.offsets[upperBound(this.offsets,time)-1];return row?.n>=2?(10*Math.sqrt(row.m2/row.n)).toFixed(1):'—';}
  lastKeys(time){
    return this.down.map((rows,i)=>({down:rows[upperBound(rows,time)-1]?.time,up:this.up[i][upperBound(this.up[i],time)-1]?.time}));
  }
}
