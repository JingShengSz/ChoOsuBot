import sys, json, time, urllib.request
sys.path.insert(0, r"D:\DeepSeek Harness\workspace\osu-mania-render")
from mania_render.cdp import CDP
raw = urllib.request.urlopen("http://127.0.0.1:9333/json/list", timeout=10).read()
tabs = json.loads(raw)
pages = [t for t in tabs if t.get("type") == "page"]
print("  当前标签页:")
for t in pages[:6]:
    print(f"    {t.get('title','')[:40]:42s} {t.get('url','')[:60]}")
c = CDP(host="127.0.0.1", port=9333, timeout=60).connect()
sess = c.attach_page("https://github.com/")
c.call("Runtime.enable", session=sess)
time.sleep(6)
info = c.evaluate("""(() => {
  const m = document.querySelector('meta[name="user-login"]');
  return {title: document.title, login: m ? m.getAttribute('content') : null,
          hasSignInLink: !!document.querySelector('a[href="/login"]'),
          url: location.href};
})()""", session=sess)
print()
print("  标题:", info.get("title"))
print("  登录名:", info.get("login"))
print("  页面有 Sign in 链接:", info.get("hasSignInLink"))
print()
print("  >>> GitHub 已登录，可以开始建仓库" if info.get("login") else "  >>> 尚未登录，请在 Edge 窗口里登录 GitHub")
c.close_last_target(); c.close()
