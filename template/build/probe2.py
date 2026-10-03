import numpy as np
from PIL import Image
src = np.asarray(Image.open(r"C:\Users\OwO\Downloads\恶魔娘原图手肘顶牌出框合成图.png").convert("RGB")).astype(np.int16)
al  = np.asarray(Image.open(r"D:\Cho Osu Bot\template\build\b_rank_alpha.png").convert("L"))
H, W = al.shape

print("=== top edge y=0, every 100px ===")
for x in range(0, W, 100):
    px = src[0, x]
    print("  x=%4d  R%3d G%3d B%3d   255-min=%3d  alpha=%3d" % (x,px[0],px[1],px[2],255-int(px.min()),al[0,x]))

print()
print("=== column x=900, y 0..24 ===")
for y in range(0, 25):
    px = src[y, 900]
    print("  y=%2d  R%3d G%3d B%3d   255-min=%3d  alpha=%3d" % (y,px[0],px[1],px[2],255-int(px.min()),al[y,900]))

print()
print("=== bottom edge y=H-1, every 200px ===")
for x in range(0, W, 200):
    px = src[H-1, x]
    print("  x=%4d  R%3d G%3d B%3d  255-min=%3d  alpha=%3d" % (x,px[0],px[1],px[2],255-int(px.min()),al[H-1,x]))

print()
print("=== left edge x=0, every 200px ===")
for y in range(0, H, 200):
    px = src[y, 0]
    print("  y=%4d  R%3d G%3d B%3d  255-min=%3d  alpha=%3d" % (y,px[0],px[1],px[2],255-int(px.min()),al[y,0]))
