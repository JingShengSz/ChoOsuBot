import numpy as np
from PIL import Image

SRC = r"C:\Users\OwO\Downloads\恶魔娘原图手肘顶牌出框合成图.png"
OUT = r"D:\Cho Osu Bot\template\build\b_rank_alpha.png"
src = np.asarray(Image.open(SRC).convert("RGB")).astype(np.int16)
A   = np.asarray(Image.open(OUT))[:, :, 3]
H, W = A.shape

# 真正的问题像素：不透明 且 接近白（用 alpha 判定）
leftover = (A > 128) & ((255 - src.min(axis=2)) <= 30)
print("opaque & near-white: %d px (%.3f%%)" % (leftover.sum(), 100.0*leftover.mean()))

# 连通块
visited = np.zeros((H,W), bool)
comps = []
ys, xs = np.nonzero(leftover)
for y0, x0 in zip(ys, xs):
    if visited[y0,x0]: continue
    st=[(y0,x0)]; visited[y0,x0]=True; n=0
    miny=maxy=y0; minx=maxx=x0
    while st:
        y,x = st.pop(); n+=1
        if y<miny: miny=y
        if y>maxy: maxy=y
        if x<minx: minx=x
        if x>maxx: maxx=x
        for dy,dx in ((1,0),(-1,0),(0,1),(0,-1)):
            ny,nx=y+dy,x+dx
            if 0<=ny<H and 0<=nx<W and leftover[ny,nx] and not visited[ny,nx]:
                visited[ny,nx]=True; st.append((ny,nx))
    comps.append((n,minx,miny,maxx,maxy))
comps.sort(reverse=True)
print("clusters:", len(comps))
for n,x0,y0,x1,y1 in comps[:6]:
    print("  size=%6d  bbox x%d..%d y%d..%d  (w%d h%d)" % (n,x0,x1,y0,y1,x1-x0+1,y1-y0+1))
