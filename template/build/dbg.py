import numpy as np
from PIL import Image
import sys

SRC = r"C:\Users\OwO\Downloads\恶魔娘原图手肘顶牌出框合成图.png"
arr = np.asarray(Image.open(SRC).convert("RGB")).astype(np.int16)
H, W = arr.shape[:2]
TOL = 38
near_white = (255 - arr.min(axis=2)) <= TOL
print("H,W =", H, W, " dtype:", near_white.dtype)
print("near_white[0,0]   =", bool(near_white[0,0]))
print("near_white[0,900] =", bool(near_white[0,900]))
print("near_white[24,900]=", bool(near_white[24,900]))

bg = np.zeros((H, W), dtype=bool)
stack = []
nseed = 0
for x in range(W):
    for y in (0, H-1):
        if near_white[y,x] and not bg[y,x]:
            bg[y,x] = True; stack.append((y,x)); nseed += 1
for y in range(H):
    for x in (0, W-1):
        if near_white[y,x] and not bg[y,x]:
            bg[y,x] = True; stack.append((y,x)); nseed += 1
print("seeds =", nseed, " stack len =", len(stack))
print("bg[0,0] after seeding =", bool(bg[0,0]))

# iterative flood, 用一维索引避免元组开销
b = bg.reshape(-1)
nw = near_white.reshape(-1)
st = [y*W+x for (y,x) in stack]
while st:
    p = st.pop()
    y, x = divmod(p, W)
    if y > 0:
        q = p - W
        if nw[q] and not b[q]: b[q] = True; st.append(q)
    if y < H-1:
        q = p + W
        if nw[q] and not b[q]: b[q] = True; st.append(q)
    if x > 0:
        q = p - 1
        if nw[q] and not b[q]: b[q] = True; st.append(q)
    if x < W-1:
        q = p + 1
        if nw[q] and not b[q]: b[q] = True; st.append(q)

bg = b.reshape(H, W)
print("flooded = %.2f%%" % (100.0*bg.mean()))
for pt in [(0,0),(0,900),(24,900),(100,300),(60,1200),(400,1357)]:
    y,x = pt
    print("  bg[%d,%d] = %s   (pixel 255-min=%d)" % (y,x,bool(bg[y,x]), 255-int(arr[y,x].min())))
