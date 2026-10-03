import struct, sys, glob, os
p = glob.glob("cache/dl_test/*.mp4")[0]
data = open(p, "rb").read()
print(f"文件 {os.path.basename(p)}  {len(data)/1048576:.1f} MB")

def walk(buf, base=0, depth=0, path=""):
    i = 0
    out = []
    while i + 8 <= len(buf):
        size = struct.unpack(">I", buf[i:i+4])[0]
        typ = buf[i+4:i+8].decode("latin1")
        if size == 1:
            size = struct.unpack(">Q", buf[i+8:i+16])[0]
        if size < 8:
            break
        out.append((typ, i, size, buf[i+8:i+size]))
        i += size
    return out

def find(buf, want):
    for typ, off, size, body in walk(buf):
        if typ == want:
            return body
    return None

top = walk(data)
print("顶层 box:", [t for t,_,_,_ in top])
moov = find(data, "moov")
print("moov 内:", [t for t,_,_,_ in walk(moov)])
mvhd = find(moov, "mvhd")
ver = mvhd[0]
if ver == 0:
    ts, dur = struct.unpack(">II", mvhd[12:20])
else:
    ts, dur = struct.unpack(">IQ", mvhd[20:32])
print(f"mvhd  timescale={ts} duration={dur}  -> {dur/ts:.3f}s")

for idx, (typ, off, size, body) in enumerate([b for b in walk(moov) if b[0] == "trak"]):
    mdia = find(body, "mdia")
    mdhd = find(mdia, "mdhd")
    hdlr = find(mdia, "hdlr")
    kind = hdlr[8:12].decode("latin1", "replace") if hdlr else "?"
    v = mdhd[0]
    if v == 0:
        ts, dur = struct.unpack(">II", mdhd[12:20])
    else:
        ts, dur = struct.unpack(">IQ", mdhd[20:32])
    stbl = find(mdia, "minf")
    stbl = find(stbl, "stbl") if stbl else None
    n = None
    if stbl:
        stsz = find(stbl, "stsz")
        if stsz:
            n = struct.unpack(">I", stsz[8:12])[0]
    print(f"trak[{idx}] kind={kind!r} timescale={ts} duration={dur} -> {dur/ts:.3f}s"
          + (f"  samples={n}" if n is not None else ""))
