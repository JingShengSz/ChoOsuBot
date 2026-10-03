"""Drive this machine's Photoshop to turn the template into one rendered PNG.

Why COM and not something portable: the card IS a PSD. The layout, the fonts and
the effect stack live in that file, and the only thing that renders it faithfully
is Photoshop itself.

Two hard-won rules are baked into the design here (they are also in the project
README, under "Photoshop 脚本注意事项"):

  * **Nothing is ever translated.** Every bitmap handed to Photoshop is already
    composited onto a full 1920x1080 transparent canvas at its final position, so
    it is placed with ``duplicate(doc, PLACEATBEGINNING)`` and needs no move at
    all. ``ArtLayer.translate()`` on this build applies a *negative, scaled* delta
    and a "self-correcting" retry loop diverges to y = -114000.
  * **Text colour goes through ``SolidColor``**, never ``RGBColor``, and never
    through the ActionManager's ``setd``/``TxLr``, which reports success and
    changes nothing.

A copy of the template is opened, never the template itself, and the copy is
closed without saving. A crash mid-render therefore cannot damage the original.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

# Where the layer tree starts. Every layer name in layer_mapping.json is looked
# up from here by a recursive search, so groups may be nested freely.
ROOT_GROUP = "TEMPLATE_ROOT"

# Grades whose signboard art is missing fall back down this chain; the JSX picks
# the first name that actually exists in the document.
SIGNBOARD_FALLBACK = {
    # 用户定的规则：**不管有没有开 mod，S 系一律用 S 的立绘，SS 系一律用 SS 的**。
    # 所以 X 前缀（Hidden/开 mod 出的评级）不再走单独立绘：
    #   XH (= SS+HD) -> signboard_ss
    #   SH (= S+HD)  -> signboard_s
    # 缺的那几档先退回 B，等出图后再填。
    "XH": ["signboard_ss", "signboard_b"],
    "SS": ["signboard_ss", "signboard_b"],
    "SH": ["signboard_s",  "signboard_b"],
    "S":  ["signboard_s",  "signboard_b"],
    "A":  ["signboard_a",  "signboard_b"],
    "B":  ["signboard_b",  "signboard_a"],
    "C":  ["signboard_c",  "signboard_b"],
    "D":  ["signboard_d",  "signboard_b"],
    "F":  ["signboard_f",  "signboard_b"],
}


class PhotoshopError(RuntimeError):
    """Raised with a message safe to show a user (never contains credentials)."""


def _js_string(value: str) -> str:
    """A JS string literal that is pure ASCII.

    Non-ASCII is escaped to \\uXXXX. The script is handed to ExtendScript as a
    string, and escaping removes every question about how the JSX would be
    decoded on the way in — which matters because beatmap titles are routinely
    Japanese.
    """
    out = ['"']
    for ch in str(value):
        code = ord(ch)
        if ch == '"':
            out.append('\\"')
        elif ch == "\\":
            out.append("\\\\")
        elif ch in "\r\n":
            out.append("\\n")
        elif 32 <= code < 127:
            out.append(ch)
        elif code <= 0xFFFF:
            out.append("\\u%04x" % code)
        else:
            # Surrogate pair for anything above the BMP.
            code -= 0x10000
            out.append("\\u%04x\\u%04x" % (0xD800 + (code >> 10), 0xDC00 + (code & 0x3FF)))
    out.append('"')
    return "".join(out)


def _js_value(value) -> str:
    if isinstance(value, str):
        return _js_string(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(_js_value(v) for v in value) + "]"
    if isinstance(value, dict):
        return "{" + ",".join(f"{_js_string(k)}:{_js_value(v)}" for k, v in value.items()) + "}"
    raise TypeError(f"cannot embed {type(value).__name__} in a JSX script")


# ─────────────────────────────── the script ───────────────────────────────

_JS_TEMPLATE = """
(function () {
  var D = __DATA__;
  app.displayDialogs = DialogModes.NO;
  var out = { ok: false, log: [], textApplied: 0, textMissing: [], rasters: [], shown: [] };

  // ExtendScript is ES3: there is no JSON object, so the result is hand-serialised.
  function q(s) {
    s = String(s === undefined || s === null ? "" : s);
    var r = '"';
    for (var i = 0; i < s.length; i++) {
      var c = s.charAt(i);
      var code = s.charCodeAt(i);
      if (c === '"') { r += '\\\\"'; }
      else if (c === '\\\\') { r += '\\\\\\\\'; }
      else if (code < 32 || code > 126) {
        r += '\\\\u' + ('000' + code.toString(16)).slice(-4);
      } else { r += c; }
    }
    return r + '"';
  }
  function arr(a) {
    var parts = [];
    for (var i = 0; i < a.length; i++) parts.push(q(a[i]));
    return "[" + parts.join(",") + "]";
  }

  var doc = app.open(new File(D.psd));
  try {
    function find(set, name) {
      for (var i = 0; i < set.length; i++) {
        var l = set[i];
        if (l.name === name) return l;
        if (l.typename === "LayerSet") {
          var r = find(l.layers, name);
          if (r) return r;
        }
      }
      return null;
    }
    function layerNames(set) {
      var a = [];
      for (var i = 0; i < set.length; i++) a.push(set[i].name);
      return a;
    }
    function orderGroup(g, want) {
      // move() with INSIDE inserts at the TOP, so re-asserting a stack means
      // walking the wanted order backwards.
      for (var i = want.length - 1; i >= 0; i--) {
        var l = find(g.layers, want[i]);
        if (l) l.move(g, ElementPlacement.INSIDE);
      }
    }

    /* ---- 0. 清掉模板里默认可见、插件却不负责设置的图层 ----------------
       模板的 mod_2_mult（DT 的 x1.5）出厂就是可见的。插件只「设置需要的」，
       从不「隐藏多余的」，所以一张没开 mod 的成绩卡上也残留着一个 x1.5。

       同类的还有 rank_a..rank_xh 那 8 个评级字母 —— 评级现在画在立绘里，
       这些层模板里虽然是隐藏的，但这里一并兜底，免得哪次改模板又把它们放出来。

       只按名字兜底、不碰 _deco_ 开头的设计标签（那些本来就该显示）。 */
    var wanted = {};
    for (var w = 0; w < D.text.length; w++) wanted[D.text[w].name] = true;
    var stalePat = /^(mod_[0-9]+_mult|rank_(xh|ss|sh|s|a|b|c|d))$/;
    function hideStale(set) {
      for (var h = 0; h < set.length; h++) {
        var lx = set[h];
        if (lx.typename === "LayerSet") { hideStale(lx.layers); continue; }
        if (lx.kind !== LayerKind.TEXT) continue;
        if (stalePat.test(lx.name) && !wanted[lx.name] && lx.visible) {
          lx.visible = false;
          out.log.push("hid stale " + lx.name);
        }
      }
    }
    hideStale(doc.layers);

    /* ---- 1. text layers ---------------------------------------------- */
    for (var i = 0; i < D.text.length; i++) {
      var job = D.text[i];
      var l = find(doc.layers, job.name);
      if (!l || l.kind !== LayerKind.TEXT) { out.textMissing.push(job.name); continue; }
      if (job.font) {
        try { l.textItem.font = job.font; } catch (e) { /* keep the template's font */ }
      }
      l.textItem.contents = job.value;
      // Colour changes go through SolidColor. RGBColor throws 1200 on this build,
      // and the ActionManager's setd/TxLr reports success while changing nothing.
      if (job.accent) {
        try {
          var hex = job.accent.replace("#", "");
          var sc = new SolidColor();
          sc.rgb.red = parseInt(hex.substr(0, 2), 16);
          sc.rgb.green = parseInt(hex.substr(2, 2), 16);
          sc.rgb.blue = parseInt(hex.substr(4, 2), 16);
          l.textItem.color = sc;
        } catch (e2) { out.log.push("accent failed on " + job.name); }
      }
      out.textApplied++;
    }

    /* ---- 2. rasters --------------------------------------------------- */
    // Every bitmap is a full-canvas 1920x1080 RGBA PNG, so duplicating it in
    // lands it at (0,0) with no translation needed.
    for (var i = 0; i < D.rasters.length; i++) {
      var r = D.rasters[i];
      var old = find(doc.layers, r.layer);
      var parent = old ? old.parent : find(doc.layers, r.group || "TEMPLATE_ROOT");
      if (!parent) { out.log.push("no parent for " + r.layer); continue; }
      var sd = app.open(new File(r.path));
      var fresh = sd.layers[0].duplicate(doc, ElementPlacement.PLACEATBEGINNING);
      sd.close(SaveOptions.DONOTSAVECHANGES);
      app.activeDocument = doc;
      fresh.move(parent, ElementPlacement.INSIDE);
      fresh.name = r.layer;
      fresh.visible = true;
      if (old && old !== fresh) old.remove();
      if (r.blend) { try { fresh.blendMode = BlendMode.SCREEN; } catch (e) {} }
      out.rasters.push(r.layer);
    }

    /* ---- 3. group stacks that must not be disturbed ------------------- */
    var bgGroup = find(doc.layers, "bg");
    if (bgGroup) orderGroup(bgGroup, ["_deco_bg_gradient", "_deco_bg_overlay", "beatmap_bg"]);

    var boardGroup = find(doc.layers, "signboard");
    if (boardGroup && D.signboard && D.signboard.length) {
      // D.signboard is a preference chain: the first name that exists in the
      // document wins. Grades XH/SS/SH/C/D have no art of their own yet, so they
      // borrow the nearest one rather than showing nothing at all.
      var chosen = null;
      for (var c = 0; c < D.signboard.length && !chosen; c++) {
        if (find(boardGroup.layers, D.signboard[c])) chosen = D.signboard[c];
      }
      // NOTE: .layers, not the group itself. Passing the LayerSet made this
      // return an empty list (a LayerSet has no .length), the loop below never
      // ran, and every signboard kept whatever visibility the template shipped
      // with — the grade silently stopped driving the illustration.
      var names = layerNames(boardGroup.layers);
      out.log.push("signboard children=" + names.length + " chosen=" + chosen);
      for (var i = 0; i < names.length; i++) {
        var l2 = find(boardGroup.layers, names[i]);
        if (!l2) { out.log.push("unresolved " + names[i]); continue; }
        if (names[i].indexOf("signboard_") === 0) l2.visible = (names[i] === chosen);
        if (names[i] === "_deco_board_placeholder") l2.visible = false;
        if (names[i].indexOf("signboard_") === 0) {
          out.log.push(names[i] + (l2.visible ? " SHOWN" : " hidden"));
        }
      }
      var glow = find(doc.layers, "rank_glow");
      if (glow) {
        glow.visible = true;
        var kids = boardGroup.layers;
        if (kids.length > 1) glow.move(kids[kids.length - 1], ElementPlacement.PLACEAFTER);
      }
      out.shown.push(chosen || "(none)");
    }

    /* ---- 4. export ---------------------------------------------------- */
    var opts = new PNGSaveOptions();
    opts.compression = 6;
    opts.interlaced = false;
    doc.saveAs(new File(D.out), opts, true);
    out.ok = true;
  } catch (err) {
    out.error = String(err);
  }
  try { doc.close(SaveOptions.DONOTSAVECHANGES); } catch (e2) {}
  return '{"ok":' + (out.ok ? "true" : "false") +
         ',"error":' + q(out.error) +
         ',"textApplied":' + out.textApplied +
         ',"textMissing":' + arr(out.textMissing) +
         ',"rasters":' + arr(out.rasters) +
         ',"shown":' + arr(out.shown) +
         ',"log":' + arr(out.log) + '}';
})();
"""


def build_jsx(payload: dict) -> str:
    return _JS_TEMPLATE.replace("__DATA__", _js_value(payload))


# ─────────────────────────────── COM plumbing ───────────────────────────────


def _run_via_win32com(jsx: str, timeout_ms: int) -> str:
    import pythoncom  # noqa: PLC0415  (only needed on this path)
    import win32com.client  # noqa: PLC0415

    pythoncom.CoInitialize()
    try:
        app = win32com.client.Dispatch("Photoshop.Application")
        return str(app.DoJavaScript(jsx))
    finally:
        pythoncom.CoUninitialize()


def _run_via_powershell(jsx: str, timeout_ms: int) -> str:
    """Fallback path: same script, launched through PowerShell's COM support.

    The script is pure ASCII by construction (see _js_string), so writing it out
    and reading it back cannot mangle beatmap titles.
    """
    with tempfile.TemporaryDirectory(prefix="osucard_") as tmp:
        jsx_path = Path(tmp) / "run.jsx"
        jsx_path.write_text(jsx, encoding="ascii")
        ps = (
            "$ErrorActionPreference='Stop';"
            f"$jsx = Get-Content -Raw -Encoding UTF8 '{jsx_path}';"
            "$ps = New-Object -ComObject Photoshop.Application;"
            "$ps.DoJavaScript($jsx)"
        )
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            capture_output=True, text=True, timeout=max(30, timeout_ms // 1000),
        )
        if proc.returncode != 0:
            # stderr can carry an ExtendScript message; it never carries secrets.
            raise PhotoshopError(f"PowerShell 调用 Photoshop 失败: {proc.stderr.strip()[:400]}")
        return proc.stdout.strip()


def run_jsx(jsx: str, timeout_ms: int, prefer_com: bool = True) -> str:
    order = [_run_via_win32com, _run_via_powershell] if prefer_com else \
            [_run_via_powershell, _run_via_win32com]
    errors = []
    for fn in order:
        try:
            return fn(jsx, timeout_ms)
        except ImportError as exc:
            errors.append(f"{fn.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001 - try the other transport
            errors.append(f"{fn.__name__}: {type(exc).__name__}: {exc}")
    raise PhotoshopError("两条 Photoshop 通道都失败了: " + " | ".join(errors)[:500])


# ─────────────────────────────── public API ───────────────────────────────


class ScoreCardRenderer:
    """Renders one card. Stateless between calls; safe to reuse."""

    def __init__(self, template: Path, work_dir: Path,
                 timeout_seconds: int = 180, prefer_com: bool = True):
        self.template = Path(template)
        self.work_dir = Path(work_dir)
        self.timeout_ms = int(timeout_seconds * 1000)
        self.prefer_com = prefer_com
        self.work_dir.mkdir(parents=True, exist_ok=True)

    def signboard_chain(self, grade: str) -> list[str]:
        """Candidate signboard layers for a grade, best first."""
        return list(SIGNBOARD_FALLBACK.get(str(grade).upper(), ["signboard_b"]))

    def render(self, text_layers: list[dict], rasters: list[dict],
               signboard, out_png: Path) -> dict:
        """One render.

        text_layers : [{"name", "value", "font": str|None, "accent": str|None}]
        rasters     : [{"layer", "path", "group": str|None, "blend": bool}]
                      each path must be a 1920x1080 RGBA PNG already at its
                      final position.
        signboard   : a preference chain of signboard_* layer names, or None.
        """
        if not self.template.is_file():
            raise PhotoshopError(f"模板不存在: {self.template}")

        if isinstance(signboard, str):
            signboard = [signboard]

        out_png = Path(out_png)
        out_png.parent.mkdir(parents=True, exist_ok=True)

        # Work on a copy so an interrupted render cannot touch the template.
        scratch_psd = self.work_dir / "card_work.psd"
        shutil.copy2(self.template, scratch_psd)

        payload = {
            "psd": scratch_psd.as_posix(),
            "out": out_png.as_posix(),
            "text": text_layers,
            "rasters": rasters,
            "signboard": signboard,
        }
        raw = run_jsx(build_jsx(payload), self.timeout_ms, self.prefer_com)

        try:
            result = json.loads(raw)
        except (TypeError, ValueError):
            raise PhotoshopError(f"Photoshop 返回了非 JSON: {str(raw)[:200]}") from None

        try:
            scratch_psd.unlink(missing_ok=True)
        except OSError:
            pass

        if not result.get("ok"):
            raise PhotoshopError(f"Photoshop 脚本失败: {result.get('error', '未知错误')}")
        if not out_png.is_file() or out_png.stat().st_size < 1024:
            raise PhotoshopError("导出没有产生有效的 PNG")
        return result
