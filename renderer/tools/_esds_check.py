import struct, sys
PREFIX = {"stsd":8,"mp4a":28,"avc1":78,"wave":0,"esds":0}
CONT = {"moov","trak","mdia","minf","stbl","stsd","mp4a","wave","avc1"}
def walk(buf):
    i, out = 0, []
    while i+8 <= len(buf):
        size = struct.unpack(">I", buf[i:i+4])[0]
        typ = buf[i+4:i+8].decode("latin1","replace")
        hdr = 8
        if size == 1: size = struct.unpack(">Q", buf[i+8:i+16])[0]; hdr = 16
        if size < hdr or i+size > len(buf): break
        out.append((typ, size, buf[i+hdr:i+size])); i += size
    return out
def find_esds(data):
    for t,s,b in walk(data):
        if t == "esds": return b
        if t in CONT:
            r = find_esds(b[PREFIX.get(t,0):])
            if r is not None: return r
    return None
b = find_esds(open(sys.argv[1],"rb").read())
print(f"esds body {len(b)} B: {b.hex(' ')}")
i = 4
def rd(i, d):
    pad = "  " + "  "*d
    names={3:"ES_Descriptor",4:"DecoderConfigDescriptor",5:"DecoderSpecificInfo"}
    while i < len(b):
        tag = b[i]; i += 1
        ln = 0
        for _ in range(4):
            c = b[i]; i += 1
            ln = (ln<<7)|(c&0x7F)
            if not (c&0x80): break
        end = i+ln
        print(f"{pad}tag=0x{tag:02x} {names.get(tag,'?'):24s} len={ln:3d} {'OK' if end<=len(b) else '!! 越界'}")
        if tag == 3:
            print(f"{pad}   ES_ID={struct.unpack('>H',b[i:i+2])[0]} flags=0x{b[i+2]:02x}")
            rd(i+3, d+1)
        elif tag == 4:
            print(f"{pad}   oti=0x{b[i]:02x} streamType={b[i+1]>>2} max={struct.unpack('>I',b[i+5:i+9])[0]} avg={struct.unpack('>I',b[i+9:i+13])[0]}")
            rd(i+13, d+1)
        elif tag == 5:
            print(f"{pad}   ASC={b[i:end].hex(' ')}")
        if end > len(b): return
        i = end
rd(i, 0)
print()
print("期望结构: 03 -> (ES_ID,flags) -> 04 -> (oti,st,buf,max,avg) -> 05(ASC)")
