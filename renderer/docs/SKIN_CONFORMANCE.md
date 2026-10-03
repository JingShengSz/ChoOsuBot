# osu!mania skin conformance

How the WebGL renderer resolves a skin, and the exact source rules it follows.
Primary references:

- Spec: <https://osu.ppy.sh/wiki/en/Skinning/osu%21mania> (local copy: [`wiki-osu-mania-skinning.md`](wiki-osu-mania-skinning.md))
- Implementation: the osu!lazer checkout at `C:\Users\OwO\Desktop\osu-master`
  - `osu.Game/Skinning/LegacyManiaSkinDecoder.cs` — skin.ini grammar
  - `osu.Game/Skinning/LegacyManiaSkinConfiguration.cs` — defaults & scale factors
  - `osu.Game.Rulesets.Mania/Skinning/Legacy/*` — the drawables
  - `osu.Game.Rulesets.Mania/UI/DrawableManiaRuleset.cs` — scroll speed

## Coordinate spaces

skin.ini numbers live in osu!stable's **480-height** space. lazer converts them to its
768-height space with `POSITION_SCALE_FACTOR = 1.6`. This renderer keeps every parsed
number in **480-space** and applies `VIEW_H / 480` (= 2.25) once, in `buildGeometry`.

```
480-space * 2.25  ==  768-space * 1.40625  ==  screen px
```

**Sprite pixel dimensions are NOT positioning values.** lazer draws a legacy texture at
its native pixel size inside a 768-unit-tall playfield, so texture pixels map by
`TEX_SCALE = VIEW_H / 768` (= 1.40625) — a different factor. Using the 480-space factor on
them makes every sprite **1.6× too large**; that is why Cho's receptors used to be
oversized (360px instead of 225px for a 160px-tall key sprite).

| Quantity | Factor |
|---|---|
| `HitPosition`, `LightPosition`, `ComboPosition`, `ColumnWidth`, `ColumnSpacing`, `WidthForNoteHeightScale`, `LightingNWidth` | `VIEW_H / 480` |
| sprite width/height in pixels (`mania-key*`, `mania-stage-left/right/bottom`, lighting, hint) | `VIEW_H / 768` |
| note/LN sprite height | neither — `texH * noteHeight / texW`, a pure ratio times a screen length |

`HitPosition` and `LightPosition` are stored as the **distance from the bottom edge**
(lazer: `(480 - clamp(v, 240, 480))`).

| Quantity | Source rule |
|---|---|
| `HitPosition` | `DrawableManiaRuleset`: `hitPosition = (480 - clamp(v,240,480)) * 1.6` |
| scroll length | `lengthToHitPosition = 768 - hitPosition` |
| **TimeRange** | `(11485 / ScrollSpeed) * (lengthToHitPosition / (768 - DEFAULT_HIT_POSITION))`, `DEFAULT_HIT_POSITION = (480-402)*1.6` |
| `ColumnWidth` | `LegacyManiaSkinConfiguration.DEFAULT_COLUMN_SIZE = 30 * 1.6` when not set |
| `WidthForNoteHeightScale` | sprite height `= texH * noteHeight / texW`, where `noteHeight = WidthForNoteHeightScale ?? DrawWidth` |

For owc (`HitPosition: 412`, scroll 30): `TimeRange = 382.83 * 659.2/643.2 = 392.36 ms`.

## `[Mania]` blocks

A skin may declare **several** `[Mania]` sections, one per `Keys:` value — owc ships a 4K
and a 7K block; Suisei ships 4/5/6/7K; boj ships 1–10K. Each `Keys:` line starts a new
configuration and a duplicate `Keys:` is discarded entirely (stable/lazer keep the first).
The renderer must therefore select the block matching the beatmap's column count — reading
"the last block in the file" makes a 4K beatmap load the 7K block and produces the wrong
note images.

When the skin has no block for that key count, the nearest declared block is used
(CONTEXT.md Q32).

## Header/value parsing

- **`//` comments are stripped** from the whole line (lazer `LegacyDecoder.StripComments`).
  Skins do put prose after values — Cho' ships
  `ColumnWidth: 85,85,85,85  // 65 |越大越瘦？`.
- **An unparseable array entry reads as zero**, never `NaN` (lazer `parseArrayValue`,
  stable parity, ppy/osu#26464). A single `NaN` width poisons `startX` and every column,
  so nothing renders at all.

## Sprite resolution

`mania-note{1|2|S}` / `mania-key{1|2|S}` are chosen by
`LegacyManiaColumnElement.FallbackColumnIndex`: the **middle column of an odd key count is
the special `S` column**, otherwise the parity of the distance to the nearest edge picks
`1` / `2`. That reproduces the wiki's default key-layout table exactly (4K → 2,2,1 → i.e.
1,2,2,1).

| Element | skin.ini key | fallback chain |
|---|---|---|
| note | `NoteImage{n}` | `mania-note{1\|2\|S}` |
| key idol/pressed | `KeyImage{n}` / `KeyImage{n}D` | `mania-key{1\|2\|S}` / `…D` |
| hit burst | `Hit300g/300/200/100/50/0` | `mania-hit300g`, … (lazer `default_hit_result_skin_filenames`) |
| hit lighting | `LightingN` / `LightingL` | `lightingN` / `lightingL` |
| judgement line | `StageHint` | `mania-stage-hint` |
| stage sides/bottom | `StageLeft`/`StageRight`/`StageBottom` | `mania-stage-left`/`-right`/`-bottom` |

Texture lookups normalise `\` → `/` and are case-insensitive, then fall back from the full
path to the bare stem and finally `stem0` / `stem1` (Cho' uses `Orbs\BLUE`, which resolves
to `Orbs/BLUE1.png`).

### Two resolution rules that are easy to miss
**Existence decides, exactly like lazer's `GetAnimation`.** owc's `mania-note{1,2}T.png` are
**1×1 fully transparent**; the cap is deliberately absent, and treating them as "missing" so
the head-as-tail fallback fires puts a bogus extra note at every tail. The `T → H → NoteImage`
chain only advances when the skin provides **no** tail sprite at all.

**Black is keyed out of note sprites.** Cho' authors `Orbs/noteL.png` and `Orbs/noteT.png`
on an **opaque black** background (~50% of their pixels are `(0,0,0,255)`); drawn as-is
that shows up as black slabs around the long note. `keyOutBlack()` clears the alpha of
pixels darker than 12/255. It is applied **only** to note / LN sprites — key images
(`Orbs/4KR.png`) and the stage side panels (`mania-stage-left.png`) are legitimately
opaque black in many skins and must not be touched.

## Column layout

`ColumnFlow.updateColumnSize()` gives every column
`Margin = LeftColumnSpacing / RightColumnSpacing ?? Stage.COLUMN_SPACING (=1, 768-space)`
and `Width = ColumnWidth[col]`. The stage width is therefore
`Σ(width) + Σ(spacing)`, and it is centred. `ColumnStart` / `ColumnRight` are decoded by
lazer but **never used** for rendering (only round-tripped by the encoder), so they are
ignored here too.

## Hold notes are one composed system, not four separate elements

Everything about an LN's geometry comes from a single model —
`osu.Game.Rulesets.Mania/Objects/Drawables/DrawableHoldNote.cs`. Do not tune the head,
tail and body individually; derive them all from this:

| Piece | Placement | Source rule |
|---|---|---|
| **head** | note sprite at the head's time position, **outside** the mask, drawn last | stays visible while held |
| **body** | spans **tailCentre → headCentre** | *"Position and resize the body to lie half-way under the head and the tail notes. The rationale for this is account for heads/tails with corner radius."* |
| **tail** | sprite at the tail's time position, **inside** the mask | clipped together with the body |
| **mask** | edge at **headCentre**, shrinking as the hold progresses | *"the contained masking container will mask the body and ticks"* |

```
hh = head sprite height, th = tail sprite height
headY  = now < t1 ? y(t1) : hitY      // falls, then parks on the judgement line
maskY  = headY - hh / 2               // the mask edge = head centre
body   = [ y(t2) - th/2 , maskY ]     // half-way under the tail … half-way under the head
tail   = [ y(t2) - th , min(y(t2), maskY) ]
head   = [ headY - hh , headY ]
```

The mask is what makes the LN collapse cleanly: as the tail descends it is eaten at the
head's centre, so **nothing can poke out past the head** and no half-circle is left behind
once the note has been consumed. The `hh/2` and `th/2` insets are the source's own
corner-radius allowance — they are not tunables, and head/tail sprites with transparent
margins (Cho's circle head, owc's solid bar head) both fall out of the same rule.

The body texture is then drawn into `[bodyTop, bodyBot]` with `WrapMode.Repeat` unless
`NoteBodyStyle: Stretch`, anchored at the body's top — which is what makes owc's 18
transparent top rows show up as its intended small gap at the tail.

| Element | Rule |
|---|---|
| keys | wiki Origin **Bottom**; lazer `LegacyKeyArea` anchors the container BottomCentre, so the sprite's bottom edge sits at the **bottom of the column**, stretched to the column width |
| note | wiki Origin **Bottom** (the sprite's bottom edge sits at its time position). The note is **gone the moment that edge touches the judgement line** — it is never clamped or allowed to linger on the line |
| judgement line | `LegacyHitTarget`: hint sprite **always** drawn, stretched to the full stage width with `Scale.y = 0.9 * 1.6025`; the 1px bar on top is gated by `JudgementLine` |
| column background | **There is no lane background image.** `LegacyManiaSkinConfigurationLookups` has no such entry and the mania wiki page lists no `mania-column*` sprite — the lane is a plain solid `Box` (`LegacyStageBackground.ColumnBackground`) coloured `Colour{n}` (**1-based**; `ColumnBackgroundColour` = `getCustomColour(existing, $"Colour{columnIndex + 1}")`) through `LegacyColourCompatibility.ApplyWithDoubledAlpha`, which puts the colour's alpha on the drawable and forces a **zero** alpha to opaque. Default `Color4.Black` = fully opaque. Measured per skin: Cho'/Suisei have no `Colour{n}` → opaque black (lane level `0.00`); boj `Colour1..n: 0,0,0,230` → 90 %; **owc 4K `Colour1..4: 0,0,0,196` → 77 %**, verified as `0.285 ×` the background beside the stage. `COLUMN_BACKGROUND_OVERRIDE` (null = follow the skin) is a knob, not a source value |
| column divider | `ColumnLineWidth` has **`keys + 1`** entries read left to right: `[0]` = lane 0's left edge, `[1..keys-1]` = the LEFT edge of each following lane, `[keys]` = the last lane's right edge. So 4K = 5 boundaries (2 outer + 3 inner) and Suisei's `0,5,5,5,0` means "no outer border, three 5-wide inner lines". **0 = the line is not drawn** (`hasLeftLine = leftLineWidth > 0`). Width is scaled by `Scale.x = 0.74`, lines sit inside a `HitTargetInsetContainer` so they stop at the **judgement line**, and the colour is `ColourColumnLine` (through `ApplyWithDoubledAlpha`: a zero alpha becomes opaque). Decoded with `applyScaleFactor: false`, i.e. a raw **768-space** value; ctor default `Fill(2)`. We draw each boundary **once** — lazer builds them per column (`ColumnLineWidth[i]` = left, `[i+1]` = right), which would draw every shared boundary twice and double its alpha |
| inter-column gap | `ColumnSpacing` (decoded **×1.6**, so 480-space) has `keys - 1` entries; `LeftColumnSpacing(i) = ColumnSpacing[i-1] / 2` and `RightColumnSpacing(i) = ColumnSpacing[i] / 2`, with margins 0 at the stage's outer edges — so **one entry = the full gap** between two lanes. `Stage.COLUMN_SPACING = 1` is only the fallback when there is no legacy `[Mania]` config at all (`?.Value ?? …` never triggers for a decoded skin.ini: a `Bindable<float>` holding 0 is not null). The array defaults to all zeros, so **a skin without `ColumnSpacing` gets contiguous lanes**. Suisei `1,1,1` → 2.25 px gaps at 1080p |
| `Colour*` keys | `LegacyManiaSkinDecoder`: any key starting with `Colour` **inside `[Mania]`** is a custom colour of that mania block — `ColourColumnLine`, `Colour{n}` (1-based lane background), `ColourLight{n}`. They are **not** read from the global `[Colours]` section. Parsed into `block.colours`; only `ColourColumnLine` is applied so far |
| stage light | `mania-stage-light`, Origin Bottom / `RelativeSizeAxes.X` (stretched to the column width), bottom edge `LightPosition` above the column bottom, drawn **under** the notes. **Blend is Normal, not Multiplicative** — the wiki says Multiplicative but `LegacyColumnBackground` sets no `Blending` while every genuinely additive mania element says so explicitly; a multiply with a white sprite is a no-op anyway. `OnPressed` = instant full alpha/size, `OnReleased` = linear 250 ms `FadeTo(0)` **and** `ScaleTo((1,0))` (squashes down onto its bottom edge) |
| hit lighting | `lightingN` (single/tail) / `lightingL` (hold), **Additive**, Origin Centre, at the judgement-line × lane-centre crossing; frame length `max(1000/60, 170 / frameCount)` |
| hit bursts | `mania-hit*`, Origin Centre, **60 FPS loop** (wiki; lazer loads it at 20 FPS), Normal blend, centred on `ScorePosition * 2.25`, **75% of lane width** (requested deviation) |
| stage bottom | `mania-stage-bottom`, drawn **over** the notes, **not** stretched to the stage width (0.625× of it) |

Notes and the LN head are both **bottom-aligned at the judgement line**, which is what keeps
"where the note disappears" and "where a held head sits" the same pixel.

### Why the LN body must tile, not stretch

owc's `mania-note1L.png` is **256×20018**, and its **top 18 rows are fully transparent**
(rows 18..20017 are solid). Stretching that texture over a ~200px body squeezes the
transparent band to ~0.09% of the height — invisible — so the body runs flush into the tail
cap. Tiling it at natural aspect puts those 18 rows at their real size,
`18 × colWidth / texW` ≈ **9px at 1080p**, which is the small gap between body and tail cap
the skin is designed around; likewise a short tile (Cho's 128×32 `Orbs/noteL.png`) repeats
along the hold as intended. `drawQuad` takes a UV sub-rect and `uploadTexture` a `repeat`
wrap mode to make this possible.

`lightingN` / `lightingL` / `mania-stage-bottom` are drawn strictly from skin pixels — an
empty or transparent file means no flash, never a synthesised fallback (CONTEXT.md
"Hit Lighting").

## Hit bursts vs autoplay

Per the requested behaviour, hit bursts (`mania-hit*`) and hit lighting are drawn **only
when a Replay is loaded**. Autoplay (FC Sim) renders notes and HUD but no hit imagery.

## Caching rules

Two caches are keyed by *role*, not by skin, and must be dropped whenever a skin changes
or they keep drawing the previous skin's sprites:

- `Renderer.textureCache` — WebGL texture slots (`n0`, `b1`, `k2`, …) → `Renderer.resetTextures()`
- `_hitFrameCache` / `_flipCache` in `main.js` → `invalidateSkinCaches()`

Skin loads also carry a **generation token** (`skinLoadToken`): a 180 MB `.osk` takes
seconds, and without the token the initial auto-load can land *after* the user picks
another skin and silently overwrite it, leaving the dropdown showing one skin while the
renderer draws another.

## Texture size limit

`MAX_TEXTURE_SIZE` on this machine is **8192**, and owc ships `mania-note1L.png` at
**256×20018**. `texImage2D` rejects that with `INVALID_VALUE`; because the upload is never
checked, sampling the incomplete texture returns opaque **black** — the long-note bodies
drew as solid black bars. `Renderer._fitToMaxTexture` downscales any oversized sprite into
a canvas at a legal size before upload. The body is stretched to the note length on screen
anyway, so the discarded rows were never visible.

## LN body colour

The body is drawn at **full opacity** from `NoteImage{n}L` (lazer's `LegacyBodyPiece`
applies no alpha), so owc's 4K bodies read exactly as the sprite files do:

| column | sprite | pixel |
|---|---|---|
| 0, 3 | `mania-note1L.png` | `(189,189,189)` |
| 1, 2 | `mania-note2L.png` | `(77,105,161)` |

i.e. the same white / blue / blue / white pattern as the notes.

## Loading a beatmap without a metadata API

The `.osu` file carries its own ids in `[Metadata]` — `BeatmapID` and `BeatmapSetID` — and
its background name in `[Events]`. `resolveSid()` uses the metadata API first and falls
back to the value inside the `.osu`. Without that fallback an unreachable sayobot means
`sid` is empty, the audio and background are never even *requested*, and 播放 has nothing
to play.

## Playback clock

Playback is driven by `performance.now()`, not by `<audio>` events. When a real track is
loaded the audio element stays the master clock (so picture and music cannot drift apart);
otherwise the wall clock drives the frame, and 播放 still animates the notes and HUD.
`Space` toggles playback, except while a form control has focus.

## UI shell

The playfield is the whole page. **Every control lives in the bottom drawer** — nothing
outside `#stage` except the drawer itself. `#drawerBar` no longer exists; the drawer is
hidden (`translateY(100%)`) and `#hotzone` + a `mousemove` listener pull it out when the
pointer comes within 18px of the bottom edge, retiring it again on the way out. It stays
open while a text field inside has focus (so typing is not interrupted) but **not** for
buttons or file/range inputs — otherwise clicking 加载 would pin it open forever.
`⛶ 全屏` fullscreens `document.documentElement` rather than `#stage`, so the drawer is
still reachable in fullscreen.

**`hh` / `th` are extents, not sprite boxes.** lazer's geometry is expressed in
`Head.Height` / `Tail.Height`, which are real extents of real sprites. owc ships
`mania-note{1,2}T.png` as a **1x1 fully transparent placeholder**: reporting its box height
gives a fictitious 90px that drags the body up over the tail and leaves the hold unfilled.
A sprite with no visible pixels therefore measures **0** (`isBlankSprite`). It is still the
sprite the skin asked for -- no substitution -- it just has no extent. This distinction
matters: treating a blank sprite as "missing" and falling back to the head (an earlier
mistake here) puts a bogus extra note at every tail.

## Hold body shape: DefaultBodyPiece capsule

The body is drawn as a **uniform capsule**, not the skin's tiled bar —
`DefaultBodyPiece` is a `CircularContainer` masked with a radius equal to its width, i.e.
the standard capsule construction, spanning tailCentre -> headCentre. A tiled bar leaves
its square corners visible beside a narrower tail cap (Cho's `noteT` dome is ~110px wide
against a 128px bar), which reads as "a piece of body sticking out beside the tail"; a
round body cannot produce that, so body and tail join into one shape as they do in game.

The colour still comes from the skin's own `NoteImage{n}L` sprite (sampled average), so each
column keeps its palette: owc grey/blue/blue/grey, Cho grey.

`Renderer.drawQuad` gained a `radius` argument backed by a rounded-rect SDF in the fragment
shader, and `drawColorQuad` draws a flat shape; `uRect` is declared `highp` in both stages
because a uniform shared by the vertex and fragment shaders must have matching precision.

## Layer order inside a hold note (source-verified)

`DrawableHoldNote` adds its children in this order, and later children draw on top:

```
sizingContainer   (maskedContents = body proxy, tail proxy; then headContainer)
bodyContainer
bodyPiece         the real body
tailContainer     the real tail   <-- TOPMOST of the three
slidingSample
```

so the painter order is **body -> head -> tail**: the TAIL is on top, not the head.
An earlier revision here drew body -> tail -> head, which buried the tail under the head.

## Hit burst placement

`LegacyManiaJudgementPiece.onDirectionChanged()`. Write **S** / **H** for the ×1.6 config
values of `ScorePosition` / `HitPosition` (lazer 768-space), so `hitPositionFromTop = 768 - H`:

```
if S > hitPositionFromTop / 2:  Anchor BottomCentre, Y = S - (768 - H)
else:                           Anchor TopCentre,    Y = S
```

The piece's parent is `DrawableManiaJudgement` (RelativeSizeAxes.Both) inside `Stage`'s
`JudgementContainer` inside a `HitPositionPaddedContainer` whose `Padding.Bottom` is the
**raw** `HitPosition` config value (`HitPositionPaddedContainer.UpdateHitPosition`). Its
content box is therefore exactly `768 - H` tall, measured from the top of the stage. With
`Origin = Centre` the two branches then both collapse to the same place:

```
BottomCentre: centre = (768 - H) + (S - (768 - H)) = S
TopCentre   : centre = 0 + S                       = S
```

**The anchor branch never moves the sprite** — a mania hit burst always sits at
`ScorePosition` from the top of the stage, wherever the judgement line happens to be.
In our view space that is simply `ScorePosition * VIEW_H/480` = `ScorePosition * 2.25`,
because `ScorePosition` is stored raw in 480-space.

Cross-check on the sign: `ManiaLegacySkinTransformer.cs:107-109` puts the combo counter at
`Anchor.TopCentre; combo.Y = ComboPosition`, so these mania Y values are downward from the
top — the default `ComboPosition` 111 lands at 23% of the stage height, which is where the
combo counter sits. (An earlier revision here read the branch as
`768 + S - hitFromTop`, which evaluated to 1035-1305 for real skins, i.e. **below the
viewport**; the same revision also conflated `hitPositionFromTop` (= 1.6H) with the padding
`768 - 1.6H`. They are complementary, and equal only when `HitPosition = 240`.)

Measured after the fix (1080-tall view, sprite centred on `ScorePosition * 2.25`):

| skin | HitPosition | ScorePosition | burst centre Y | judgement line Y |
| :- | -: | -: | -: | -: |
| owc (default) | 412 | 320 | 720 | 927 |
| Cho' | 300 | 280 | 630 | 675 |
| Suisei | 448 | 210 | 472.5 | 1008 |
| boj 1-10K | 432 | 280 | 630 | 972 |

## Hit burst size

The source draws the burst at its natural texture size (`AutoSizeAxes = Axes.Both`), which
for wide skins overflows its own lane (owc: 222 px sprite in a 130 px lane).

**Requested deviation from source:** the burst is scaled so its **width is 75% of its
lane**, aspect ratio preserved — scaled, never stretched. `HIT_BURST_LANE_FRACTION = 0.75`
in `main.js` (first set to 0.30 on request, then widened to 0.75 because 30% read too
small). Verified numerically via `__mania.burstRect()`:

| skin | sprite | natural | drawn at 75% | aspect |
| :- | :- | -: | -: | -: |
| owc (default) | `mania-hit300` | 222×131 | 97.9×57.8 | 1.6947 = 1.6947 |
| Cho' | `mania-hit300` | 158×158 | 143.4×143.4 | 1.0000 = 1.0000 |
| Suisei | `judge2/330` (`Hit300g`) | 200×69 | 114.8×39.6 | 2.8986 = 2.8986 |

## Known gap: no default-skin fallback layer

`getResult()` resolves `Hit300g/300/200/100/50/0` through the skin chain:

```csharp
string filename = this.GetManiaSkinConfig<string>(value)?.Value
                  ?? default_hit_result_skin_filenames[result];
var animation = this.GetAnimation(filename, true, true, frameLength: 1000 / 20d);
```

`GetAnimation` walks **down** the chain, so a user skin that ships no `mania-hit*` still gets
lazer's built-in default-skin sprites. Our loader has only one layer: **boj 1-10K ships no
`mania-hit*` at all, so its replays draw no bursts.** The assets exist in
`%LOCALAPPDATA%\osulazer\current\osu.Game.Resources.dll` (131 MB, the `osu-resources`
package) and could be extracted into a fallback layer.

Blank placeholders are *not* a bug: Cho' ships a fully transparent `mania-hit300g.png`
(502 bytes) and owc a 129-byte one, so `mania-hit300g` bursts correctly draw nothing.
Absent files that our loader *does* fall back on are the `mania-hit300-{n}.png` animation
frames, which fall back to the single `mania-hit300.png`.

## Wiki 60 FPS vs lazer 20 FPS

The wiki says the `mania-hit*` animation is a "fixed looped animation of 60 FPS" and our
loop uses `1000/60`. The lazer loader passes `frameLength: 1000 / 20d` (**20 FPS**) to
`GetAnimation`. Only visible on skins that ship numbered animation frames; single-image
skins are unaffected. Not reconciled — source says 20, wiki says 60.

