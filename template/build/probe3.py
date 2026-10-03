import numpy as np
from PIL import Image

OUT = r"D:\Cho Osu Bot\template\build\b_rank_alpha.png"
im = Image.open(OUT)
print("mode:", im.mode, " size:", im.size)
a = np.asarray(im)
print("array shape:", a.shape)
A = a[:, :, 3]                       # 真正的 alpha 通道
print("alpha: transparent(0) = %.2f%%   opaque(255) = %.2f%%   partial = %.2f%%" % (
    100.0*(A == 0).mean(), 100.0*(A == 255).mean(),
    100.0*((A > 0) & (A < 255)).mean()))

for x, y in [(0,0),(900,24),(900,0),(1200,50),(300,60),(60,1200),(1357,400),(300,1000)]:
    print("  a[%4d,%4d] = %3d" % (y, x, A[y, x]))

# 边缘一圈的平均 alpha
edge = np.concatenate([A[0,:], A[-1,:], A[:,0], A[:,-1]])
print("border alpha: mean=%.1f  max=%d" % (edge.mean(), edge.max()))
