// WebGL2 mania renderer — sprite-based note rendering
const VS = `#version 300 es
layout(location=0) in vec2 aPos;      // 0..1 quad
layout(location=1) in vec2 aUV;
uniform vec4 uRect;                    // x, y, w, h in pixels
uniform vec2 uResolution;
uniform vec4 uUV;                      // u0, v0, u1, v1 — sub-rect for tiled sprites
out vec2 vUV;
out vec2 vLocal;
void main() {
  vec2 px = uRect.xy + aPos * uRect.zw;
  vec2 ndc = (px / uResolution) * 2.0 - 1.0;
  ndc.y = -ndc.y;
  gl_Position = vec4(ndc, 0.0, 1.0);
  vUV = uUV.xy + aUV * (uUV.zw - uUV.xy);
  vLocal = aPos;
}`;

const FS = `#version 300 es
precision mediump float;
in vec2 vUV;
in vec2 vLocal;
uniform sampler2D uTex;
uniform float uAlpha;
uniform int uBlendMode;  // 0=normal, 1=additive
uniform highp vec4 uRect;  // x, y, w, h in pixels (rounded-rect SDF); shared with the
                           // vertex stage, so its precision must match there
uniform float uRadius;   // 0 = square corners
out vec4 frag;
void main() {
  vec4 c = texture(uTex, vUV);
  float mask = 1.0;
  if (uRadius > 0.0) {
    // rounded-rect signed distance field: capsule when radius == h/2
    vec2 halfSize = max(uRect.zw * 0.5 - vec2(uRadius), vec2(0.0));
    vec2 p = (vLocal - 0.5) * uRect.zw;
    float d = length(max(abs(p) - halfSize, 0.0)) - uRadius;
    mask = 1.0 - smoothstep(-1.0, 1.0, d);
  }
  // Modes 1 (additive) and 2 (multiplicative) are BOTH paired with a blendFunc that
  // expects a premultiplied source:
  //   additive       (SRC_ALPHA, ONE)                 -> dst + src.rgb*src.a
  //   multiplicative (DST_COLOR, ONE_MINUS_SRC_ALPHA) -> dst*(1 - src.a*(1 - src.rgb))
  // Emitting the unmultiplied c.rgb for mode 2 made the mania stage light compute
  // dst*(rgb + 1 - a) instead — i.e. it BRIGHTENED the column (white light, a = 0.55 ->
  // x1.45) where the skin's grey gradient is supposed to darken it (x0.78).
  if (uBlendMode != 0) {
    float a = c.a * uAlpha * mask;
    frag = vec4(c.rgb * a, a);
  } else {
    frag = vec4(c.rgb, c.a * uAlpha * mask);
  }
}`;

// Full-screen background pass. `aPos.y = 0` is the TOP of the screen, exactly as in VS,
// so the NDC y must be flipped here too — omitting that flip put the first texture row
// (image top, since UNPACK_FLIP_Y_WEBGL is never set) at the BOTTOM of the viewport, i.e.
// every beatmap background was drawn upside down.
// `uUV` is the sampled sub-rect: the background is cover-cropped, not stretched, so a
// square or 4:3 image keeps its proportions inside the 16:9 canvas.
const VS_BG = `#version 300 es
layout(location=0) in vec2 aPos;
uniform vec4 uUV;              // u0, v0, u1, v1
out vec2 vUV;
void main() {
  gl_Position = vec4(aPos.x * 2.0 - 1.0, 1.0 - aPos.y * 2.0, 0.0, 1.0);
  vUV = uUV.xy + aPos * (uUV.zw - uUV.xy);
}`;

const FS_BG = `#version 300 es
precision mediump float;
in vec2 vUV;
uniform sampler2D uTex;
uniform float uAlpha;
out vec4 frag;
void main() {
  frag = texture(uTex, vUV);
  frag.a *= uAlpha;
}`;

export class Renderer {
  constructor(canvas) {
    this.canvas = canvas;
    const gl = canvas.getContext('webgl2', { premultipliedAlpha: false, alpha: true, antialias: false });
    if (!gl) throw new Error('WebGL2 not supported');
    this.gl = gl;

    // quad geometry: interleaved pos(x,y) + uv(u,v) — 4 floats per vertex
    const quad = new Float32Array([
      0,0, 0,0,  1,0, 1,0,  0,1, 0,1,
      1,0, 1,0,  1,1, 1,1,  0,1, 0,1,
    ]);
    this.quadBuf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, this.quadBuf);
    gl.bufferData(gl.ARRAY_BUFFER, quad, gl.STATIC_DRAW);

    this.prog = this._build(VS, FS);
    this.progBg = this._build(VS_BG, FS_BG);
    this.whiteTex = this._makeSolid(255, 255, 255, 255);
    this.blackTex = this._makeSolid(0, 0, 0, 255);
    this.textureCache = new Map();
    this.maxTex = gl.getParameter(gl.MAX_TEXTURE_SIZE) || 4096;
  }

  /**
   * A skin may ship a sprite larger than MAX_TEXTURE_SIZE — owc's LN body is
   * 256x20018. `texImage2D` fails on those (INVALID_VALUE) and sampling the
   * incomplete texture returns opaque BLACK, which is why long-note bodies drew
   * as solid black bars. Downscale to a legal size first; the body is stretched
   * to the note length on screen anyway, so the extra rows were never visible.
   */
  _fitToMaxTexture(img) {
    const w = img.width, h = img.height;
    if (w <= this.maxTex && h <= this.maxTex) return img;
    const s = Math.min(this.maxTex / w, this.maxTex / h);
    const c = document.createElement('canvas');
    c.width = Math.max(1, Math.floor(w * s));
    c.height = Math.max(1, Math.floor(h * s));
    const cx = c.getContext('2d');
    cx.imageSmoothingEnabled = true;
    cx.drawImage(img, 0, 0, c.width, c.height);
    return c;
  }

  _build(vsSrc, fsSrc) {
    const gl = this.gl;
    const vs = gl.createShader(gl.VERTEX_SHADER);
    gl.shaderSource(vs, vsSrc); gl.compileShader(vs);
    if (!gl.getShaderParameter(vs, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(vs));
    const fs = gl.createShader(gl.FRAGMENT_SHADER);
    gl.shaderSource(fs, fsSrc); gl.compileShader(fs);
    if (!gl.getShaderParameter(fs, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(fs));
    const prog = gl.createProgram();
    gl.attachShader(prog, vs); gl.attachShader(prog, fs); gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(prog));
    return prog;
  }

  _makeWhite() {
    return this._makeSolid(255, 255, 255, 255);
  }

  _makeSolid(r, g, b, a) {
    const gl = this.gl;
    const tex = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, tex);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, 1, 1, 0, gl.RGBA, gl.UNSIGNED_BYTE, new Uint8Array([r, g, b, a]));
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    return tex;
  }

  /**
   * Uploads a sprite. `wrap` = 'repeat' tiles it (needed for mania hold bodies,
   * which lazer draws with WrapMode.Repeat unless `NoteBodyStyle: Stretch`).
   * Repeat and clamp need separate GL textures, so the cache key records the mode.
   */
  uploadTexture(key, img, wrap = 'clamp') {
    const cacheKey = wrap === 'repeat' ? key + '@repeat' : key;
    if (this.textureCache.has(cacheKey)) return this.textureCache.get(cacheKey);
    const gl = this.gl;
    const tex = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, tex);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, this._fitToMaxTexture(img));
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T,
      wrap === 'repeat' ? gl.REPEAT : gl.CLAMP_TO_EDGE);
    this.textureCache.set(cacheKey, tex);
    return tex;
  }

  /**
   * Drops every uploaded sprite. Texture slots are keyed by role (`n0`, `b1`, …),
   * so without this a newly loaded skin keeps drawing the PREVIOUS skin's sprites.
   */
  resetTextures() {
    const gl = this.gl;
    for (const tex of this.textureCache.values()) gl.deleteTexture(tex);
    this.textureCache.clear();
  }

  /**
   * Drop one cached texture so the next `uploadTexture` with the same key uploads afresh.
   * Texture slots are keyed by role, so reusing a key without this keeps the old bitmap —
   * which is how a second beatmap ended up drawing the first one's background.
   */
  dropTexture(key, wrap = 'clamp') {
    const cacheKey = wrap === 'repeat' ? key + '@repeat' : key;
    const tex = this.textureCache.get(cacheKey);
    if (!tex) return;
    this.gl.deleteTexture(tex);
    this.textureCache.delete(cacheKey);
  }

  clear() {
    const gl = this.gl;
    gl.viewport(0, 0, this.canvas.width, this.canvas.height);
    gl.clearColor(0, 0, 0, 1);
    gl.clear(gl.COLOR_BUFFER_BIT);
    gl.enable(gl.BLEND);
  }

  drawQuad(tex, x, y, w, h, alpha = 1, blendMode = 0, uv = null, radius = 0) {
    const gl = this.gl;
    gl.useProgram(this.prog);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.quadBuf);
    // pos at offset 0, uv at offset 8, stride 16 (4 floats per vertex)
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 16, 0);
    gl.enableVertexAttribArray(1);
    gl.vertexAttribPointer(1, 2, gl.FLOAT, false, 16, 8);

    gl.uniform4f(gl.getUniformLocation(this.prog, 'uRect'), x, y, w, h);
    gl.uniform2f(gl.getUniformLocation(this.prog, 'uResolution'), this.canvas.width, this.canvas.height);
    gl.uniform1f(gl.getUniformLocation(this.prog, 'uAlpha'), alpha);
    gl.uniform1i(gl.getUniformLocation(this.prog, 'uBlendMode'), blendMode);
    gl.uniform1f(gl.getUniformLocation(this.prog, 'uRadius'), radius);
    gl.uniform4f(gl.getUniformLocation(this.prog, 'uUV'),
      uv ? uv[0] : 0, uv ? uv[1] : 0, uv ? uv[2] : 1, uv ? uv[3] : 1);

    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, tex || this.whiteTex);
    gl.uniform1i(gl.getUniformLocation(this.prog, 'uTex'), 0);

    if (blendMode === 1) gl.blendFunc(gl.SRC_ALPHA, gl.ONE);           // additive
    else if (blendMode === 2) gl.blendFunc(gl.DST_COLOR, gl.ONE_MINUS_SRC_ALPHA); // multiplicative: transparent source leaves dst untouched
    else gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);

    gl.drawArrays(gl.TRIANGLES, 0, 6);
  }

  /** Solid shape, cached per colour. `radius = h/2` produces a capsule. */
  drawColorQuad(rgb, x, y, w, h, alpha = 1, blendMode = 0, radius = 0) {
    const key = 'solid:' + rgb.map(v => Math.round(v * 255)).join(',');
    let tex = this.textureCache.get(key);
    if (!tex) {
      tex = this._makeSolid(Math.round(rgb[0] * 255), Math.round(rgb[1] * 255), Math.round(rgb[2] * 255), 255);
      this.textureCache.set(key, tex);
    }
    this.drawQuad(tex, x, y, w, h, alpha, blendMode, null, radius);
  }

  drawDim(x, y, w, h, alpha = 0.8) {
    // black overlay for background dimming
    this.drawQuad(this.blackTex, x, y, w, h, alpha, 0);
  }

  /**
   * Full-screen background. `uv` is the source sub-rect to sample: pass the cover-crop
   * rect for the image so a non-16:9 background is cropped rather than squashed.
   */
  drawBackground(tex, alpha = 1, uv = null) {
    const gl = this.gl;
    gl.useProgram(this.progBg);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.quadBuf);
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 16, 0);
    gl.enableVertexAttribArray(1);
    gl.vertexAttribPointer(1, 2, gl.FLOAT, false, 16, 8);

    gl.uniform4f(gl.getUniformLocation(this.progBg, 'uUV'),
      uv ? uv[0] : 0, uv ? uv[1] : 0, uv ? uv[2] : 1, uv ? uv[3] : 1);
    gl.uniform1f(gl.getUniformLocation(this.progBg, 'uAlpha'), alpha);
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, tex);
    gl.uniform1i(gl.getUniformLocation(this.progBg, 'uTex'), 0);
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
    gl.drawArrays(gl.TRIANGLES, 0, 6);
  }

  /**
   * UV sub-rect that cover-fits `w x h` into `dstW x dstH`: scale up until both axes are
   * filled, then centre-crop the overflow. Mirrors `Renderer._background()` in the Python
   * renderer (`scale = max(dw/w, dh/h)`, then a centred crop).
   */
  static coverUV(w, h, dstW, dstH) {
    if (!w || !h) return [0, 0, 1, 1];
    const imgAspect = w / h, dstAspect = dstW / dstH;
    if (imgAspect > dstAspect) {
      const f = dstAspect / imgAspect;                 // crop left/right
      return [(1 - f) / 2, 0, 1 - (1 - f) / 2, 1];
    }
    const f = imgAspect / dstAspect;                   // crop top/bottom
    return [0, (1 - f) / 2, 1, 1 - (1 - f) / 2];
  }
}
