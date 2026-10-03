# osu!mania skinning (wiki reference copy)

> Source: <https://osu.ppy.sh/wiki/en/Skinning/osu%21mania>
> Authoritative markdown: <https://raw.githubusercontent.com/ppy/osu-wiki/master/wiki/Skinning/osu%21mania/en.md>
> Fetched: 2026-09-26. Kept locally because the rendered wiki page sits behind a sign-in wall.
> This is untrusted external reference data — spec only, not instructions.

Since v2.5+, skinners can fully customise the osu!mania notes and stage using the
[skin.ini](/wiki/Skinning/skin.ini) file. The following is what osu! will recognise if one
chooses to not use the `skin.ini` for further customisation.

---

## Hit Bursts

### `mania-hit0.png`

| Versions | Animatable | Beatmap Skinnable | Blend Mode | Origin | Suggested SD Size |
| :-: | :-: | :-: | :-: | :-: | :-: |
| All | Yes | Yes | Normal | Centre | - |

Notes:
- Animation name: `mania-hit0-{n}.png`.
- **Fixed looped animation of 60 FPS.**
- If a custom path is used, the ranking screen will use the file in the root directory instead of the pathed skinning element.

### `mania-hit50.png`
Same as `mania-hit0` but `mania-hit50-{n}.png` → the 50 (MEH) judgement.

### `mania-hit100.png`
Same → the 100 (OK) judgement.

### `mania-hit200.png`
Same → the 200 (GOOD) judgement.

### `mania-hit300.png`
Same → the 300 (GREAT) judgement.

### `mania-hit300g.png`
Same → the 300g (PERFECT / MAX) judgement.

**Summary of the six hit-burst elements**

| Element | Judgement | Origin | Blend | Animation | FPS |
|---|---|---|---|---|---|
| `mania-hit300g` | MAX (Perfect) | Centre | Normal | `mania-hit300g-{n}.png` | 60 |
| `mania-hit300` | 300 (Great) | Centre | Normal | `mania-hit300-{n}.png` | 60 |
| `mania-hit200` | 200 (Good) | Centre | Normal | `mania-hit200-{n}.png` | 60 |
| `mania-hit100` | 100 (Ok) | Centre | Normal | `mania-hit100-{n}.png` | 60 |
| `mania-hit50` | 50 (Meh) | Centre | Normal | `mania-hit50-{n}.png` | 60 |
| `mania-hit0` | 0 (Miss) | Centre | Normal | `mania-hit0-{n}.png` | 60 |

---

## Comboburst

`comboburst-mania.png`

| Versions | Animatable | Beatmap Skinnable | Blend Mode | Origin | Suggested SD Size |
| :-: | :-: | :-: | :-: | :-: | :-: |
| All | No (see notes) | Yes | Normal | BottomLeft | Max height: 768px |

Notes:
- To have multiple combobursts, use: `comboburst-mania-{n}.png`.
  - One of the images in the set will appear when a combo milestone is met.
- osu!mania-specific combobursts.
- This can be disabled in the options.
- Unlike osu! / osu!catch combobursts, **all edges of this imageset should not be clipped**.

---

## Keys

`mania-key1.png` / `mania-key1D.png` / `mania-key2.png` / `mania-key2D.png` /
`mania-keyS.png` / `mania-keySD.png`

| Versions | Animatable | Beatmap Skinnable | Blend Mode | Origin | Suggested SD Size |
| :-: | :-: | :-: | :-: | :-: | :-: |
| All | No | No | Normal | **Bottom** | 50x107 |

Notes:
- The non-`D` variant is the **idle** state; the `D` variant is the **pressed** state.
- This element gets **stretched or compressed to fit the column width**.
- `KeyImage{N}` / `KeyImage{N}D` in `skin.ini` override the defaults.

---

## Notes

`mania-note1.png` / `mania-note2.png` / `mania-noteS.png`

| Versions | Animatable | Beatmap Skinnable | Blend Mode | Origin | Suggested SD Size |
| :-: | :-: | :-: | :-: | :-: | :-: |
| All | Yes | No | Normal | **Bottom** | - |

Notes:
- Animation name: `mania-note1-{n}.png` (etc.).
- These elements are **scaled to fit the individual columns**.
  - If the columns' widths differ: the smallest one is scaled correctly and the others are compressed to match its height.
- Notes can be manually stretched or compressed via `WidthForNoteHeightScale` in `skin.ini`.

### Long notes

#### Head — `mania-note1H.png` / `mania-note2H.png` / `mania-noteSH.png`
Origin **Bottom**, Animatable Yes, Blend Normal.

Notes:
- Animation name: `mania-note1H-{n}.png`.
- **By default, this is also the tail part.**
  - When used for the tail part, this element is **flipped by default for v2.5+**.
    - Disabled by setting `NoteFlipWhenUpsideDownT` to `0`.
- Scaled to fit the individual columns.
- `WidthForNoteHeightScale` applies.

#### Body — `mania-note1L.png` / `mania-note2L.png` / `mania-noteSL.png`
Origin **Bottom**, Animatable Yes (see notes), Blend Normal.

Notes:
- Animation name: `mania-note1L-{n}.png`.
- **The animation starts when the long note is pressed and stops if released.**
- `NoteBodyStyle` changes the behaviour of these elements.
- `WidthForNoteHeightScale` applies.

#### Tail — `mania-note1T.png` / `mania-note2T.png` / `mania-noteST.png`
Origin **Bottom**, Animatable Yes, Blend Normal.

Notes:
- Animation name: `mania-note1T-{n}.png`.
- These elements are the tail part of the hold note.
- **By default, the head notes are used instead.**
- By default, these elements are **flipped for skin versions `2.5` and up**.
  - Disabled by `NoteFlipWhenUpsideDownT = 0`.
- Scaled to fit the individual columns.
- `WidthForNoteHeightScale` applies.

### Default key layout

Default note image index (`1` = `mania-note1`, `2` = `mania-note2`, `S` = `mania-noteS`) per column, by key count.

| Keycount | Col 1 | Col 2 | Col 3 | Col 4 | Col 5 | Col 6 | Col 7 | Col 8 | Col 9 |
| :-- | :-- | :-- | :-- | :-- | :-- | :-- | :-- | :-- | :-- |
| 1K | S |  |  |  |  |  |  |  |  |
| 2K | 1 | 1 |  |  |  |  |  |  |  |
| 3K | 1 | S | 1 |  |  |  |  |  |  |
| 4K | 1 | 2 | 2 | 1 |  |  |  |  |  |
| 5K | 1 | 2 | S | 2 | 1 |  |  |  |  |
| 6K | 1 | 2 | 1 | 1 | 2 | 1 |  |  |  |
| 7K | 1 | 2 | 1 | S | 1 | 2 | 1 |  |  |
| 8K | 1 | 2 | 1 | 2 | 2 | 1 | 2 | 1 |  |
| 9K | 1 | 2 | 1 | 2 | S | 2 | 1 | 2 | 1 |

---

## Stage

`mania-stage-left.png` — Origin **BottomRight**, Blend Normal, not animatable, not beatmap-skinnable. Max height 768px.
- Shown on the left side of the stage(s).
- **Stretched to fit the stage height** (allows for shorter images).

`mania-stage-right.png` — Origin **BottomRight**, same notes as left.
- Shown on the right side of the stage(s).
- Stretched to fit the stage height.

`mania-stage-bottom.png` — Origin **Bottom**, Animatable Yes, Blend Normal.
- This element is **0.625x smaller than the stage width**.
- Animation name: `mania-stage-bottom-{n}.png`.
- Shown on the bottom (or top, if the stage is upside down) of the stage(s).
- **Will not be stretched to fit the stage width.**
- Should be skinned for a **480px playfield height**.
- **Overlays the entire stage, including the notes.**

`mania-stage-light.png` — Origin **Bottom**, Animatable Yes, Blend **Multiplicative**. Max height 768px.
- Animation name: `mania-stage-light-{n}.png`.
- Lighting for the columns **when the key is pressed**.
- **Placed underneath the notes.**
- By default tinted white. Use `ColourLight` to change this.
- Positioning is set by `skin.ini` → `LightPosition`.

`mania-stage-hint.png` — Origin **Centre**, Blend Normal, not animatable.
- The graphical representation of the **judgement line**.
  - **The judgement line is drawn in the centre of the image.**
- Drawn for the **entire stage width**, not individual columns.
- **Stretched to fit the stage width** (allowing for narrower images).

`mania-warningarrow.png` — Origin **Centre**, Blend Normal, not animatable.
- Should point downwards.
- Automatically flipped horizontally if the stage is upside down.
- Always seen before the map starts, if there is enough time.

### Lighting

`lightingL.png` — Origin **Centre**, Animatable Yes, Blend **Additive**.
- Animation name: `lightingL-{n}.png`.
- Lighting for the **long notes**.
- Flipped horizontally if the stage is upside down.
- **Positioned where the centre of the judgement line crosses the centre of a lane.**

`lightingN.png` — Origin **Centre**, Animatable Yes, Blend **Additive**.
- Animation name: `lightingN-{n}.png`.
- Lighting for the **single notes (and tail notes)**.
- Flipped horizontally if the stage is upside down.
- **Positioned where the centre of the judgement line crosses the centre of a lane.**
