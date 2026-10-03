// Minimal ISO-BMFF (MP4) muxer — one H.264 video track, optionally one AAC audio track.
//
// Why this exists: WebCodecs hands back encoded *samples*, not a container. MediaRecorder
// produces a container but samples the canvas against the wall clock, so it can never beat
// real time and cannot carry audio. Muxing here keeps the fast path and adds the audio.
//
// Layout written: ftyp, moov (mvhd + one trak per track), mdat. Non-fragmented: every
// sample is known before muxing, which is the case for a finished export. Video timebase
// is 1/1000 s; audio uses its sample rate. Written against ISO/IEC 14496-12 with the
// sample-entry byte layouts spelled out below, because getting those wrong yields a file
// that looks fine until a player refuses it.

const ascii = (s) => {
  const out = new Uint8Array(s.length);
  for (let i = 0; i < s.length; i++) out[i] = s.charCodeAt(i);
  return out;
};

const u8 = (...v) => new Uint8Array(v);
const u16 = (...v) => {
  const out = new Uint8Array(v.length * 2);
  const dv = new DataView(out.buffer);
  v.forEach((x, i) => dv.setUint16(i * 2, x));
  return out;
};
const u32 = (...v) => {
  const out = new Uint8Array(v.length * 4);
  const dv = new DataView(out.buffer);
  v.forEach((x, i) => dv.setUint32(i * 4, x >>> 0));
  return out;
};
/** Unity 16.16 / 2.30 fixed-point matrices, used identically by mvhd and tkhd. */
const IDENTITY_MATRIX = u32(0x00010000, 0, 0, 0, 0x00010000, 0, 0, 0, 0x40000000);
const ZEROES = (n) => new Uint8Array(n);

function concat(parts) {
  let total = 0;
  for (const p of parts) total += p.length;
  const out = new Uint8Array(total);
  let at = 0;
  for (const p of parts) { out.set(p, at); at += p.length; }
  return out;
}

function box(type, ...payload) {
  const body = concat(payload);
  const head = new Uint8Array(8);
  new DataView(head.buffer).setUint32(0, body.length + 8);
  head.set(ascii(type), 4);
  return concat([head, body]);
}

function fullBox(type, version, flags, ...payload) {
  return box(type, u8(version, (flags >> 16) & 0xff, (flags >> 8) & 0xff, flags & 0xff), ...payload);
}

/** MPEG-4 descriptor: tag + a 7-bit-chunk length with continuation bits. */
function esDescriptor(tag, payload) {
  const sizes = [];
  let rest = payload.length;
  do { sizes.unshift(rest & 0x7f); rest >>= 7; } while (rest > 0);
  for (let i = 0; i < sizes.length - 1; i++) sizes[i] |= 0x80;
  return concat([u8(tag), u8(...sizes), payload]);
}

/** A media track being filled in. Video samples are AVCC (length-prefixed) NAL units. */
export class Track {
  constructor(kind, timescale, id) {
    this.kind = kind;                       // 'video' | 'audio'
    this.timescale = timescale;
    this.id = id;
    this.samples = [];                      // { data, duration, key, offset }
    this.chunks = [];                       // { start, count, offset } — filled in build()
    this.description = null;                // avcC payload / AudioSpecificConfig
    this.width = 0;
    this.height = 0;
    this.channels = 2;
    this.sampleRate = timescale;
  }

  add(data, duration, key = false) {
    this.samples.push({ data, duration, key, offset: 0 });
  }

  get duration() {
    return this.samples.reduce((n, s) => n + s.duration, 0);
  }

  /**
   * Sample index ranges, one per chunk — the granularity `stco` indexes with.
   *
   * A single chunk per track is legal but useless AS AN INDEX. WMP's MP4 splitter builds its
   * time->byte map from `stco`, and with one entry per track it cannot locate any moment, so
   * it drops the track: the identical audio bytes played SILENT in WMP from a 1-chunk file
   * and played fine after `ffmpeg -c copy`, which rewrites stco to 22257 entries and
   * interleaves the two tracks. Chrome is lenient — it sums `stsz` from the chunk start
   * instead — which is exactly why the same file sought and played there and not in WMP.
   *
   * Video splits on keyframes (a seek needs a sync sample to restart from); audio splits on
   * a fixed frame count, since every AAC frame is independently decodable.
   */
  chunkRanges() {
    const out = [];
    const n = this.samples.length;
    if (!n) return out;
    if (this.kind === 'video') {
      let start = 0;
      for (let i = 1; i < n; i++) {
        if (this.samples[i].key) { out.push({ start, count: i - start, offset: 0 }); start = i; }
      }
      out.push({ start, count: n - start, offset: 0 });
    } else {
      const per = 43;                       // ~0.92 s of 1024-frame AAC at 48 kHz
      for (let i = 0; i < n; i += per) {
        out.push({ start: i, count: Math.min(per, n - i), offset: 0 });
      }
    }
    return out;
  }

  /** stts — run-length encode equal durations, as the box requires. */
  stts() {
    const runs = [];
    for (const s of this.samples) {
      const last = runs[runs.length - 1];
      if (last && last.delta === s.duration) last.count++;
      else runs.push({ count: 1, delta: s.duration });
    }
    return fullBox('stts', 0, 0,
      u32(runs.length),
      concat(runs.map((r) => u32(r.count, r.delta))));
  }

  stbl() {
    // stsc is run-length encoded: (first_chunk, samples_per_chunk, description_index), one
    // entry per RUN of chunks with an equal sample count.
    const runs = [];
    this.chunks.forEach((c, i) => {
      const last = runs[runs.length - 1];
      if (last && last.count === c.count) last.n++;
      else runs.push({ first: i + 1, count: c.count, n: 1 });
    });
    const parts = [
      this.kind === 'video' ? this.videoStsd() : this.audioStsd(),
      this.stts(),
      fullBox('stsc', 0, 0, u32(Math.max(1, runs.length)),
        concat((runs.length ? runs : [{ first: 1, count: this.samples.length, n: 1 }])
          .map((r) => u32(r.first, r.count, 1)))),
      fullBox('stsz', 0, 0, u32(0, this.samples.length),
        concat(this.samples.map((s) => u32(s.data.length)))),
      // One offset per chunk, and stsc must describe exactly those chunks. Listing an offset
      // per SAMPLE here makes stco claim N chunks while stsc claims 1, and ffmpeg reports
      // "wrong sample count".
      fullBox('stco', 0, 0, u32(Math.max(1, this.chunks.length)),
        concat((this.chunks.length ? this.chunks : [{ offset: 0 }]).map((c) => u32(c.offset)))),
    ];
    if (this.kind === 'video') {
      const keys = [];
      this.samples.forEach((s, i) => { if (s.key) keys.push(i + 1); });
      if (keys.length) {
        parts.push(fullBox('stss', 0, 0, u32(keys.length), concat(keys.map((k) => u32(k)))));
      }
    }
    return box('stbl', ...parts);
  }

  /**
   * VisualSampleEntry (ISO 14496-12 §12.1.3), 78 bytes before the codec box:
   *   6 reserved | 2 data_reference_index | 2 pre_defined | 2 reserved | 12 pre_defined
   *   2 width | 2 height | 4 horizresolution | 4 vertresolution | 4 reserved
   *   2 frame_count | 32 compressorname | 2 depth | 2 pre_defined(-1)
   */
  videoStsd() {
    const entry = box('avc1',
      ZEROES(6),
      u16(1),                       // data_reference_index
      u16(0, 0),                    // pre_defined, reserved
      u32(0, 0, 0),                 // pre_defined[3]
      u16(this.width, this.height),
      u32(0x00480000, 0x00480000),  // 72 dpi
      u32(0),
      u16(1),                       // frame_count
      ZEROES(32),                   // compressorname
      u16(0x0018),                  // depth
      u16(0xffff),                  // pre_defined = -1
      box('avcC', this.description));
    return fullBox('stsd', 0, 0, u32(1), entry);
  }

  /**
   * AudioSampleEntry (ISO 14496-12 §12.2.3), 28 bytes before `esds`:
   *   6 reserved | 2 data_reference_index | 8 reserved | 2 channelcount | 2 samplesize
   *   2 pre_defined | 2 reserved | 4 samplerate (16.16)
   */
  audioStsd() {
    const esds = fullBox('esds', 0, 0,
      esDescriptor(0x03, concat([
        // ES_ID is 16 bits and flags is 8 — THREE bytes total. This was `u16(0, 0)`, which
        // writes FOUR and left a stray 0x00 sitting between the flags and the
        // DecoderConfigDescriptor tag. That desynchronises the descriptor chain from there
        // on: a lenient parser (ffmpeg) still stumbled onto the AudioSpecificConfig and
        // decoded the track, while stricter players walked the chain, failed to find the
        // ASC, could not configure the AAC decoder, and played the file SILENTLY.
        u8(0, 0, 0),                                    // ES_ID = 0x0000, flags = 0x00
        esDescriptor(0x04, concat([
          u8(0x40, 0x15),                                 // AAC-LC, audio stream
          u8(0, 0, 0),                                    // bufferSizeDB
          u32(192000),                                    // maxBitrate
          u32(192000),                                    // avgBitrate
          esDescriptor(0x05, this.description),           // AudioSpecificConfig
        ])),
      ])));
    const entry = box('mp4a',
      ZEROES(6),
      u16(1),                       // data_reference_index
      u32(0, 0),                    // reserved[2]
      u16(this.channels, 16),
      u16(0, 0),                    // pre_defined, reserved
      u32(this.sampleRate << 16),
      esds);
    return fullBox('stsd', 0, 0, u32(1), entry);
  }

  trak() {
    // TrackHeaderBox (v0): 4+4 creation/modification, 4 track_id, 4 reserved, 4 duration,
    // 8 reserved, 2 layer, 2 alternate_group, 2 volume, 2 reserved, 36 matrix, 4+4 size.
    const tkhd = fullBox('tkhd', 0, 0x000007,
      u32(0, 0, this.id, 0, this.duration),
      u32(0, 0),
      u16(0, 0, this.kind === 'audio' ? 0x0100 : 0, 0),
      IDENTITY_MATRIX,
      u32(this.width << 16, this.height << 16));
    // MediaHeaderBox (v0): creation, modification, timescale, duration, language, quality.
    // 0x55C4 is the packed ISO-639 code for "und".
    const mdhd = fullBox('mdhd', 0, 0,
      u32(0, 0, this.timescale, this.duration),
      u16(0x55c4, 0));
    const hdlr = fullBox('hdlr', 0, 0,
      u32(0),
      ascii(this.kind === 'video' ? 'vide' : 'soun'),
      u32(0, 0, 0),
      ascii(this.kind === 'video' ? 'VideoHandler' : 'SoundHandler'),
      u8(0));
    const minf = box('minf',
      this.kind === 'video'
        ? fullBox('vmhd', 0, 1, u16(0, 0, 0, 0))
        : fullBox('smhd', 0, 0, u16(0, 0)),
      box('dinf', fullBox('dref', 0, 0, u32(1), fullBox('url ', 0, 1))),
      this.stbl());
    return box('trak', tkhd, box('mdia', mdhd, hdlr, minf));
  }
}

export class Mp4Muxer {
  constructor(tracks) {
    this.tracks = tracks.filter((t) => t && t.samples.length);
  }

  build() {
    const ftyp = box('ftyp', ascii('isom'), u32(0x200), ascii('isomiso2avc1mp41'), ascii('mp41'));
    // Chunk layout is decided BEFORE the first moov pass: it fixes the SHAPE of stsc/stco
    // (how many entries), and only the stco values differ between the two passes.
    for (const t of this.tracks) t.chunks = t.chunkRanges();

    // Interleave. Ordering every chunk by the decode time of its first sample makes video
    // and audio alternate through mdat instead of one whole track following the other, which
    // is what ffmpeg produces and what a strict demuxer expects to find.
    const order = [];
    this.tracks.forEach((t, ti) => {
      let dts = 0;
      for (const c of t.chunks) {
        order.push({ ti, c, dts });
        for (let i = c.start; i < c.start + c.count; i++) dts += t.samples[i].duration;
      }
    });
    order.sort((a, b) => (a.dts - b.dts) || (a.ti - b.ti));

    const probe = this.moov();
    let at = ftyp.length + probe.length + 8;
    for (const o of order) {
      const t = this.tracks[o.ti];
      o.c.offset = at;
      for (let i = o.c.start; i < o.c.start + o.c.count; i++) {
        t.samples[i].offset = at;
        at += t.samples[i].data.length;
      }
    }
    const moov = this.moov();
    // mdat body must follow the EXACT order the offsets were assigned in.
    const body = concat(order.flatMap((o) => {
      const t = this.tracks[o.ti];
      return t.samples.slice(o.c.start, o.c.start + o.c.count).map((s) => s.data);
    }));
    const head = new Uint8Array(8);
    new DataView(head.buffer).setUint32(0, body.length + 8);
    head.set(ascii('mdat'), 4);
    return new Blob([ftyp, moov, head, body], { type: 'video/mp4' });
  }

  moov() {
    const longest = Math.max(...this.tracks.map((t) => t.duration / t.timescale));
    // MovieHeaderBox (v0), 1000 ticks/s: creation, modification, timescale, duration,
    // rate 1.0, volume 1.0, 2 reserved, 8 reserved, matrix, 24 pre_defined, next_track_id.
    const mvhd = fullBox('mvhd', 0, 0,
      u32(0, 0, 1000, Math.round(longest * 1000)),
      u32(0x00010000),
      u16(0x0100, 0),
      u32(0, 0),
      IDENTITY_MATRIX,
      ZEROES(24),
      u32(this.tracks.length + 1));
    return box('moov', mvhd, ...this.tracks.map((t) => t.trak()));
  }
}
