// Minimal ZIP reader for .osk skin files (stored + deflate)
export async function readZip(buffer) {
  const u8 = new Uint8Array(buffer);
  const dv = new DataView(buffer);
  // find EOCD (signature 0x06054b50) from end
  let eocd = -1;
  for (let i = u8.length - 22; i >= 0; i--) {
    if (dv.getUint32(i, true) === 0x06054b50) { eocd = i; break; }
  }
  if (eocd < 0) throw new Error('not a zip');
  const nFiles = dv.getUint16(eocd + 10, true);
  const cdOff = dv.getUint32(eocd + 16, true);
  const files = {};
  let p = cdOff;
  for (let i = 0; i < nFiles; i++) {
    if (dv.getUint32(p, true) !== 0x02014b50) break;
    const method = dv.getUint16(p + 10, true);
    const compSize = dv.getUint32(p + 20, true);
    const uncompSize = dv.getUint32(p + 24, true);
    const nameLen = dv.getUint16(p + 28, true);
    const extraLen = dv.getUint16(p + 30, true);
    const commentLen = dv.getUint16(p + 32, true);
    const localOff = dv.getUint32(p + 42, true);
    const name = new TextDecoder().decode(u8.subarray(p + 46, p + 46 + nameLen));
    p += 46 + nameLen + extraLen + commentLen;
    if (name.endsWith('/')) continue;
    // local header
    const lp = localOff;
    if (dv.getUint32(lp, true) !== 0x04034b50) continue;
    const lNameLen = dv.getUint16(lp + 26, true);
    const lExtraLen = dv.getUint16(lp + 28, true);
    const dataStart = lp + 30 + lNameLen + lExtraLen;
    const raw = u8.subarray(dataStart, dataStart + compSize);
    files[name] = { method, raw, uncompSize };
  }
  return { files, async read(name) {
    const f = files[name] || files[name.replace(/\\/g, '/')] || files[name.replace(/\//g, '\\')];
    if (!f) return null;
    if (f.method === 0) return f.raw;
    if (f.method === 8) {
      const ds = new DecompressionStream('deflate-raw');
      const stream = new Blob([f.raw]).stream().pipeThrough(ds);
      return new Uint8Array(await new Response(stream).arrayBuffer());
    }
    return null;
  }, async readText(name) {
    const d = await this.read(name);
    return d ? new TextDecoder().decode(d) : null;
  }, async readBlob(name, mime) {
    const d = await this.read(name);
    return d ? new Blob([d], { type: mime || 'application/octet-stream' }) : null;
  }, names() { return Object.keys(files); }
  };
}
