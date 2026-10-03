# Handover — osu!mania WebGL renderer

State of the work, what is source-derived, what is still guessed, and how to verify.
Written so a fresh session (or a different agent) can pick this up without re-deriving
anything. Read this together with `CONTEXT.md` and `docs/SKIN_CONFORMANCE.md`.

---

## 1. Where things are

| | |
|---|---|
| Project | `D:\DeepSeek Harness\workspace\osu-mania-render` |
| Run | `python -m mania_render --web --port 8760` (from the project root) |
| Renderer | `mania-web/` — `index.html` + `src/{main,parsers,renderer,zip}.js`, served by `mania_render/webapp.py` |
| Source of truth (skins) | the four `.osk` files in `D:\osu-lazer\exports\` |
| Source of truth (rules) | osu!lazer checkout at `C:\Users\OwO\Desktop\osu-master` |
| Spec | `docs/wiki-osu-mania-skinning.md` (local copy of the osu! wiki page) |
| Verification harness | `D:\DeepSeek Harness\workspace\.browserkit\` |

### Verification harness (read this before changing anything)

The sandbox forbids Chrome's named-pipe IPC, so Playwright cannot launch the browser.
Instead: launch headless Chrome yourself with a CDP port, then attach over TCP.

```powershell
$exe = "$env:USERPROFILE\AppData\Local\ms-playwright\chromium-1234\chrome-win64\chrome.exe"
& $exe --headless=new --remote-debugging-port=9222 `
   --user-data-dir="D:\DeepSeek Harness\workspace\.browserkit\chrome-profile" `
   --use-gl=angle --use-angle=swiftshader --enable-unsafe-swiftshader `
   --no-first-run --no-default-browser-check --mute-audio `
   --autoplay-policy=no-user-gesture-required about:blank
```

Run it as a **background job** — if the launching shell is killed, Chrome dies with it.
Then, from `.browserkit\`:

| script | purpose |
|---|---|
| `node probe.mjs <url> <outdir> [--bid X] [--osr path] [--skin K] [--seek S] [--noplay] [--shots 3,6] [--viewport 1920x1080] [--shot-el "#stage"] [--clip x,y,w,h]` | general: load, seek, screenshot, dump `window.__mania.state` |
| `node ui_check.mjs` | 17 assertions over the drawer / spacebar / fullscreen |
| `pwsh -File regress.ps1` | 4 skins × replay/autoplay |
| `node tail_steps.mjs <bid> <skin> <ms> <outdir>` | frame-steps through an LN's tail arriving |
| `node hold_threshold.mjs <bid> "skinA\|skinB"` | computes the "body disappears" threshold per skin |
| `node sweep.mjs` | (slow under SwiftShader — avoid) |

`probe.mjs` disables the HTTP cache via CDP; without that the browser serves stale `/src/*.js`
and you will "fix" things that were never loaded.

Debug hooks exposed on the page by `main.js`: `window.__mania.state`, `.probeTex(name)`,
`.holdsAt(ms)`.

**Two traps that cost real time here:**
1. A **second server** can hold port 8760 (the previous agent's, serving a different
   checkout). Verify with `/src/main.js` content, not just HTTP 200.
2. `Select-Object -Last N` buffers pipeline output — a timed-out command shows *nothing*.
   Never use it on a long-running command you need to watch.

---

## 2. Conventions this project insists on

- **A skin is one system.** Never tune head / body / tail (or any component) individually;
  derive them all from the same source model. Per-element patches were explicitly rejected.
- **No invented constants.** Every position/size/order must trace to a file:line in the
  lazer checkout or to an explicit wiki statement. If it cannot, say so and ask — do not guess.
- **An empty sprite has no extent.** A fully transparent placeholder measures 0 — but it is
  still the sprite the skin asked for. Do *not* treat it as "missing" and fall back to another
  sprite (that mistake put a bogus extra note on every LN tail).
- **Verify with pixels, not impressions.** Screenshot, then measure the PNG.

---

## 3. What is implemented, and on what authority

| Area | State | Authority |
|---|---|---|
| skin.ini parsing (`parsers.js`) | multiple `[Mania]` blocks keyed by `Keys:`, duplicate discarded, `//` comments stripped, unparseable array entries read as 0 | `LegacyManiaSkinDecoder.cs` |
| coordinate spaces | skin.ini values kept in 480-space, scaled by `VIEW_H/480`; **sprite pixel dimensions** scaled by `VIEW_H/768` (`TEX_SCALE`) | `LegacyManiaSkinConfiguration.POSITION_SCALE_FACTOR`, `DrawableManiaRuleset` |
| scroll speed | `TimeRange = 11485 / ScrollSpeed × (768 − HitPosition·1.6) / (768 − 124.8)` | `DrawableManiaRuleset.updateTimeRange()` |
| column layout | `ColumnWidth` + `ColumnSpacing` margins (default 1 in 768-space); `ColumnStart`/`ColumnRight` deliberately ignored (lazer decodes but never uses them) | `ColumnFlow.updateColumnSize()` |
| note | wiki Origin Bottom; the sprite's bottom edge is its time position; gone the moment that edge touches the judgement line (replay-Missed notes keep falling) | wiki + `LegacyNotePiece` |
| LN body | skin's `NoteImage{n}L`, tiled at natural aspect unless `NoteBodyStyle: Stretch`; spans **tailCentre → headCentre** | `DrawableHoldNote.cs:252-253`, `LegacyBodyPiece` |
| LN head | bottom-aligned like a note; falls, then parks on the judgement line while held | `LegacyHoldNoteHeadPiece` |
| LN tail | skin's `NoteImage{n}T` (no substitution), flipped unless `NoteFlipWhenUpsideDownT: 0` | wiki + `LegacyHoldNoteTailPiece` |
| **LN layer order** | **body → head → tail** (tail topmost) | `DrawableHoldNote.load()` child order |
| hit bursts | centred on `ScorePosition × 2.25` (the anchor branch collapses — see `SKIN_CONFORMANCE.md`); **width = 75% of the lane, aspect preserved** (requested deviation from the source's natural size); 60 fps loop (wiki; lazer loads 20 fps); replay-only | source + wiki |
| black keying | pure black cleared **only** on note/LN sprites (Cho authors them on opaque black) | skin assets |
| playback | wall-clock driven so 播放 works without an audio track; `Space` toggles | — |
| 导出 | **canvas recording, not a render**: `captureStream(60)` + MediaRecorder runs at exactly 1× real time, so a 3:08 chart takes 3 minutes and nothing is delivered until it ends. Stops on the **chart clock** (`beatmap.duration`); `audio.onended` is only a backstop, because a failed audio fetch used to leave it running forever. Button shows `导出中… NN%`, a second click cancels (and discards the partial recording). Measured: 95.6 s chart with audio blocked → ended at 97.4 s and downloaded | — |
| UI | everything except the playfield lives in a hover-drawer summoned from the bottom edge; fullscreen button | — |
| static serving | every file out of `mania-web/` is sent with `Cache-Control: no-store` — with no cache headers at all the browser heuristic-cached `/src/main.js`, so a reload could keep running an old build and make fixes look like they never landed | — |

---

## Deploying on a small VPS (2 cores / 2 GB) with an API for a QQ bot

Measured on this machine; the numbers below are `tools/mem_probe.py`, `tools/mem_tree.ps1`,
`tools/skin_weight.py` and `.browserkit/chrome_mem.ps1`.

**The container problem is already solved in the client:** Chrome's `MediaRecorder`
supports `video/mp4;codecs=avc1.42E01E` (verified with `isTypeSupported`), so 导出 now
writes **MP4/H.264 directly** — no webm, no ffmpeg, no remux. `check_export2.mjs` confirms
a `.mp4` download.

**Memory is dominated by the skin, not by the renderer.** Whole-Chrome-tree RSS while the
page plays a chart:

| state | whole tree | growth |
| :- | -: | -: |
| idle headless Chrome (SwiftShader), about:blank | 470 MB | — |
| + page with Cho' (0.6 MB skin) | 955 MB | +485 MB |
| + page with Suisei (181 MB skin, 1578 textures) | **2450 MB** | +1980 MB |
| + page with a **slimmed** Suisei (67 files, 1.23 MB) | **958 MB** | +489 MB |

`tools/skin_weight.py`: Suisei is 181.3 MB of which the mania renderer references **0.1 MB
(0.1 %, 35 of 1798 files)**; owc 23.7 %, Cho' 9.5 %, boj 6.0 %. `tools/slim_skin.py` repacks
a `.osk` down to just those files with **pure zip I/O** (no image is decoded), so it is cheap
on 2 cores: Suisei 1798 files / 181.3 MB → 67 files / 1.23 MB (0.7 %), and the page still
loads it (81 textures instead of 1578).

Budget that fits 2 GB with headroom: OS ~250 MB + Python API ~50 MB + one headless Chrome
with a slim skin ~960 MB ≈ **1.3 GB**. Serialise renders (one page, killed after each job);
a second concurrent page is what breaks it. The Python renderer (`_run_job`) is *not* part
of this path — it decodes every PNG into RGBA (+1638 MB for Suisei) and fans the skin out to
2 workers.

Verified invariants (re-run `regress.ps1` + `ui_check.mjs` after any change):
4 skins × 2 modes load with 0 JS errors; UI 17/17; hit bursts present in replay and absent in
autoplay; owc 4K columns read white/blue/blue/white. Burst geometry additionally has a
numeric check — `node burst_geom.mjs <url> --skin "…" --osr <replay.osr> --freeze` reads
`__mania.burstRect()` and asserts width = 75% of the lane, aspect preserved, centre =
`ScorePosition × 2.25`, no lane overflow.

Known gap: there is **no default-skin fallback layer** — a skin shipping no `mania-hit*`
(e.g. boj 1-10K) draws no bursts, where lazer would fall through to its built-in default
skin. Assets are extractable from
`%LOCALAPPDATA%\osulazer\current\osu.Game.Resources.dll`.

---

## 4. Known-wrong or unsolved

### 4.1 LN mask cuts the tail at the head's centre  ← **current visible bug**

`main.js` computes `maskY = headY - hh/2` and clamps the tail with
`tailBot = Math.min(y2, maskY)`. For a short hold the tail's time position lies *below* the
head's centre, so the tail is sliced by a straight line exactly at the head's circle centre —
which reads as "a pink circle with its top half greyed out".

This `maskY` clamp was **derived by us, not from the source**. The real lazer mask is
`maskingContainer.Padding.Bottom = Head.Height/2` (downscroll) *inside* a `sizingContainer`
whose height only shrinks when `Time.Current >= StartTime && Head.IsHit && !DroppedHoldAfter`,
i.e. **only while holding**. Whether the padding alone clips a falling note is exactly the
open question — see `docs/SOURCE-HOLDNOTE.md` (§3) once it lands.

### 4.2 Not yet implemented (the "补齐" list)

| # | Item | Authority |
|---|---|---|
| 2 | `mania-stage-light` — `LightPosition`, `ColourLight`, Multiplicative blend, animation frames, drawn **under** notes, on key press | `LegacyKeyArea`, `LegacyStageBackground` |
| 3 | `NoteBodyStyle` branches — `Stretch` vs default (`FillMode` + `MathF.Max(1, 32800 / sprite.DrawHeight)`) | `LegacyBodyPiece.Update()` |
| 4 | combo burst (`comboburst-mania[-{n}]`) and `mania-warningarrow` | wiki |
| — | `Colour{n}` / `ColourLight{n}` / `ColourHold` / `ColourBarline` — parsed? applied? Currently **not applied at all** | `LegacyColumnBackground` |

### 4.3 Environment limitations

- **sayobot is unreachable** from this machine (direct *and* via the clash proxy on 7890).
  `osu.ppy.sh` works. Consequence: metadata lookups 502, so audio/background only load for
  beatmaps already in `cache/`. Mitigation in place: `BeatmapSetID` is read from the `.osu`
  itself, and a replay whose MD5 cannot be resolved can be paired with a typed 谱面 ID.
  To remove the dependency entirely, add nerinyan / catboy / beatconnect fallbacks.
- A signed-in osu! wiki page cannot be fetched; use the GitHub raw markdown
  (`ppy/osu-wiki/wiki/Skinning/osu!mania/en.md`), which is what `docs/wiki-osu-mania-skinning.md` is.

### 4.4 Unresolved question about Cho'

Cho's `skin.ini` body/tail are `Orbs\noteL` (a 128×32 full-width bar) and `Orbs\noteT`
(128×64, full-width with a black band). The skin also ships `Orbs\GLN` (128×284), a
**uniform capsule** with a light outline — and lazer's on-screen LN looks like that capsule.
`GLN` is referenced **nowhere** in the skin.ini. So one of these is true:

- lazer renders Cho's hold body with `DefaultBodyPiece` (which *is* a capsule:
  `CircularContainer` + `Radius = DrawWidth`), not the legacy bar; or
- something in the ancestor chain (`Orbs\GLN` ← ?) supplies it.

Resolving this needs `docs/SOURCE-SKIN-CHAIN.md` §1 (the gate) plus a decision from the user.
The user chose to **revert the capsule experiment and stay with the skin's own sprites**
for now, so the renderer draws the bar + dome and the visual differs from lazer at the tail.

---

## 5. Next actions, in order

1. Read `docs/SOURCE-SKIN-CHAIN.md` and `docs/SOURCE-HOLDNOTE.md` (being produced by
   subagents). Both are quote-backed audits, not summaries.
2. Fix §4.1 from `SOURCE-HOLDNOTE.md` §3 — replace the invented `maskY` clamp with the
   source's actual mask condition. **Rewrite the whole LN block**, do not patch it.
3. Work the §4.2 table in order, one item at a time, verifying each with the harness.
4. Re-run `regress.ps1` + `ui_check.mjs` and re-measure the burst band after every change.

---

## AstrBot 插件（astrbot_plugin_mania_render/）

`om <谱面ID>` 或 `om` + 回复一条带 `.osr` 的消息 → 调 `/api/render` → 轮询 → 下载 MP4 →
`Comp.Video.fromFileSystem` 发出去。默认 **1280x720 / 60fps / H.264 MP4**
（`MediaRecorder` 走的是浏览器那条路；服务端渲染由 ffmpeg 的 `-vf scale` 出 720p，
`scale_to=(1280,720)`，渲染几何仍是 1920x1080，所以不用重排轨道）。

API 侧为了插件补的东西：`/api/render` 现在接受 `bg_dim` / `width` / `height`，
任务状态带 `percent`，回显全部提交参数；并且**同时接受 multipart、
x-www-form-urlencoded 和 JSON** —— `aiohttp.FormData` 在没有文件字段时
`is_multipart` 是 False，纯文本请求会变成 urlencoded，只解析 multipart 会让每次调用
都报「需要谱面 ID」（这是用真机 AstrBot 跑出来的）。

自测（都不需要星号）：
- `tools/plugin_package_check.py` —— 按开发手册逐条检查包结构
- `tools/plugin_arg_selftest.py` —— 命令参数解析
- `tools/plugin_runtime_check.py --live` —— 用 AstrBot 自己的解释器加载插件、
  检查 `star_handlers_registry`，并真跑一次渲染
- `tools/plugin_registry_check.py` —— 确认 `om` / `om皮肤` / `om参数` 已注册