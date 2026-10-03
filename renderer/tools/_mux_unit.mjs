import { Track, Mp4Muxer } from "../mania-web/src/mp4.js";
import fs from "fs";
// 视频：5 个样本，第 0/3 是关键帧 -> 期望 2 个 chunk
const v = new Track('video', 60000, 1);
v.width = 640; v.height = 360;
v.description = new Uint8Array([1,100,0,40,0xff,0xe1,0,4,0x67,0x64,0,0x28,1,0,4,0x68,0xee,0x3c,0x80]);
const vp = [];
for (let i = 0; i < 5; i++) {
  const d = new Uint8Array(100 + i * 7);
  d.fill(0x10 + i);                        // 每个样本可识别的填充
  vp.push(d); v.add(d, 1000, i === 0 || i === 3);
}
// 音频：100 个样本，每 43 个一块 -> 期望 3 个 chunk
const a = new Track('audio', 48000, 2);
a.description = new Uint8Array([0x11, 0x90]);
const ap = [];
for (let i = 0; i < 100; i++) {
  const d = new Uint8Array(50 + (i % 5));
  d.fill(0xa0 + (i % 16));
  ap.push(d); a.add(d, 1024);
}
const blob = new Mp4Muxer([v, a]).build();
const buf = Buffer.from(await blob.arrayBuffer());
fs.writeFileSync("cache/_mux_unit.mp4", buf);
fs.writeFileSync("cache/_mux_expect.json", JSON.stringify({
  video: vp.map(d => ({ len: d.length, fill: d[0] })),
  audio: ap.map(d => ({ len: d.length, fill: d[0] })),
}));
console.log("写出 cache/_mux_unit.mp4", buf.length, "bytes");
