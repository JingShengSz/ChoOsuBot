import sys, time
sys.path.insert(0, r"D:\DeepSeek Harness\workspace\osu-mania-render")
from mania_render.cdp import CDP
BID = "5206393"
c = CDP(host="127.0.0.1", port=9222, timeout=120).connect()
sess = c.attach_page("http://127.0.0.1:8760/")
c.call("Runtime.enable", session=sess)
for _ in range(200):
    time.sleep(0.5)
    try:
        if c.evaluate("typeof window.__mania", session=sess) == "object": break
    except Exception: pass
print("page ready")
c.evaluate("""
window.__net = []; window.__errs = [];
const of = window.fetch;
window.fetch = async (...a) => {
  const t0 = performance.now();
  try { const r = await of(...a); window.__net.push([String(a[0]), r.status, Math.round(performance.now()-t0)]); return r; }
  catch (e) { window.__net.push([String(a[0]), 'THREW', Math.round(performance.now()-t0), String(e)]); throw e; }
};
const oe = console.error; console.error = (...a) => { window.__errs.push(a.map(String).join(' ')); oe(...a); };
window.addEventListener('unhandledrejection', e => window.__errs.push('unhandled: ' + e.reason));
""", session=sess)
t0 = time.time()
c.evaluate("""(() => { const i=document.getElementById('bidInput'); i.value=%s;
  i.dispatchEvent(new Event('input',{bubbles:true}));
  document.getElementById('btnLoad').click(); return 1; })()""" % repr(BID), session=sess)
prev, last_change = None, time.time()
while time.time() - t0 < 200:
    time.sleep(0.5)
    txt = c.evaluate("document.getElementById('info').textContent", session=sess)
    if txt != prev:
        print(f"  t={time.time()-t0:6.1f}s  info = {txt}")
        prev, last_change = txt, time.time()
    if txt and ('就绪' in txt or '失败' in txt or txt.startswith('错误')) and time.time()-last_change > 5:
        break
print(f"\n=== 最终 #info (t={time.time()-t0:.1f}s) ===")
print("  ", repr(c.evaluate("document.getElementById('info').textContent", session=sess)))
print("\n=== 页面请求 (url, status, ms) ===")
for row in (c.evaluate("window.__net", session=sess) or []): print("  ", row)
print("\n=== console 错误 ===")
for e in (c.evaluate("window.__errs", session=sess) or []): print("  ", str(e)[:220])
print("\n=== audio ===")
print(" ", c.evaluate("""(() => { const a=document.getElementById('audio');
 return {src:(a.src||'').slice(0,40), readyState:a.readyState, networkState:a.networkState,
         err:a.error?(a.error.code+'/'+a.error.message):null, dur:a.duration}; })()""", session=sess))
print("\n=== __mania.state ===")
print(" ", c.evaluate("JSON.stringify(window.__mania.state||null)", session=sess))
c.close_last_target(); c.close()
