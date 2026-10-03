import numpy as np
from PIL import Image
src = np.asarray(Image.open(r"C:\Users\OwO\Downloads\恶魔娘原图手肘顶牌出框合成图.png").convert("RGB")).astype(np.int16)
al  = np.asarray(Image.open(r"D:\Cho Osu Bot\template\build\b_rank_alpha.png").convert("L"))
H, W = al.shape
pts = [(W-1,400),(W-1,100),(W-1,600),(1200,50),(900,60),(700,1000),(W-1,900),(W-1,1400),(300,60),(60,1200)]
print(" x     y   |  R   G   B  | 255-min | alpha")
for x,y in pts:
    px = src[y,x]
    print("%5d %5d | %3d %3d %3d |   %3d   |  %3d" % (x,y,px[0],px[1],px[2],255-int(px.min()),al[y,x]))
print()
# 右边缘整条：有多少是"浅灰"
col = src[:, W-1, :]
d = 255 - col.min(axis=1)
print("right edge column: pixels with 255-min <= 38 :", int((d<=38).sum()), "/", H)
print("                    alpha at those pixels >128:", int(((d<=38) & (al[:,W-1]>128)).sum()))
