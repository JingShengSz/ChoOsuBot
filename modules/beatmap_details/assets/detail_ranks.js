/* Keep both regular and LN estimates when the analyser returns a dual result. */
(() => {
  const data = window.BEATMAP_DETAILS;
  if(data){
    const rate=Number(data.conditions.speedRate||1),mods=(data.conditions.mods||[]).join('+');
    document.querySelector('.over').textContent=`OSU!MANIA / BEATMAP DETAIL / ${mods||'RATE'} ${rate}×`;
  }
  if (!data || data.vibroDetection?.isVibroMap) return;
  const mixed = data.algorithms.Mixed;
  const ranks = String(mixed.rework.estDiff || '').split(/\s*\|\|\s*/).filter(Boolean);
  if (ranks.length < 2) return;
  const escape = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const container = document.getElementById('estimate-display');
  container.classList.add('dual-estimates');
  const cards = ranks.map(name => {
    const key = rankIconKey(name.replace(/^[<≤]\s*/, ''));
    const art = window.DAN_ICON_BOUNDS?.[key] ? key : 'question';
    const suffix = name.match(/\s+(mid\/high|mid\/low|high|low)$/i)?.[1].toLowerCase();
    const suffixKey = suffix?.includes('high') ? 'plus' : suffix?.includes('low') ? 'minus' : null;
    return `<div class="dual-rank"><div class="dual-rank-art">${iconSvg(art,'estimate-icon')}${suffixKey ? iconSvg(suffixKey,'estimate-suffix') : ''}</div><div><div class="dual-rank-kind">${/\bLN\b/.test(name) ? 'LN · 长条段位' : '常规段位'}</div><div class="dual-rank-name">${escape(name)}</div></div></div>`;
  }).join('');
  container.innerHTML = `<div class="estimate-eyebrow">MIXED → ${escape(mixed.actualEstimatorAlgorithm.toUpperCase())} · 推荐估算</div><div class="dual-rank-list">${cards}</div>`;
  document.getElementById('sunny-diff').textContent = String(data.algorithms.Sunny.rework.estDiff || '—').replace(/\s*\|\|\s*/g,' / ');
})();
