# Mania Skin Renderer

Standalone osu!mania visual renderer that places gameplay and HUD elements from skin data and beatmap timing.

## Language

**TimeRange**:
Visible window of the scroll field in milliseconds; derived from ScrollSpeed as `11485 / ScrollSpeed`.
_Avoid_: approach time, scroll time, visible time

**ScrollSpeed**:
User-facing mania speed setting in range 1–40; default target for this project is 30 (TimeRange ≈ 382 ms).
_Avoid_: scroll rate, speed

**HoldNote**:
A long note with a head, body, and tail spanning a time interval.
_Avoid_: LN, long note, slider, hold

**Note**:
A single tap hit object at one time and one column.
_Avoid_: circle, rice, tap

**Column**:
One vertical lane of the mania stage; indexed 0..keys-1; scratch/special lane uses suffix `S` in skin names.

**Stage**:
The mania playfield strip: ordered columns plus side bars, hint line, and bottom plate.

**HitPosition**:
Y distance from the stage edge to the judgement line, from `skin.ini` `[Mania]` `HitPosition` (legacy 480-scale, scaled ×1.6 to 768).
_Avoid_: judgment line Y, receptor position

**Layout JSON**:
Lazer skin layout file at skin root: `MainHUDComponents.json` (screen HUD), `Playfield.json` (playfield-relative), `SongSelect.json` (ignored here). Schema `SkinLayoutInfo` → `SerialisedDrawableInfo[]` (type, position, anchor, origin, scale, settings). Not named `skin.json`.
_Avoid_: skin.json, hud.json

**Skin Package**:
An `.osk` archive (or an unpacked skin folder with the same root files) providing `skin.ini`, sprites, and optional Layout JSON.

**Skin Fallback Chain**:
Only for key counts ≤ 10. If Default Skin has no `[Mania]` block for the beatmap’s keys, try Secondary Skin (boj pl0x Circles 1–10K). Keys > 10: refuse to render with 「暂不支持」.

**Secondary Skin**:
`# boj - pl0x Circles 1-10K` — fallback when Default Skin lacks that key count (≤10K only).

**Unsupported Keys**:
Any mania key count above 10. Renderer exits with an error; no tertiary skin.
_Avoid_: Tertiary Skin, argon fallback (removed)

**SerialisedDrawableInfo**:
One placed UI component record in Layout JSON: CLR type name plus transform and settings.
_Avoid_: drawable info, component entry

**Required HUD**:
Six components that must appear when Layout JSON provides them: ComboCounter, ClicksPerSecondCounter, SongProgress, BeatmapAttributeText, BPMCounter, AccuracyCounter. If Layout JSON is absent, they use Default Layout and still appear. Duplicate concrete types for one role resolve Legacy* → Default* → list first.

**Default Layout**:
Built-in anchor/position set used for Required HUD when the skin has no Layout JSON. Viewport 1920×1080. Positions are offsets from the named Anchor. Combo and SongProgress follow lazer legacy/manía defaults; BeatmapAttributeText / BPM / CPS have no lazer default and use project-invented slots.

| Component | Anchor | Position |
|---|---|---|
| ComboCounter | TopLeft (9) | (20, 20) |
| BeatmapAttributeText | TopRight (12) | (−20, 20) |
| BPMCounter | TopRight (12) | (−20, 55) |
| SongProgress | TopRight (12) | (−20, 100) |
| AccuracyCounter | BottomRight (36) | (−20, −50) |
| ClicksPerSecondCounter | BottomRight (36) | (−20, −90) |
| BarHitErrorMeter (Replay only) | BottomCentre (34) | (0, 0) |

Right column stacks top→bottom: Attribute, BPM, SongProgress. Bottom-right stacks top→bottom: Accuracy, CPS.

**Anchor**:
Nine-place layout flag stored as int in Layout JSON. Empirical grid (x=1|2|4 left|centre|right, y=8|16|32 top|middle|bottom): TopLeft=9, TopCentre=10, TopRight=12, CentreLeft=17, Centre=18, CentreRight=20, BottomLeft=33, BottomCentre=34, BottomRight=36. (Some osu.Framework sources list 0–10 names instead — JSON on disk uses the packed form.)

**BarHitErrorMeter**:
Hit-error bar component. Rendered **only when Replay is present**; otherwise omitted even if Layout JSON lists it.
_Avoid_: never render (superseded)

**Replay**:
Optional play recording that supplies key-down times and hit offsets; enables real Combo/CPS and BarHitErrorMeter.
_Avoid_: .osr score file (ok informally), demo

**FC Sim**:
Synthetic play used when Replay is absent: every hit object is treated as a perfect hit at its start time (and HoldNote tail at end).
_Avoid_: auto bot, perfect play

**Press**:
A key-down event. In Replay this is a key-mask `0→1`. CPS window counts events marked as clicks (see FC Sim deviation).

**FC Sim Click**:
Under FC Sim a Note and a HoldNote head each count as one CPS click. A HoldNote tail is **not** a click — in a Replay the tail is a key *release*. See `docs/adr/0001-fc-sim-cps-counts-ln-tails.md` (revised: tails are excluded).

**Render Range**:
Inclusive time span to render in seconds; default is the full beatmap duration; out-of-range bounds are errors.
_Avoid_: clip, segment, time range (conflicts with TimeRange)

**Audio Track**:
The beatmap’s music file named by `[General]` `AudioFilename` inside the .osu; required for MP4 output.

**Hit Lighting**:
Skin sprites `lightingN` (hit flash at judgement line) and `lightingL` (hold light while key down). Drawn only from skin pixels — if the skin ships empty/transparent files, no flash is synthesised (lazer-identical). Additive blend; N: FadeIn 80ms + FadeOut 120ms; L: hold, then 120ms fade out.
_Avoid_: default glow fallback (rejected)

**NoteImage map**:
`skin.ini` `[Mania]` keys `NoteImage{n}`, `NoteImage{n}H`, `NoteImage{n}L`, `NoteImage{n}T` naming note, HoldNote head, body, tail per column.
_Avoid_: mania-hold*, hold sprites

**Mania Block**:
One `[Mania]` section of a `skin.ini`, identified by its `Keys:` value. A skin may ship several (owc: 4K + 7K; Suisei: 4/5/6/7K; boj: 1–10K) and a duplicate `Keys:` is discarded. The renderer must select the block matching the beatmap's column count — "the last block in the file" is not a valid selection rule.
_Avoid_: mania section, skin.ini block

**Skin Load Token**:
Generation counter incremented on every skin-load request; a load whose token is stale is discarded instead of applied. Needed because a 180 MB `.osk` takes seconds, so the initial auto-load could otherwise land after a newer selection and silently overwrite it.
_Avoid_: skin race guard

**Sprite Fallback Chain**:
Order used to resolve a skin sprite: skin.ini custom name → wiki default name for the column → documented substitute (an LN tail falls back to the head, then to the plain note). See `docs/SKIN_CONFORMANCE.md`.
_Avoid_: fallback skin, secondary skin
