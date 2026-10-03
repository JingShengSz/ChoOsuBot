# osu!mania hold note — geometry, masking, clipping and draw order (source reference)

A literal, quote-backed statement of how an osu!mania **long note (`HoldNote`)** is composed and
drawn by osu!lazer. **This document does not describe this renderer.** It describes the source only.

## Provenance

| Item | Value |
|---|---|
| Source checkout | `C:\Users\OwO\Desktop\osu-master` (read-only) |
| VCS revision | **unavailable** — the checkout has no `.git` directory (`Test-Path .git` → `False`). Cite by path + line, not by commit. |
| File mtimes | `osu.Game.Rulesets.Mania/Objects/Drawables/DrawableHoldNote.cs` — 2026-08-03 14:02:11; `osu.Game.Rulesets.Mania/Skinning/Legacy/LegacyBodyPiece.cs` — 2026-08-03 14:02:11; `osu.Game/Rulesets/UI/Scrolling/ScrollingHitObjectContainer.cs` — 2026-08-03 14:02:32 |
| Framework reference | `osu.Game/osu.Game.csproj:42` — `<PackageReference Include="ppy.osu.Framework" Version="2026.731.0" />` |
| Framework source | **Not vendored in the checkout** (o!lazer references `ppy.osu.Framework` as a NuGet package; only `2026.303.0` is present in the local NuGet cache, which is *not* the pinned version). Framework-level quotes below were fetched from `raw.githubusercontent.com/ppy/osu-framework/2026.731.0/...` and are marked **[framework]**. Every such claim is tagged, so a claim that matters can be re-verified against the pinned package. |

All `file:line` citations below are relative to that checkout unless the path is absolute.
Code quotes are verbatim, including the source's own typos, hedges and stale comments.
Everything the source does not say is listed in **§9 Ambiguity ledger**.

### Notation used below

* Screen/layout space in osu!framework: **y grows downward**; the top-left corner of a drawable is
  `(0, 0)` in its own local space.
* `Down` = `ScrollingDirection.Down` = **the mania default** (`ManiaRulesetConfigManager.cs:25`).
  All "for DOWNSCROLL" statements are the default path; the Up path is the mirror image and is called
  out where it differs.
* `y(t)` := the y coordinate, inside the `ScrollingHitObjectContainer`'s coordinate space, of the
  **leading edge of a note whose time is `t`** (this is the value `updatePosition` assigns plus the
  drawable's anchor offset — see §4.1). For Down the leading edge is the bottom edge.
* `H_head` = `Head.Height`, `H_tail` = `Tail.Height`, `L` = the hold note's own `DrawHeight`
  (= `Height`, because nothing scales the hold note itself).
* "anchor" arithmetic (see §2.5 and §4.1 for why this is needed):
  **[framework]** `Drawable.AnchorPosition => RelativeAnchorPosition * Parent?.ChildSize ?? Vector2.Zero`
  and `computeDrawInfo(): Vector2 pos = DrawPosition + AnchorPosition; ... if (Parent != null) pos += Parent.ChildOffset;`
  (`osu.Framework/Graphics/Drawable.cs`, tag `2026.731.0`). So a child with `Anchor = Origin = BottomCentre`
  ends up with its **bottom edge at `Position.Y + Parent.ChildSize.Y`**, and a child with
  `Anchor = Origin = TopCentre` with its **top edge at `Position.Y`**. `ChildSize`/`ChildOffset` include
  padding: **[framework]** `CompositeDrawable.ChildSize => DrawSize - new Vector2(Padding.TotalHorizontal, Padding.TotalVertical)`
  and `ChildOffset => new Vector2(Padding.Left, Padding.Top)`.

### Files read

Ruleset (osu! side):

- `osu.Game.Rulesets.Mania/Objects/HoldNote.cs`, `HeadNote.cs`, `TailNote.cs`, `HoldNoteBody.cs`, `Note.cs`
- `osu.Game.Rulesets.Mania/Objects/Drawables/DrawableHoldNote.cs`, `DrawableHoldNoteHead.cs`,
  `DrawableHoldNoteTail.cs`, `DrawableHoldNoteBody.cs`, `DrawableManiaHitObject.cs`, `DrawableNote.cs`,
  `DrawableBarLine.cs`
- `osu.Game.Rulesets.Mania/Judgements/HoldNoteJudgementResult.cs`
- `osu.Game.Rulesets.Mania/Skinning/Legacy/LegacyBodyPiece.cs`, `LegacyNotePiece.cs`,
  `LegacyHoldNoteHeadPiece.cs`, `LegacyHoldNoteTailPiece.cs`, `LegacyManiaColumnElement.cs`,
  `ManiaLegacySkinTransformer.cs`, `HitTargetInsetContainer.cs`, `LegacyKeyArea.cs`
- `osu.Game.Rulesets.Mania/Skinning/Default/DefaultBodyPiece.cs`, `DefaultNotePiece.cs`, `IHoldNoteBody.cs`
- `osu.Game.Rulesets.Mania/Skinning/Argon/ManiaArgonSkinTransformer.cs`, `ArgonNotePiece.cs` (body only, cross-ref)
- `osu.Game.Rulesets.Mania/UI/Column.cs`, `Stage.cs`, `ManiaPlayfield.cs`, `DrawableManiaRuleset.cs`,
  `ManiaScrollingDirection.cs`, `ManiaPlayfieldAdjustmentContainer.cs`
- `osu.Game.Rulesets.Mania/UI/Components/ColumnHitObjectArea.cs`, `HitPositionPaddedContainer.cs`,
  `DefaultKeyArea.cs`
- `osu.Game.Rulesets.Mania/Configuration/ManiaRulesetConfigManager.cs`, `Mods/ManiaModConstantSpeed.cs`
- `osu.Game.Rulesets.Mania/Edit/Blueprints/HoldNoteSelectionBlueprint.cs` (independent corroboration of the
  hold-note local geometry)

Framework side:

- `osu.Game/Rulesets/UI/Scrolling/ScrollingHitObjectContainer.cs`, `ScrollingPlayfield.cs`,
  `ScrollingDirection.cs`, `IScrollingInfo.cs`, `DrawableScrollingRuleset.cs`
- `osu.Game/Rulesets/UI/Scrolling/Algorithms/{IScrollAlgorithm,ConstantScrollAlgorithm,SequentialScrollAlgorithm,OverlappingScrollAlgorithm}.cs`
- `osu.Game/Rulesets/UI/HitObjectContainer.cs`, `Playfield.cs`
- `osu.Game/Rulesets/Objects/Drawables/DrawableHitObject.cs`
- `osu.Game/Skinning/LegacyManiaSkinConfiguration.cs`, `SkinnableDrawable.cs`
- **[framework]** `Graphics/Drawable.cs`, `Graphics/Containers/CompositeDrawable.cs`,
  `Graphics/Containers/Container.cs`, `Graphics/Sprites/Sprite.cs`,
  `Graphics/Animations/{Animation,DrawableAnimation,TextureAnimation}.cs`

---

## 1. Children and draw order

### 1.1 The tree, as built in `load()`

`DrawableHoldNote.cs:81-126` (verbatim, comments included):

```csharp
        [BackgroundDependencyLoader]
        private void load()
        {
            Container maskedContents;

            AddRangeInternal(new Drawable[]
            {
                sizingContainer = new Container
                {
                    RelativeSizeAxes = Axes.Both,
                    Children = new Drawable[]
                    {
                        maskingContainer = new Container
                        {
                            RelativeSizeAxes = Axes.Both,
                            Child = maskedContents = new Container
                            {
                                RelativeSizeAxes = Axes.Both,
                                Masking = true,
                            }
                        },
                        headContainer = new Container<DrawableHoldNoteHead> { RelativeSizeAxes = Axes.Both }
                    }
                },
                bodyContainer = new Container<DrawableHoldNoteBody> { RelativeSizeAxes = Axes.Both },
                bodyPiece = new SkinnableDrawable(new ManiaSkinComponentLookup(ManiaSkinComponents.HoldNoteBody), _ => new DefaultBodyPiece
                {
                    RelativeSizeAxes = Axes.Both,
                })
                {
                    RelativeSizeAxes = Axes.X
                },
                tailContainer = new Container<DrawableHoldNoteTail> { RelativeSizeAxes = Axes.Both },
                slidingSample = new PausableSkinnableSound
                {
                    Looping = true,
                    MinimumSampleVolume = MINIMUM_SAMPLE_VOLUME,
                }
            });

            maskedContents.AddRange(new[]
            {
                bodyPiece.CreateProxy(),
                tailContainer.CreateProxy(),
            });
        }
```

The three nested hit objects are placed into these containers (`DrawableHoldNote.cs:142-160`):

```csharp
            switch (hitObject)
            {
                case DrawableHoldNoteHead head:
                    headContainer.Child = head;
                    break;

                case DrawableHoldNoteTail tail:
                    tailContainer.Child = tail;
                    break;

                case DrawableHoldNoteBody body:
                    bodyContainer.Child = body;
                    break;
            }
```

### 1.2 What `AddRange`/`AddRangeInternal` do to order

**[framework]** `CompositeDrawable.cs`: *"Adds a range of children to `InternalChildren`. This is
equivalent to calling `AddInternal(Drawable)` on each element of the range in order."* and
`AddInternal` assigns `drawable.ChildID = ++currentChildID` (monotonically increasing).
`CompositeDrawable.Compare` sorts by `y.Depth.CompareTo(x.Depth)` and then `x.ChildID.CompareTo(y.ChildID)`,
and `Drawable.Depth` is documented as *"A Drawable with higher `Depth` than another Drawable is drawn
behind the other Drawable."* — i.e. with equal (default) `Depth`, **the first-added child is drawn
first, therefore behind**. The repo confirms the direction of that rule in the mania input path,
`osu.Game/Rulesets/UI/HitObjectContainer.cs:184-186`:

```csharp
            // Put earlier hitobjects towards the end of the list, so they handle input first
            int i = yObj.HitObject.StartTime.CompareTo(xObj.HitObject.StartTime);
```

(end of the list = frontmost = drawn last = handles input first).

`maskedContents.AddRange(new[] { bodyPiece.CreateProxy(), tailContainer.CreateProxy() })` is
`Container.AddRange` (**[framework]** `Container.cs`: *"Adds a range of children. This is equivalent to
calling `Add(T)` on each element of the range in order."*), and for a plain `Container` whose
`Content` is itself, `Add` → `AddInternal`. Net effect: **inside the mask, the body proxy is added
first and the tail proxy second.**

### 1.3 `CreateProxy()` suppresses the original's rendering

This is the single most consequential fact for draw order, and it is framework-level:

**[framework]** `Drawable.CreateProxy()` (`osu.Framework/Graphics/Drawable.cs`):

```
        /// <summary>
        /// Creates a proxy drawable which can be inserted elsewhere in the scene graph.
        /// Will cause the original instance to not render itself.
        /// Creating multiple proxies is not supported and will result in an
        /// <see cref="InvalidOperationException"/>.
        /// </summary>
```

The osu! side relies on this explicitly — `Stage.cs:102-105` (comment) plus `Stage.cs:149-150`:

```csharp
                // For input purposes, the background is added at the highest depth, but is then proxied back below all other elements externally
                // (see `Stage.columnBackgrounds`).
```

```csharp
                topLevelContainer.Add(column.TopLevelContainer.CreateProxy());
                columnBackgrounds.Add(column.BackgroundContainer.CreateProxy());
```

Consequence for the hold note: `bodyPiece` (child 3 of the hold note) and `tailContainer`
(child 4) **do not draw where they sit**; they draw where their proxies sit — inside
`maskedContents`. Both originals remain in the tree (the proxy mirrors the target's draw state, so
the target must still be laid out), which is the "machinations" `DrawableHoldNote.OnKilled` refers to.

### 1.4 Painter's order (the answer)

Reading the code in insertion order and applying §1.2–§1.3, the effective painter's order for one
`DrawableHoldNote` (later = on top) is:

| # | What paints | Where it lives | Masked? |
|---|---|---|---|
| 1 | **body** (`LegacyBodyPiece` / `DefaultBodyPiece` / `ArgonHoldBodyPiece`) | via `bodyPiece.CreateProxy()` inside `maskedContents` | **yes** |
| 2 | **tail** (`DrawableHoldNoteTail`, itself containing the tail piece) | via `tailContainer.CreateProxy()` inside `maskedContents` | **yes** |
| 3 | **head** (`DrawableHoldNoteHead`, itself containing the head piece) | the real drawable in `headContainer`, a *sibling* of `maskingContainer` inside `sizingContainer`, added after it | **no** |

Nothing else in this drawable paints: `bodyContainer` holds `DrawableHoldNoteBody`, which has no
visual children at all (`DrawableHoldNoteBody.cs:8-33` — no `load()`, no children);
`slidingSample` is a `PausableSkinnableSound` (audio only).

So: **body behind tail, tail behind head; body and tail are clipped by the mask, the head is not.**

### 1.5 What clips what, in the wider mania chain

Worth stating because it bounds the hold note's picture:

- `DrawableHoldNote` itself: no `Masking` (nothing in `DrawableHoldNote.cs` sets it).
- `headContainer`, `tailContainer`, `bodyContainer`, `sizingContainer`: no `Masking`.
- `maskedContents`: `Masking = true` (`DrawableHoldNote.cs:99`) — the only clip in the hold note.
- The column's hit-object area is **not** masked: `ColumnHitObjectArea.cs:23-44` adds
  `UnderlayElements`, `hitTarget`, `content`, `Explosions`, none with `Masking = true`.
- `Column` itself: no `Masking`.
- The only masked container in the stage is the bar-line mask, `Stage.cs:97-114`, whose child is a
  `HitObjectContainer` holding **bar lines**, not notes.

`DefaultNotePiece` and `DefaultBodyPiece`'s inner foreground use `Masking`/`BufferedContainer` for
their own shape (corner radius, the body "hole"), not to clip the parent.

---

## 2. The body rect

### 2.1 The code

`DrawableHoldNote.cs:250-253`:

```csharp
            // Position and resize the body to lie half-way under the head and the tail notes.
            // The rationale for this is account for heads/tails with corner radius.
            bodyPiece.Y = (Direction.Value == ScrollingDirection.Up ? 1 : -1) * Head.Height / 2;
            bodyPiece.Height = DrawHeight - Head.Height / 2 + Tail.Height / 2;
```

Both lines run **every frame** in `Update()` (after the two padding assignments of §3).

### 2.2 What the body piece is

`bodyPiece` is a `SkinnableDrawable` created with `RelativeSizeAxes = Axes.X`
(`DrawableHoldNote.cs:106-112`) — width = 100 % of the hold note, height = the absolute value set above.
Its own anchor is set by direction (`DrawableHoldNote.cs:187-201`):

```csharp
            if (e.NewValue == ScrollingDirection.Up)
            {
                bodyPiece.Anchor = bodyPiece.Origin = Anchor.TopLeft;
                sizingContainer.Anchor = sizingContainer.Origin = Anchor.BottomLeft;
            }
            else
            {
                bodyPiece.Anchor = bodyPiece.Origin = Anchor.BottomLeft;
                sizingContainer.Anchor = sizingContainer.Origin = Anchor.TopLeft;
            }
```

Note that **anything that is not `Up` takes the `else` branch** (so mania's `Down` — and, were they
ever used, `Left`/`Right` — get `BottomLeft` / `-1`).

On the `Up` branch the body grows *downward* from `Y = +H_head/2`; on the `else` (Down) branch it
grows *upward* from `Y = -H_head/2`, because `Anchor = Origin = BottomLeft`
(**[framework]** a `BottomLeft` anchored+origin'd child's bottom-left corner sits at
`Position + (0, Parent.ChildSize.Y)`).

### 2.3 What `Head.Height` / `Tail.Height` / `DrawHeight` are

* `Head`/`Tail` are `headContainer.Child` / `tailContainer.Child` (`DrawableHoldNote.cs:49-51`),
  i.e. the live `DrawableHoldNoteHead` / `DrawableHoldNoteTail`.
* `DrawableNote` is `AutoSizeAxes = Axes.Y` (`DrawableNote.cs:46-50`) and its `headPiece` is
  `RelativeSizeAxes = Axes.X, AutoSizeAxes = Axes.Y` (`DrawableNote.cs:57-61`), so a head/tail's
  height is the laid-out height of its skin piece:
  * pieces that size themselves: the fallback `DefaultNotePiece.cs:22` —
    `public const float NOTE_HEIGHT = 12;` with `Height = NOTE_HEIGHT` in its constructor, so
    `Head.Height == Tail.Height == 12` whenever no mania hold-head/hold-tail skin piece is provided
    (`DrawableNote.cs:57` — `_ => new DefaultNotePiece()`); Argon provides its own pieces, also equal
    to each other (`ArgonNotePiece.NOTE_HEIGHT = 42`, `ArgonNotePiece.cs:21`);
  * legacy piece: see §4.6.
* The formula reads `Height`, **not** `DrawHeight`. That is `Drawable.Size.Y`, the *unscaled* size;
  they coincide here because nothing scales the head/tail drawables themselves (`LegacyNotePiece`
  scales its *inner* sprite, and the auto-size accounts for that via `BoundingBox`).
* `DrawHeight` (unqualified) is **the hold note's own drawn height**, `Drawable.DrawHeight => DrawSize.Y`,
  `DrawSize => ApplyRelativeAxes(RelativeSizeAxes, Size, FillMode)` **[framework]**. For this drawable
  that number is assigned by the scroll container — `ScrollingHitObjectContainer.cs:258-269`:

```csharp
        private void updateLayoutRecursive(DrawableHitObject hitObject, double? parentHitObjectStartTime = null)
        {
            parentHitObjectStartTime ??= hitObject.HitObject.StartTime;

            if (hitObject.HitObject is IHasDuration e)
            {
                float length = LengthAtTime(hitObject.HitObject.StartTime, e.EndTime);
                if (scrollingAxis == Direction.Horizontal)
                    hitObject.Width = length;
                else
                    hitObject.Height = length;
            }
```

`HoldNote` is `IHasDuration` (`HoldNote.cs:19` — `public class HoldNote : ManiaHitObject, IHasDuration`),
so **`DrawHeight` = `LengthAtTime(StartTime, EndTime)`** — the pixel length the active scroll algorithm
assigns to the hold's time span, *not* `(EndTime - StartTime) / TimeRange * height` in general
(mania's default algorithm is per-timing-point: see §2.6). The hold note is `RelativeSizeAxes = Axes.X`
(`DrawableManiaHitObject.cs:46-50`) with `Scale = 1`, so `DrawHeight == Height == L`.

### 2.4 The two screen positions that bound the body (DOWNSCROLL)

For `Down`, with `y(t)` defined as in the notation block (leading — i.e. bottom — edge of a note at
time `t`), and using the anchors of §2.2:

* the hold note's own rectangle spans exactly **`y(tail time)` (top) to `y(head time)` (bottom)**:
  its `Anchor = Origin = BottomCentre` (`DrawableManiaHitObject.cs:68-71`) puts its bottom edge at
  `Position.Y + Parent.ChildSize.Y`, and `Position.Y` at the head's time is the head's time position;
* therefore the hold's local space is `local 0 ≡ y(tail time)`, `local L ≡ y(head time)`.

Substituting `Y_body = -H_head/2` and `Height = L - H_head/2 + H_tail/2`:

* **bottom edge of the body** = `local (L - H_head/2)` = **`y(head time) − H_head/2`**
* **top edge of the body** = `local (−H_tail/2)` = **`y(tail time) − H_tail/2`**

In words, for downscroll:

> The body runs from **half a tail-height above the tail's time position** down to **half a
> head-height above the head's time position**. Equivalently — and this is the phrasing to implement
> against — **the body's two edges are the vertical CENTRES of the tail sprite and the head sprite**:
> the tail's centre is `y(tail time) − H_tail/2` because the tail's bottom edge sits *on* its time
> position, and the head's centre is `y(head time) − H_head/2` for the same reason.
> Both notes "hang above" their time position; the body is inset by half a note at each end,
> which is exactly what the source comment calls "account for heads/tails with corner radius".

The same statement holds for `Up` after mirroring (`bodyPiece.Y = +H_head/2`, `Anchor = Origin = TopLeft`,
head/tail `Anchor = Origin = TopCentre`, so the head's *top* edge sits on its position): **the body is
always delimited by the head's and tail's vertical centres**; only which one is on which side flips.

Independent corroboration of the local geometry (same numbers, editor side) —
`osu.Game.Rulesets.Mania/Edit/Blueprints/HoldNoteSelectionBlueprint.cs:94-113`:

```csharp
            head.Height = DrawableObject.Head.DrawHeight;
            head.Y = HitObjectContainer.PositionAtTime(HitObject.Head.StartTime, HitObject.StartTime);
            tail.Height = DrawableObject.Tail.DrawHeight;
            tail.Y = HitObjectContainer.PositionAtTime(HitObject.Tail.StartTime, HitObject.StartTime);
            Height = HitObjectContainer.LengthAtTime(HitObject.StartTime, HitObject.EndTime) + tail.DrawHeight;
```

(with `Origin = direction.NewValue == ScrollingDirection.Down ? Anchor.BottomCentre : Anchor.TopCentre;`
on the line above it).

### 2.5 Why the anchors are load-bearing (easy to get wrong)

Because `bodyPiece` is `Anchor = Origin = BottomLeft` on the Down branch, the sign of `Y` is *not*
"how far down the body is". With `Anchor/Origin = BottomLeft`,
`Y = -H_head/2` means "the body's bottom edge sits `H_head/2` px above the parent's bottom edge".
Any reimplementation that anchors the body at the top and copies the `Y` expression verbatim gets the
body one full hold-length away from where lazer puts it.

### 2.6 Which scroll algorithm produces those positions (mania default)

* `DrawableScrollingRuleset.cs:172` — `private ScrollVisualisationMethod visualisationMethod = ScrollVisualisationMethod.Sequential;`
  and `:184-200` selects `new SequentialScrollAlgorithm(ControlPoints)` for `Sequential`.
* `ManiaModConstantSpeed.cs:27-31` is the only thing in the ruleset that switches it:
  `maniaRuleset.VisualisationMethod = ScrollVisualisationMethod.Constant;`
* `DrawableManiaRuleset.cs:53` — `protected override bool RelativeScaleBeatLengths => true;` and
  `:90-99` cancel the global velocity / fold in the slider multiplier. `TimeRange` itself is
  `TargetTimeRange * AggregateTempo * AggregateFrequency * scale` (`DrawableManiaRuleset.cs:167-176`),
  with `scale = (768 - hitPosition) / (768 - DEFAULT_HIT_POSITION)`, and
  `ComputeScrollTime(speed) => MAX_TIME_RANGE / scrollSpeed` (`:183`), defaults
  `ScrollSpeed = 8.0`, `ScrollDirection = Down` (`ManiaRulesetConfigManager.cs:24-25`).
* `SequentialScrollAlgorithm.GetLength` / `PositionAt` (`SequentialScrollAlgorithm.cs:35-45`):

```csharp
        public float GetLength(double startTime, double endTime, double timeRange, float scrollLength)
        {
            double objectLength = relativePositionAt(endTime, timeRange) - relativePositionAt(startTime, timeRange);
            return (float)(objectLength * scrollLength);
        }

        public float PositionAt(double time, double currentTime, double timeRange, float scrollLength, double? originTime = null)
        {
            double timelineLength = relativePositionAt(time, timeRange) - relativePositionAt(currentTime, timeRange);
            return (float)(timelineLength * scrollLength);
        }
```

Both `GetLength(start,end)` and `PositionAt(end, start)` reduce to the same expression, so — for
`Sequential`, `Constant` and `Overlapping` alike — **`DrawHeight` (the hold's `Height`) is exactly the
pixel distance between `y(head time)` and `y(tail time)`**, i.e. `L = y(head time) − y(tail time)` for Down.

---

## 3. The mask

### 3.1 The two containers

From the tree in §1.1 (`DrawableHoldNote.cs:88-104`):

```csharp
                sizingContainer = new Container
                {
                    RelativeSizeAxes = Axes.Both,
                    Children = new Drawable[]
                    {
                        maskingContainer = new Container
                        {
                            RelativeSizeAxes = Axes.Both,
                            Child = maskedContents = new Container
                            {
                                RelativeSizeAxes = Axes.Both,
                                Masking = true,
                            }
                        },
                        headContainer = new Container<DrawableHoldNoteHead> { RelativeSizeAxes = Axes.Both }
                    }
                },
```

Stated in the class's own words (`DrawableHoldNote.cs:59-67`):

```csharp
        /// <summary>
        /// Contains the size of the hold note covering the whole head/tail bounds. The size of this container changes as the hold note is being pressed.
        /// </summary>
        private Container sizingContainer;

        /// <summary>
        /// Contains the contents of the hold note that should be masked as the hold note is being pressed. Follows changes in the size of <see cref="sizingContainer"/>.
        /// </summary>
        private Container maskingContainer;
```

Note the naming trap: **the container that actually clips is `maskedContents` (`Masking = true`),
not `maskingContainer` (a plain, unpadded-by-default container whose only job is to carry the padding
of §3.3).** `maskingContainer` has one child, so its `Child` setter is used
(**[framework]** `Container.Child` setter = `Clear(); Add(value);`).

### 3.2 The paddings (set every frame, unconditionally)

`DrawableHoldNote.cs:234-248`:

```csharp
            // Pad the full size container so its contents (i.e. the masking container) reach under the tail.
            // This is required for the tail to not be masked away, since it lies outside the bounds of the hold note.
            sizingContainer.Padding = new MarginPadding
            {
                Top = Direction.Value == ScrollingDirection.Down ? -Tail.Height : 0,
                Bottom = Direction.Value == ScrollingDirection.Up ? -Tail.Height : 0,
            };

            // Pad the masking container to the starting position of the body piece (half-way under the head).
            // This is required to make the body start getting masked immediately as soon as the note is held.
            maskingContainer.Padding = new MarginPadding
            {
                Top = Direction.Value == ScrollingDirection.Up ? Head.Height / 2 : 0,
                Bottom = Direction.Value == ScrollingDirection.Down ? Head.Height / 2 : 0,
            };
```

**Both paddings apply always — holding or not, judged or not.** They are recomputed from
`Head.Height`/`Tail.Height`/`Direction` on every `Update()` of the hold note;
`maskingContainer.Padding` is *not* gated on `IsHolding` or on the `if` of §3.4.

The `sizingContainer.Padding` values are **negative**, which *grows* the child area rather than
shrinking it (**[framework]** `ChildSize = DrawSize - Padding.Total`, `ChildOffset = (Padding.Left, Padding.Top)`):
on Down, `Top = -Tail.Height` gives children `ChildOffset.Y = -Tail.Height` (shifted **up** by
`Tail.Height`) and `ChildSize.Y = sizingContainer height + Tail.Height` (grown by the same amount).
That is precisely "the mask reaches Tail.Height beyond the top of the hold note so that the tail —
which pokes out above the hold note's rectangle — is not clipped away".

### 3.3 The shrink update, and the exact condition

`DrawableHoldNote.cs:255-271`:

```csharp
            if (Time.Current >= HitObject.StartTime)
            {
                // As the note is being held, adjust the size of the sizing container. This has two effects:
                // 1. The contained masking container will mask the body and ticks.
                // 2. The head note will move along with the new "head position" in the container.
                //
                // As per stable, this should not apply for early hits, waiting until the object starts to touch the
                // judgement area first.
                if (Head.IsHit && !Result.DroppedHoldAfter(HitObject.StartTime) && DrawHeight > 0)
                {
                    // How far past the hit target this hold note is.
                    float yOffset = Direction.Value == ScrollingDirection.Up ? -Y : Y;
                    sizingContainer.Height = 1 - yOffset / DrawHeight;
                }
            }
            else
                sizingContainer.Height = 1;
```

The exact condition under which the mask shrinks is the conjunction:

1. `Time.Current >= HitObject.StartTime` — **outer** guard, i.e. never before the head's own time,
   even if the head was hit early ("As per stable, this should not apply for early hits").
2. `Head.IsHit` — the head has a hit result (`DrawableHitObject.IsHit => Result?.IsHit ?? false`).
3. `!Result.DroppedHoldAfter(HitObject.StartTime)` — no recorded "not holding" state at or after the
   start time; `HoldNoteJudgementResult.cs:30-39` walks the reported hold-state stack:

```csharp
        public bool DroppedHoldAfter(double time)
        {
            foreach (var state in holdingState)
            {
                if (state.time >= time && !state.holding)
                    return true;
            }

            return false;
        }
```

4. `DrawHeight > 0` — division guard *and* volume guard.

When all four hold, `yOffset = (Up ? -Y : Y)` and `sizingContainer.Height = 1 - yOffset / DrawHeight`.
`Height` is a **relative** value here (`RelativeSizeAxes = Axes.Both`), so the pixel height is
`sizingContainerHeight = L * (1 - yOffset / L) = L - yOffset`. `Y` is the hold note's own
`Position.Y`, i.e. the algorithm's position of the head's time relative to now: for Down it is `0` at
the head's time, negative while the note is still approaching the hit line, and **positive** once the
note has passed it — hence "how far past the hit target this hold note is" is `Y` itself on Down.

Two behavioural asymmetries that follow literally from the code (not from any documented intent):

* `else sizingContainer.Height = 1;` only covers `Time.Current < HitObject.StartTime`. If the inner
  `if` stops being satisfied *after* having shrunk (head missed at the last moment, hold dropped, or
  `DrawHeight` collapsing to 0), **the sizing container keeps its last value; nothing resets it to 1.**
  It restarts at 1 for the next use only via `OnApply` (`DrawableHoldNote.cs:135-140`):
  `sizingContainer.Size = Vector2.One;`.
* Because the outer `if` is on `Time.Current`, the shrink is driven by *time*, not by the
  press/release edges; holding state only gates it through `DroppedHoldAfter`.

### 3.4 What region the mask clips (DOWNSCROLL, derived)

Working through `ChildSize`/`ChildOffset` for Down, with `yOffset = Y` (so
`H_sizing = L − yOffset`) and using the hold's local space (local 0 = the tail's time position,
local L = the head's time position — §2.4):

| container | its rect in the hold's local space |
|---|---|
| `sizingContainer` (`Anchor = Origin = TopLeft`, `RelativeSizeAxes = Axes.Both`, `Height = 1 - yOffset/L`) | `y ∈ [0, L − yOffset]` |
| its children (padding `Top = −Tail.Height`) | `ChildSize.Y = (L − yOffset) + Tail.Height`, `ChildOffset.Y = −Tail.Height` |
| `maskingContainer` (`RelativeSizeAxes = Axes.Both`) | `y ∈ [−Tail.Height, L − yOffset]` |
| its child (`maskingContainer.Padding.Bottom = Head.Height/2`) | `ChildSize.Y = (L − yOffset + Tail.Height) − H_head/2`, offset `Y = 0` |
| `maskedContents` (the **clip rectangle**, `Masking = true`) | `y ∈ [−Tail.Height, L − yOffset − H_head/2]` |
| `headContainer` (also padded — `RelativeSizeAxes = Axes.Both`) | `y ∈ [−Tail.Height, L − yOffset + Tail.Height]`; its **bottom edge is still `L − yOffset`** |

Converting the clip rectangle into screen terms (`local 0 ≡ y(tail time)`, `local L ≡ y(head time)`,
and both notes' leading edges tracking their positions):

* clip **top** = `y(tail time) − H_tail` = exactly the top edge of the tail sprite's rectangle
  (the tail's rect is `[−H_tail, 0]` locally, because the tail's bottom edge is on its position);
* clip **bottom** = local `L − yOffset − H_head/2`, i.e. container-space
  `y(tail time) + L − yOffset − H_head/2`. With `y(head time) = y(tail time) + L` that is
  `y(head time) − yOffset − H_head/2`, and since on Down `y(head time) = Y_hold + H_c` with
  `Y_hold = yOffset` (`Y_hold` is the hold note's own `Position.Y`, §3.3), the expression reduces to
  **`H_c − H_head/2`** — `H_c` being the container's own height, i.e. the judgement line (§3.6).
  So the clip's bottom edge is a **constant `H_head/2` above the judgement line, independent of time
  and of where the note is**. The head's own bottom edge is pinned at that same judgement line while
  the shrink is active, which is why *"half-way under the head"* and *"the body's bottom edge"*
  coincide exactly.

The mask therefore covers, in screen terms: **from the top edge of the tail sprite to half a
head-height above the judgement line**. At rest (`yOffset = 0`, i.e. not holding) that is the region
`[y(tail time) − H_tail, y(head time) − H_head/2]`, which is a strict superset of the body's own
extent `[y(tail time) − H_tail/2, y(head time) − H_head/2]` — so **the mask is a no-op until the note
is held**, and it starts cutting exactly when the body's bottom edge would otherwise cross the head's
centre (i.e. immediately, because the padding places the mask's bottom edge on the body's bottom edge).

### 3.5 What it clips: body and tail — never the head

* The mask is `maskedContents`, and its only children are the **body proxy** and the **tail proxy**
  (§1.1, §1.3). It clips those two, and only those.
* The **head is outside the mask** — `headContainer` is a sibling of `maskingContainer` inside
  `sizingContainer`, and is added *after* it, so the head also paints over the masked contents.
  Nothing else in the chain masks (§1.5). This is why `sizingContainer.Height` can move the head
  without ever cutting it: the comment at `DrawableHoldNote.cs:257-259` says so ("The head note will
  move along with the new 'head position' in the container"), and `DrawableHoldNoteHead.cs:56-65`
  adds the complementary rule:

```csharp
        protected override void UpdateHitStateTransforms(ArmedState state)
        {
            // suppress the base call explicitly.
            // the hold note head should never change its visual state on its own due to the "freezing" mechanic
            // (when hit, it remains visible in place at the judgement line; when dropped, it will scroll past the line).
            // it will be hidden along with its parenting hold note when required.

            // Set `LifetimeEnd` explicitly to a non-`double.MaxValue` because otherwise this DHO is automatically expired.
            LifetimeEnd = double.PositiveInfinity;
        }
```

* Consequence for the **tail**: while the hold is held, the clip's bottom edge stays at
  `judgement line − H_head/2` while the tail keeps descending, so the tail is progressively clipped
  from the bottom as it arrives at the line. Nothing in the source calls this out; it follows from
  the geometry.

### 3.6 Where the judgement line is, and why `H_c` (the container height) matters

* `Stage.HIT_TARGET_POSITION = 110` (`Stage.cs:38`).
* `HitPositionPaddedContainer.UpdateHitPosition` (`HitPositionPaddedContainer.cs:33-42`):

```csharp
            Padding = Direction.Value == ScrollingDirection.Up
                ? new MarginPadding { Top = hitPosition }
                : new MarginPadding { Bottom = hitPosition };
```

so on Down the hit-object area (and the hit target sprite, `ColumnHitObjectArea.cs:46-54`,
`hitTarget.Anchor = hitTarget.Origin = Anchor.BottomLeft`) is the region *above* the line, and the
line is the **bottom edge** of the `ScrollingHitObjectContainer`. The key area confirms the same
reading from the other side: `DefaultKeyArea` is `Height = Stage.HIT_TARGET_POSITION` with
`directionContainer.Anchor = directionContainer.Origin = Anchor.BottomLeft;` on the Down branch
(`DefaultKeyArea.cs:49`, `:108`), i.e. the bottom `110 px` of the column.
* `ScrollingHitObjectContainer.ScreenSpacePositionAtTime` (`:115-122`) is consistent with that
  (`localPosition += axisInverted ? scrollLength : 0;`), which is why the container's bottom edge is
  "now" and its top edge is the future.

---

## 4. Head and tail placement

### 4.1 Anchor / Origin — and the dead assignment

Both classes set up their anchors in their constructors:

`DrawableHoldNoteHead.cs:31-36`:

```csharp
        public DrawableHoldNoteHead(HeadNote headNote)
            : base(headNote)
        {
            Anchor = Anchor.TopCentre;
            Origin = Anchor.TopCentre;
        }
```

`DrawableHoldNoteTail.cs:33-38` is identical.

**Those two constructor assignments are overwritten before the first draw.** Both drawables inherit
`DrawableManiaHitObject`, which binds the direction and re-applies the anchors:

`DrawableManiaHitObject.cs:61-71`:

```csharp
        protected override void LoadComplete()
        {
            base.LoadComplete();

            Direction.BindValueChanged(OnDirectionChanged, true);
        }

        protected virtual void OnDirectionChanged(ValueChangedEvent<ScrollingDirection> e)
        {
            Anchor = Origin = e.NewValue == ScrollingDirection.Up ? Anchor.TopCentre : Anchor.BottomCentre;
        }
```

Neither `DrawableHoldNoteHead` nor `DrawableHoldNoteTail` overrides `OnDirectionChanged`
(`DrawableNote` only overrides it to move its *inner* `headPiece` — `DrawableNote.cs:78-83`), and
`BindValueChanged(..., true)` fires immediately with the current value during `LoadComplete`, which
runs before the first `Update()`. So in practice:

| direction | head/tail `Anchor`/`Origin` |
|---|---|
| `Up` | `TopCentre` (constructor value coincidentally the same) |
| `Down` (**default**) | `BottomCentre` |

For Down, **[framework]** the head/tail's bottom edge lands at `Position.Y + Parent.ChildSize.Y`.
This is the anchor arithmetic the whole body/mask computation is built on: it is why `y(time)` means
"the note's bottom edge is on its time position".

### 4.2 Where nested hit objects get their Y

`ScrollingHitObjectContainer.cs:271-289`:

```csharp
            foreach (var obj in hitObject.NestedHitObjects)
            {
                updateLayoutRecursive(obj, parentHitObjectStartTime);

                // Nested hitobjects don't need to scroll, but they do need accurate positions and start lifetime
                updatePosition(obj, hitObject.HitObject.StartTime, parentHitObjectStartTime);
                setComputedLifetime(obj.Entry);
            }
```

```csharp
        private void updatePosition(DrawableHitObject hitObject, double currentTime, double? parentHitObjectStartTime = null)
        {
            float position = PositionAtTime(hitObject.HitObject.StartTime, currentTime, parentHitObjectStartTime);

            if (scrollingAxis == Direction.Horizontal)
                hitObject.X = position;
            else
                hitObject.Y = position;
        }
```

(`ScrollingHitObjectContainer.cs:281-289`.)

Two things fall out of this, and both are easy to misread:

1. `currentTime` for nested objects is **the parent's start time**, not the clock — nested hit objects
   are positioned *once, relative to their parent*, and the parent's own `Y` carries the scrolling.
2. Therefore, for a hold note:
   * the **head** (whose `StartTime == HoldNote.StartTime`, `HoldNote.cs:104-109`) gets `Y = 0`;
   * the **tail** (`Tail.StartTime = EndTime`, `HoldNote.cs:29-39` / `:111-116`) gets
     `Y = PositionAtTime(EndTime, StartTime)`, which for Down (`axisInverted`, see
     `ScrollingHitObjectContainer.cs:39`) is **`−L`** and for Up is **`+L`**. As shown in §2.6 this is
     exactly minus/plus the hold's `DrawHeight` for every algorithm.
   * the invisible `HoldNoteBody` (`StartTime == StartTime`) gets `Y = 0`; being `IHasDuration` it also
     gets `Height = L` — irrelevant visually, it draws nothing.

### 4.3 Where they end up (DOWNSCROLL)

Combining §4.1 (bottom edge at `Position.Y + parent.ChildSize.Y`) with §4.2 and §3.4's padding maths:

| | parent container | `Y` | parent `ChildSize.Y` | ⇒ bottom edge | ⇒ rect |
|---|---|---|---|---|---|
| head | `headContainer` (inside `sizingContainer`; padded, so bottom edge = `H_sizing`) | `0` | `H_sizing + H_tail` at offset `−H_tail` | `L − yOffset` | `[L − yOffset − H_head, L − yOffset]` |
| tail | `tailContainer` (direct child of the hold note, no padding) | `−L` | `L` | `0` | `[−H_tail, 0]` |

In screen terms, with the hold's own rect `[y(tail time), y(head time)]`:

* the **tail's bottom edge sits on `y(tail time)`**, its rectangle occupying
  `[y(tail time) − H_tail, y(tail time)]` — i.e. it pokes `H_tail` **above** the hold note's own
  rectangle, which is why `sizingContainer.Padding` reaches under it (§3.2);
* the **head's bottom edge sits on `y(head time)`** when the hold is at rest; while the note is held
  (i.e. whenever the §3.3 condition holds) the *sizing container* pulls `headContainer` up by
  `yOffset`, so the head's bottom edge is pinned to the **judgement line** and only the tail side
  keeps moving. (`local(head bottom) = H_sizing = L − yOffset`, and the hold's rectangle top is at
  `rectTop = y(head time) − L`, so the head's bottom edge in container space is
  `rectTop + H_sizing = y(head time) − yOffset`, which equals `H_c` — the judgement line — because on
  Down `y(head time) = Y_hold + H_c` and `yOffset = Y_hold`. This matches the `DrawableHoldNoteHead`
  comment: "it remains visible in place at the judgement line; when dropped, it will scroll past the
  line".)
* for `Up` everything mirrors: head/tail `Anchor = Origin = TopCentre`, `sizingContainer =
  BottomLeft`, head at `local 0`, tail at `local L`.

### 4.4 Inside or outside the mask

* **head — outside.** It lives in `headContainer`, a sibling of `maskingContainer`
  (`DrawableHoldNote.cs:102`) and is never a descendant of the `Masking = true` `maskedContents`.
* **tail — inside.** Its rendering goes through `tailContainer.CreateProxy()` placed in
  `maskedContents` (`DrawableHoldNote.cs:123-124`), and the original does not render itself (§1.3).

### 4.5 Head/tail height

* No legacy/argon mania piece available → `DefaultNotePiece`: `NOTE_HEIGHT = 12`,
  `CornerRadius = 5`, `Masking = true`, a full-size `Box` plus a `colouredBox` of
  `Height = NOTE_HEIGHT / 2` with `Alpha = 0.1f` anchored to the top or bottom by direction
  (`DefaultNotePiece.cs:20-84`).
* Legacy piece → `LegacyNotePiece`, whose height is the layout height of its scaled sprite —
  see §5/§6 for the sprite and §4.6 below.
* The head/tail drawable itself is `RelativeSizeAxes = Axes.X` (`DrawableManiaHitObject.cs:49`) plus
  `AutoSizeAxes = Axes.Y` (`DrawableNote.cs:49`), with a single `headPiece` child
  (`DrawableNote.cs:57-61`).

### 4.6 Legacy head/tail sprite height (feeds back into §2)

`LegacyNotePiece.cs:27-31` and `:50-66`:

```csharp
        public LegacyNotePiece()
        {
            RelativeSizeAxes = Axes.X;
            AutoSizeAxes = Axes.Y;
        }
```

```csharp
            if (texture != null)
            {
                float noteHeight = widthForNoteHeightScale ?? DrawWidth;
                noteAnimation.Scale = Vector2.Divide(new Vector2(DrawWidth, noteHeight), texture.DisplayWidth);
            }
```

`noteAnimation` is a `Sprite` (or a `TextureAnimation`), created without an explicit size, and
**[framework]** `Sprite.Texture`'s setter does `if (Size == Vector2.Zero) Size = new Vector2(texture?.DisplayWidth ?? 0, texture?.DisplayHeight ?? 0);`
— so the sprite's base size is the texture's display size, and the assignment above makes the drawn
size `(DrawWidth, texHeight * noteHeight / texWidth)`. With
`widthForNoteHeightScale = skin.GetConfig<...WidthForNoteHeightScale>()` (`LegacyNotePiece.cs:36`):

* `WidthForNoteHeightScale` unset → `noteHeight = DrawWidth` → proportional scaling, drawn height
  `= DrawWidth * texHeight / texWidth`;
* `WidthForNoteHeightScale` set → drawn height `= widthForNoteHeightScale * texHeight / texWidth`.

This is the value that shows up as `Head.Height` / `Tail.Height` in §2 and §3 — i.e. **on legacy skins
the body inset changes with the note texture's aspect ratio and the skin's
`WidthForNoteHeightScale`.** (Argon has its own pieces: `ArgonHoldNoteHeadPiece`,
`ArgonHoldNoteTailPiece`, `ArgonNotePiece`.)

---

## 5. `LegacyBodyPiece`

`osu.Game.Rulesets.Mania/Skinning/Legacy/LegacyBodyPiece.cs`. Class declaration and constructor
(`:22-38`):

```csharp
    public partial class LegacyBodyPiece : LegacyManiaColumnElement
    {
        private DrawableHoldNote holdNote = null!;

        private readonly IBindable<ScrollingDirection> direction = new Bindable<ScrollingDirection>();
        private readonly IBindable<bool> isHitting = new Bindable<bool>();
        private readonly IBindable<double?> missingStartTime = new Bindable<double?>();

        private Drawable? bodySprite;
        private Drawable? lightContainer;
        private Drawable? light;
        private LegacyManiaSkinConfiguration.LegacyNoteBodyStyle? bodyStyle;

        public LegacyBodyPiece()
        {
            RelativeSizeAxes = Axes.Both;
        }
```

### 5.1 Loading: image, wrap mode, animation frame length, light

`LegacyBodyPiece.cs:40-98` (key lines):

```csharp
            string imageName = GetColumnSkinConfig<string>(skin, LegacyManiaSkinConfigurationLookups.HoldNoteBodyImage)?.Value
                               ?? $"mania-note{FallbackColumnIndex}L";

            string lightImage = GetColumnSkinConfig<string>(skin, LegacyManiaSkinConfigurationLookups.HoldNoteLightImage)?.Value
                                ?? "lightingL";

            float lightScale = GetColumnSkinConfig<float>(skin, LegacyManiaSkinConfigurationLookups.HoldNoteLightScale)?.Value
                               ?? 1;

            // Create a temporary animation to retrieve the number of frames, in an effort to calculate the intended frame length.
            // This animation is discarded and re-queried with the appropriate frame length afterwards.
            var tmp = skin.GetAnimation(lightImage, true, false);
            double frameLength = 0;
            if (tmp is IFramedAnimation tmpAnimation && tmpAnimation.FrameCount > 0)
                frameLength = Math.Max(1000 / 60.0, 170.0 / tmpAnimation.FrameCount);
```

```csharp
            bodyStyle = skin.GetConfig<ManiaSkinConfigurationLookup, LegacyManiaSkinConfiguration.LegacyNoteBodyStyle>(new ManiaSkinConfigurationLookup(LegacyManiaSkinConfigurationLookups.NoteBodyStyle))?.Value;

            var wrapMode = bodyStyle == LegacyManiaSkinConfiguration.LegacyNoteBodyStyle.Stretch ? WrapMode.ClampToEdge : WrapMode.Repeat;

            direction.BindTo(scrollingInfo.Direction);
            isHitting.BindTo(holdNote.IsHolding);
            missingStartTime.BindTo(holdNote.MissingStartTime);

            bodySprite = skin.GetAnimation(imageName, wrapMode, wrapMode, true, true, frameLength: 30)?.With(d =>
            {
                if (d is TextureAnimation animation)
                    animation.IsPlaying = false;

                d.Anchor = Anchor.TopCentre;
                d.RelativeSizeAxes = Axes.Both;
                d.Size = Vector2.One;
                // Todo: Wrap?
            });

            if (bodySprite != null)
                InternalChild = bodySprite;
```

Notes that matter for a reimplementation:

* `bodyStyle` is **nullable**, and the default when a skin does not declare `NoteBodyStyle` is `null`
  (`LegacyManiaSkinConfiguration.cs:49` — `public LegacyNoteBodyStyle? NoteBodyStyle;`). A `switch`
  over a nullable enum matches no case label for `null` — not even `Stretch` — so an undeclared
  `NoteBodyStyle` falls to `default:` in `Update()` (§5.3) and to `WrapMode.Repeat` here.
* `LegacyManiaSkinConfiguration.LegacyNoteBodyStyle` (`LegacyManiaSkinConfiguration.cs:93-103`) is
  `Stretch = 0`, `RepeatTop = 2`, `RepeatBottom = 3`, `RepeatTopAndBottom = 4` — with `Repeat = 1`
  deliberately commented out. **lazer implements all three "repeat" styles with the same code path**
  (the `default:` branch), which the file itself admits.
* The wrap mode is applied to both texture axes.
* The body sprite is anchored `TopCentre` here and `RelativeSizeAxes = Axes.Both; Size = Vector2.One`
  — i.e. it fills the `SkinnableDrawable` that carries the body rect of §2.
* Frame length for the *body* animation is hard-coded `frameLength: 30`, while the *light* animation
  gets a frame count derived from the sheet.

### 5.2 `Update()` — the `Stretch` case

`LegacyBodyPiece.cs:182-198`:

```csharp
        protected override void Update()
        {
            base.Update();

            if (!isHitting.Value)
                (bodySprite as TextureAnimation)?.GotoFrame(0);

            int scaleDirection = (direction.Value == ScrollingDirection.Down ? 1 : -1);

            // here we go...
            switch (bodyStyle)
            {
                case LegacyManiaSkinConfiguration.LegacyNoteBodyStyle.Stretch:
                    // this is how lazer works by default. nothing required.
                    if (bodySprite != null)
                        bodySprite.Scale = new Vector2(1, scaleDirection);
                    break;
```

So on `Stretch`: `Scale = (1, 1)` for Down (no change) and `(1, −1)` for Up (vertical flip); the
`FillMode` is left at the framework default (Stretch), i.e. the texture is stretched over the body
rect exactly as the lazer-default body piece behaves. The comment states this explicitly:
*"this is how lazer works by default. nothing required."*

### 5.3 `Update()` — the `default:` case

`LegacyBodyPiece.cs:200-216`:

```csharp
                default:
                    // this is where things get a bit messed up.
                    // honestly there's three modes to handle here but they seem really pointless?
                    // let's wait to see if anyone actually uses them in skins.
                    if (bodySprite != null)
                    {
                        var sprite = bodySprite as Sprite ?? bodySprite.ChildrenOfType<Sprite>().Single();

                        bodySprite.FillMode = FillMode.Stretch;
                        // i dunno this looks about right??
                        // the guard against zero draw height is intended for zero-length hold notes. yes, such cases have been spotted in the wild.
                        if (sprite.DrawHeight > 0)
                            bodySprite.Scale = new Vector2(1, scaleDirection * MathF.Max(1, 32800 / sprite.DrawHeight));
                    }

                    break;
```

Facts to pin down literally:

* This branch covers `null` (no `NoteBodyStyle` in `skin.ini`), `RepeatTop`, `RepeatBottom`,
  `RepeatTopAndBottom` — all four behave identically.
* `sprite` is the body sprite itself when it is a `Sprite`, otherwise its single inner `Sprite`
  (`.Single()` — **throws** if the animation has zero or more than one `Sprite` child).
* `bodySprite.FillMode = FillMode.Stretch;` is set explicitly on the outer drawable (every update), so
  this branch never depends on the framework default. For a `TextureAnimation` the visible frame is a
  separate inner sprite created without an explicit `FillMode`
  (**[framework]** `TextureAnimation.CreateContent() => textureHolder = new Sprite { RelativeSizeAxes = Axes.Both, Anchor = Anchor.Centre, Origin = Anchor.Centre }`),
  i.e. it uses `Drawable.FillMode`'s default.
* `32800 / sprite.DrawHeight` is float division (32800 is an `int` literal promoted to `float`), not
  integer division — no truncation.
* `MathF.Max(1, …)` clamps the **up**-scale only: the sprite is never scaled *down* below 1.
* The sign comes from `scaleDirection` (Down `+1`, Up `−1`), so on Down the sprite is stretched
  downward from its `Origin`; `Origin`/`Anchor` for the body sprite are set in
  `onDirectionChanged` (`:141-165`): Up → `Origin = Anchor.TopCentre; Anchor = Anchor.BottomCentre; // needs to be flipped due to scale flip in Update.`;
  Down → `Origin = Anchor.TopCentre; Anchor = Anchor.TopCentre;`. **On Down the sprite's top edge is
  pinned to the top of the body rect**, so all of the extra height it gains extends downwards.
* **The zero-draw-height guard**: `if (sprite.DrawHeight > 0)`. Its stated purpose is in the comment —
  zero-length hold notes — i.e. `sprite.DrawHeight` is read as "the height this sprite currently
  occupies", which for these relatively-sized sprites is the **body rect height** and is therefore
  `0` for a zero-length hold (§7) — that is also the only reading under which the comment is true.
  With `sprite.DrawHeight == 0` the scale is left untouched (avoiding `32800/0 = ∞`).

### 5.4 What `32800` does visually

Literal consequence of the arithmetic. Let `h = sprite.DrawHeight` (the body rect height, which for
the body sprite equals `bodyPiece.Height` of §2) and let `k = max(1, 32800 / h)`:

* the sprite's *own* draw size is the body rect, so with `FillMode.Stretch` the texture is mapped over
  `h` px of local space;
* the drawable's `Scale.Y` is then `k`, so the texture ends up mapped over `h * k` screen pixels;
* therefore: **if `h < 32800`, the body texture is drawn exactly 32800 screen pixels tall, pinned to
  the top of the body rect** (Down); if `h ≥ 32800`, nothing changes (`k = 1`).

Reading that as intent: the constant turns "the texture is squeezed into the hold's length" into "the
texture occupies a fixed ≈32800 px strip anchored at the body's top", with the mask of §3 deciding how
much of it is visible. The number is consistent with the legacy long-note body textures being 32800 px
tall — under which the arithmetic is exactly *1 texture pixel = 1 screen pixel*, i.e. no scaling at
all, which also explains why the `Stretch` body style (which leaves the scale at 1 and uses
`ClampToEdge`) is described as *"this is how lazer works by default"*.

On the `WrapMode.Repeat` choice of §5.1: with `FillMode.Stretch` the texture rectangle is the full
`(0,0,1,1)` mapped over the sprite's own draw size (**[framework]** `Sprite.DrawTextureRectangle` =
`TextureRectangle`, scaled by `DrawSize` when `TextureRelativeSizeAxes != Axes.None`), so sampling
stays inside `[0,1]` and the texture's wrap mode has no effect on what is drawn — it is passed to the
skin's texture lookup, which can still affect how the texture is created/packed. A "repeat the body
texture" reading only becomes visible if the sprite is drawn with a non-Stretch `FillMode`, which this
branch explicitly rules out. See the ledger (§9.13).

> **Flagged as inference, not source.** The 32800 value is a bare literal in this file; nothing in the
> checkout states what it is the height *of*. The mania long-note body textures come from the
> `ppy.osu.Game.Resources` package, which is not in the checkout and not in the local NuGet cache, so
> their pixel dimensions could not be verified here. The *arithmetic* claim above ("the texture is
> drawn 32800 px tall when the body rect is shorter than that") is a direct consequence of the quoted
> code and needs no assumption; the *interpretation* ("the textures are 32800 px tall, so this is
> 1:1") does. The file's own comments ("this is where things get a bit messed up", "i dunno this looks
> about right??") indicate the author considered this branch an approximation rather than a
> specification.

### 5.5 The `isHitting` animation behaviour

`LegacyBodyPiece.cs:100-139`:

```csharp
        protected override void LoadComplete()
        {
            base.LoadComplete();

            direction.BindValueChanged(onDirectionChanged, true);
            isHitting.BindValueChanged(onIsHittingChanged, true);
            missingStartTime.BindValueChanged(onMissingStartTimeChanged, true);

            holdNote.ApplyCustomUpdateState += onApplyCustomUpdateState;
        }

        private void onIsHittingChanged(ValueChangedEvent<bool> isHitting)
        {
            if (bodySprite is TextureAnimation bodyAnimation)
                bodyAnimation.IsPlaying = isHitting.NewValue;

            if (lightContainer == null)
                return;

            if (isHitting.NewValue)
            {
                // Clear the fade out and, more importantly, the removal.
                lightContainer.ClearTransforms();

                // Only add the container if the removal has taken place.
                if (lightContainer.Parent == null)
                    Column.TopLevelContainer.Add(lightContainer);

                // The light must be seeked only after being loaded, otherwise a nullref occurs (https://github.com/ppy/osu-framework/issues/3847).
                if (light is TextureAnimation lightAnimation)
                    lightAnimation.GotoFrame(0);

                lightContainer.FadeIn(80);
            }
            else
            {
                lightContainer.FadeOut(120)
                              .OnComplete(d => Column.TopLevelContainer.Remove(d, false));
            }
        }
```

plus the coupling of the animation to the hold state at the top of `Update()`:
`if (!isHitting.Value) (bodySprite as TextureAnimation)?.GotoFrame(0);` (`:186-187`).

So, for the body *animation*: it **plays while the hold note is being held and pauses + rewinds to
frame 0 otherwise** (`IsPlaying = isHitting`, and `GotoFrame(0)` every frame while not holding — the
latter is what makes a released body return to its first frame even if it was mid-play). Note it is
created with `animation.IsPlaying = false` at load (§5.1), so a body animation never plays on its own.
The light (`lightingL` by default, additive blending, `Origin = Anchor.Centre`, scaled by
`HoldNoteLightScale`) is a child of a `HitTargetInsetContainer` (`Alpha = 0` initially) that is
**inserted into the column's `TopLevelContainer` only while hitting** and *removed* from the tree
`120 ms` after release. This out-of-tree insertion is why `DrawableHoldNote.OnKilled` has to flush
the holding state (`DrawableHoldNote.cs:208-219`):

```csharp
            // flush the final state of holding on kill.
            // this matters because some skin implementations like legacy skin
            // insert drawables in the hierarchy that are not a child of this DHO
            // (see `LegacyBodyPiece` and related machinations with `lightContainer` being added at column level)
            isHolding.Value = Result.IsHolding(Time.Current);
            missingStartTime.Value = null;
            (bodyPiece.Drawable as IHoldNoteBody)?.Recycle();
```

`HitTargetInsetContainer` (`HitTargetInsetContainer.cs:23-44`) pads its content by the hit position
(top for Up, bottom for Down) — i.e. the LN light is positioned relative to the judgement line, "where
the centre of the judgement line crosses the centre of a lane".

### 5.6 `MissingStartTime` dimming

`LegacyBodyPiece.cs:167-180`:

```csharp
        private void onMissingStartTimeChanged(ValueChangedEvent<double?> startTime)
            => applyMissingDim();

        private void onApplyCustomUpdateState(DrawableHitObject obj, ArmedState state)
            => applyMissingDim();

        private void applyMissingDim()
        {
            if (missingStartTime.Value == null)
                return;

            using (BeginAbsoluteSequence(missingStartTime.Value.Value))
                this.FadeColour(Colour4.DarkGray, 60);
        }
```

The bind source is the hold note (`missingStartTime.BindTo(holdNote.MissingStartTime)`, §5.1), which
is populated in `DrawableHoldNote.Update()` (`:225-230`) as the first of:

```csharp
            if (Head.Judged && !Head.IsHit)
                missingStartTime.Value ??= Head.Result.TimeAbsolute;
            if (Body.HasHoldBreak)
                missingStartTime.Value ??= Body.Result.TimeAbsolute;
            if (Tail.Judged && !Tail.IsHit)
                missingStartTime.Value ??= Tail.Result.TimeAbsolute;
```

Effect: as soon as any of "missed head / broke the body / missed the tail" happens, the whole body
piece fades to `Colour4.DarkGray` over 60 ms, scheduled **from that absolute time** (so it replays
correctly on rewind). It is a colour fade on the piece, not a texture swap. `Dispose` unsubscribes
(`:219-228`) and expires the light container.

---

## 6. `LegacyHoldNoteTailPiece`

`osu.Game.Rulesets.Mania/Skinning/Legacy/LegacyHoldNoteTailPiece.cs`.

### 6.1 Direction inversion

`:47-53`:

```csharp
        protected override void OnDirectionChanged(ValueChangedEvent<ScrollingDirection> direction)
        {
            // Invert the direction
            base.OnDirectionChanged(direction.NewValue == ScrollingDirection.Up
                ? new ValueChangedEvent<ScrollingDirection>(ScrollingDirection.Down, ScrollingDirection.Down)
                : new ValueChangedEvent<ScrollingDirection>(ScrollingDirection.Up, ScrollingDirection.Up));
        }
```

The base implementation (`LegacyNotePiece.cs:68-80`) is what the flip acts on:

```csharp
        protected virtual void OnDirectionChanged(ValueChangedEvent<ScrollingDirection> direction)
        {
            if (direction.NewValue == ScrollingDirection.Up)
            {
                directionContainer.Anchor = Anchor.TopCentre;
                directionContainer.Scale = new Vector2(1, -1);
            }
            else
            {
                directionContainer.Anchor = Anchor.BottomCentre;
                directionContainer.Scale = Vector2.One;
            }
        }
```

Because the tail feeds the **opposite** direction value in, the tail sprite is drawn vertically
mirrored relative to the head: on Down scroll the head is unflipped (`Scale = Vector2.One`,
`Anchor = BottomCentre`) and the **tail is flipped (`Scale = (1, −1)`, `Anchor = TopCentre`)** — which
matches the wiki's *"when used for the tail part, this element is flipped by default"* and stable's
`NoteFlipWhenUpsideDownT`. **(Note: the tail drawable's own `Anchor`/`Origin` is still the
direction-derived `BottomCentre` on Down — §4.1. Only the *inner* `directionContainer` of the skin
piece is inverted, and the piece's scaling/anchoring is what changes.)**

**The flip is unconditional in lazer, and the skin's opt-out is not implemented.** The only occurrence
of `NoteFlipWhenUpsideDown*` in the whole checkout is the decoder, which stores it without any consumer
(`osu.Game/Skinning/LegacyManiaSkinDecoder.cs:187-190`):

```csharp
                    case string when pair.Key.StartsWith(@"KeyFlipWhenUpsideDown", StringComparison.Ordinal):
                    case string when pair.Key.StartsWith(@"NoteFlipWhenUpsideDown", StringComparison.Ordinal):
                        currentConfig.FlipSettings[pair.Key] = pair.Value;
                        break;
```

and `FlipSettings` sits inside the config's *"Unimplemented properties, at this time present primarily
for encode-decode stability"* region (`LegacyManiaSkinConfiguration.cs:51-65`, property at `:62`).
So lazer mirrors the tail sprite regardless of `NoteFlipWhenUpsideDownT = 0`. (The same is true of the
`UpsideDown` setting used elsewhere in this file's region — not modelled here.)

### 6.2 Animation fallback chain

`:55-61`:

```csharp
        protected override Drawable? GetAnimation(ISkinSource skin)
        {
            // TODO: Should fallback to the head from default legacy skin instead of note.
            return GetAnimationFromLookup(skin, LegacyManiaSkinConfigurationLookups.HoldNoteTailImage)
                   ?? GetAnimationFromLookup(skin, LegacyManiaSkinConfigurationLookups.HoldNoteHeadImage)
                   ?? GetAnimationFromLookup(skin, LegacyManiaSkinConfigurationLookups.NoteImage);
        }
```

Three levels: `HoldNoteTailImage` → `HoldNoteHeadImage` → `NoteImage`. **That chain never returns
`null`** unless the note texture itself is missing, because each level falls back to a *default
filename* (`LegacyNotePiece.cs:84-103`):

```csharp
            string suffix = string.Empty;

            switch (lookup)
            {
                case LegacyManiaSkinConfigurationLookups.HoldNoteHeadImage:
                    suffix = "H";
                    break;

                case LegacyManiaSkinConfigurationLookups.HoldNoteTailImage:
                    suffix = "T";
                    break;
            }

            string noteImage = GetColumnSkinConfig<string>(skin, lookup)?.Value
                               ?? $"mania-note{FallbackColumnIndex}{suffix}";

            return skin.GetAnimation(noteImage, WrapMode.ClampToEdge, WrapMode.ClampToEdge, true, true);
```

So level 1 tries `mania-noteXL.png` (`T`), level 2 `mania-noteXH.png`, level 3 `mania-noteX.png`,
with `X` = the column's fallback index (`LegacyManiaColumnElement.cs:30-42`: `"S"` for a special
column, else `"1"`/`"2"` by distance to the column-block edge). Note the wrap modes here are
`ClampToEdge` on both axes, and no `frameLength` is passed for note/head/tail pieces.

The head's chain is shorter (`LegacyHoldNoteHeadPiece.cs:46-51`):

```csharp
        protected override Drawable? GetAnimation(ISkinSource skin)
        {
            // TODO: Should fallback to the head from default legacy skin instead of note.
            return GetAnimationFromLookup(skin, LegacyManiaSkinConfigurationLookups.HoldNoteHeadImage)
                   ?? GetAnimationFromLookup(skin, LegacyManiaSkinConfigurationLookups.NoteImage);
        }
```

### 6.3 `MissingStartTime` dimming

`:38-45` — byte-for-byte the same `applyMissingDim` as the body (§5.6), but bound to the *tail's*
bindable (`:26`):

```csharp
            missingStartTime.BindTo(((DrawableHoldNoteTail)drawableObject).MissingStartTime);
```

and `DrawableHoldNoteTail` forwards the hold note's own bindable to it
(`DrawableHoldNoteTail.cs:40-46`, `:22`: `public readonly IBindable<double?> MissingStartTime = new Bindable<double?>();`
+ `MissingStartTime.BindTo(parentHold.MissingStartTime)`). Net effect: **head, tail and body all
independently schedule the same 60 ms `FadeColour(Colour4.DarkGray)` from the same absolute
`MissingStartTime`**, and each also re-checks on `ApplyCustomUpdateState` (`:34-35`).

---

## 7. Short holds: when the body is zero or negative

### 7.1 Derivation

From §2.1:

```
Height_body = DrawHeight − Head.Height/2 + Tail.Height/2
            = L − H_head/2 + H_tail/2
```

There is **no clamp of any kind** on this expression — no `Math.Max(0, …)`, no minimum length.

```
Height_body ≤ 0
  ⇔  L − H_head/2 + H_tail/2 ≤ 0
  ⇔  L ≤ (H_head − H_tail)/2
```

Equivalently, multiplying by 2: **`2·DrawHeight ≤ Head.Height − Tail.Height`.**

### 7.2 What that means in practice

* **Whenever `H_head == H_tail`** — which covers the fallback pieces (`DefaultNotePiece`, 12 px for
  head and tail alike, `DefaultNotePiece.cs:22`), Argon (`ArgonNotePiece.NOTE_HEIGHT = 42`, shared by
  `ArgonHoldNoteHeadPiece` and `ArgonHoldNoteTailPiece` — `ArgonNotePiece.cs:21`,
  `ArgonHoldNoteTailPiece.cs:34`) — the condition becomes `L ≤ 0`. **Any hold with a positive scroll
  length then has a body of exactly `L` px** — the body is never shortened, and there is no
  "minimum LN length" in this code path. A zero-length hold (`StartTime == EndTime ⇒ L = 0`) gives
  `Height_body = 0`.
* **Legacy skin** with `HoldNoteHeadImage` and `HoldNoteTailImage` of different heights: the body
  shrinks by the height difference. A **taller head than tail** can make the body vanish for short
  holds (`L ≤ (H_head − H_tail)/2`); a **taller tail than head** makes the body *longer* than the hold
  itself and can never make it vanish by this route.
* The physically relevant case in the wild is `L == 0` (zero-length holds) — the case
  `LegacyBodyPiece`'s comment names: *"the guard against zero draw height is intended for zero-length
  hold notes. yes, such cases have been spotted in the wild."*
* With `Height_body == 0` nothing is clamped: `bodyPiece.Height = 0` (and, on legacy, the sprite-guard
  of §5.3 skips the scale). A *negative* `Height_body` is also passed straight through — including
  for a hold whose `EndTime < StartTime` (the editor refuses to create one —
  `HoldNoteSelectionBlueprint.cs:62-63`: `if (proposedStartTime >= proposedEndTime) return;` — but
  nothing in the drawing path defends against it).

### 7.3 What is still visible when the body degenerates

* The mask, the paddings and the head/tail positions are unaffected by `Height_body` — a zero-height
  body simply means the body's top and bottom edges coincide (both at `y(head time) − H_head/2` when
  `H_head == H_tail`).
* The head and tail are still placed by §4, and the head is still unmasked (§4.4); only the body
  disappears.
* If the head or tail has **no** skin piece at all, `DrawableNote.load`'s fallback is
  `_ => new DefaultNotePiece()` (`DrawableNote.cs:57`), i.e. 12 px — but a skin piece that resolves to
  `Drawable.Empty()` would give `Head.Height = 0`, which shifts the body's bound in §2.4 to exactly
  `y(head time)` and halves the mask's inset. Nothing guards that.

---

## 8. `DefaultBodyPiece` vs `LegacyBodyPiece`

### 8.1 Which one a legacy skin gets — the exact condition

`osu.Game.Rulesets.Mania/Skinning/Legacy/ManiaLegacySkinTransformer.cs:141-168`:

```csharp
                case ManiaSkinComponentLookup maniaComponent:
                    if (!isLegacySkin.Value || !hasKeyTexture.Value)
                        return null;
```

```csharp
                        case ManiaSkinComponents.HoldNoteBody:
                            return new LegacyBodyPiece();
```

with the two predicates defined at `:75-80`:

```csharp
            isLegacySkin = new Lazy<bool>(() => GetConfig<SkinConfiguration.LegacySetting, decimal>(SkinConfiguration.LegacySetting.Version) != null);
            hasKeyTexture = new Lazy<bool>(() =>
            {
                string keyImage = this.GetManiaSkinConfig<string>(LegacyManiaSkinConfigurationLookups.KeyImage, 0)?.Value ?? "mania-key1";
                return this.GetAnimation(keyImage, true, true) != null;
            });
```

So a `LegacyBodyPiece` is handed back **iff** (a) the skin declares a legacy `Version` setting
(`isLegacySkin`), **and** (b) a mania key texture resolves — `mania-key1` unless
`KeyImage` overrides it (`hasKeyTexture`). Both are lazy and evaluated at the lookup.

If either is false the transformer returns `null` for the mania component, and the
`SkinnableDrawable` created in `DrawableHoldNote.load()` falls back to its default factory
(`SkinnableDrawable.cs:76-100`):

```csharp
            var retrieved = skin.GetDrawableComponent(ComponentLookup);

            if (retrieved == null)
            {
                Drawable = CreateDefault(ComponentLookup);
                isDefault = true;
            }
```

— i.e. `_ => new DefaultBodyPiece { RelativeSizeAxes = Axes.Both }` (`DrawableHoldNote.cs:106-109`).
Other transformers can still claim the component: the Argon skin returns `new ArgonHoldBodyPiece()`
for `ManiaSkinComponents.HoldNoteBody` (`ManiaArgonSkinTransformer.cs:94-95`).

One more `SkinnableDrawable` behaviour that affects the *placement* of whichever piece is returned
(`SkinnableDrawable.cs:93-99`):

```csharp
            if (CentreComponent)
            {
                Drawable.Origin = Anchor.Centre;
                Drawable.Anchor = Anchor.Centre;
            }

            InternalChild = Drawable;
```

`CentreComponent` defaults to `true` (`:26`) and is never changed for the hold body, so whichever
piece is returned is **centred inside the `SkinnableDrawable`, whose rect is the body rect of §2** —
the `Anchor`/`Origin` set on `bodyPiece` by `DrawableHoldNote.OnDirectionChanged` belong to the
`SkinnableDrawable` wrapper, not to the piece (which, being full-size, ends up filling the same rect).

### 8.2 `DefaultBodyPiece` shape construction

`osu.Game.Rulesets.Mania/Skinning/Default/DefaultBodyPiece.cs:22-33`:

```csharp
    public partial class DefaultBodyPiece : CompositeDrawable, IHoldNoteBody
    {
        protected readonly Bindable<Color4> AccentColour = new Bindable<Color4>();
        protected readonly IBindable<bool> IsHitting = new Bindable<bool>();

        protected Drawable Background { get; private set; } = null!;
        private Container foregroundContainer = null!;

        public DefaultBodyPiece()
        {
            Blending = BlendingParameters.Additive;
        }
```

`:35-65` — the two children and the accent plumbing:

```csharp
        [BackgroundDependencyLoader(true)]
        private void load(DrawableHitObject? drawableObject)
        {
            InternalChildren = new[]
            {
                Background = new Box { RelativeSizeAxes = Axes.Both },
                foregroundContainer = new Container { RelativeSizeAxes = Axes.Both }
            };

            if (drawableObject != null)
            {
                var holdNote = (DrawableHoldNote)drawableObject;

                AccentColour.BindTo(drawableObject.AccentColour);
                IsHitting.BindTo(holdNote.IsHolding);
            }

            AccentColour.BindValueChanged(onAccentChanged, true);

            Recycle();
        }

        public void Recycle() => foregroundContainer.Child = CreateForeground();

        protected virtual Drawable CreateForeground() => new ForegroundPiece
        {
            AccentColour = { BindTarget = AccentColour },
            IsHitting = { BindTarget = IsHitting }
        };

        private void onAccentChanged(ValueChangedEvent<Color4> accent) => Background.Colour = accent.NewValue.Opacity(0.7f);
```

`:85-122` — the "hole" machinery (verbatim):

```csharp
            [BackgroundDependencyLoader]
            private void load()
            {
                InternalChild = foregroundBuffer = new BufferedContainer(cachedFrameBuffer: true)
                {
                    Blending = BlendingParameters.Additive,
                    RelativeSizeAxes = Axes.Both,
                    Children = new Drawable[]
                    {
                        new Box { RelativeSizeAxes = Axes.Both },
                        subtractionBuffer = new BufferedContainer(cachedFrameBuffer: true)
                        {
                            RelativeSizeAxes = Axes.Both,
                            // This is needed because we're blending with another object
                            BackgroundColour = Color4.White.Opacity(0),
                            // The 'hole' is achieved by subtracting the result of this container with the parent
                            Blending = new BlendingParameters { AlphaEquation = BlendingEquation.ReverseSubtract },
                            Child = subtractionLayer = new CircularContainer
                            {
                                Anchor = Anchor.Centre,
                                Origin = Anchor.Centre,
                                // Height computed in Update
                                Width = 1,
                                Masking = true,
                                Child = new Box
                                {
                                    RelativeSizeAxes = Axes.Both,
                                    Alpha = 0,
                                    AlwaysPresent = true
                                }
                            }
                        }
                    }
                };

                AccentColour.BindValueChanged(onAccentChanged, true);
                IsHitting.BindValueChanged(_ => onAccentChanged(new ValueChangedEvent<Color4>(AccentColour.Value, AccentColour.Value)), true);
            }
```

`:124-163` — colour, hit pulse and the per-size geometry:

```csharp
            private void onAccentChanged(ValueChangedEvent<Color4> accent)
            {
                foregroundBuffer.Colour = accent.NewValue.Opacity(0.5f);

                const float animation_length = 50;

                foregroundBuffer.ClearTransforms(false, nameof(foregroundBuffer.Colour));

                if (IsHitting.Value)
                {
                    // wait for the next sync point
                    double synchronisedOffset = animation_length * 2 - Time.Current % (animation_length * 2);
                    using (foregroundBuffer.BeginDelayedSequence(synchronisedOffset))
                        foregroundBuffer.FadeColour(accent.NewValue.Lighten(0.2f), animation_length).Then().FadeColour(foregroundBuffer.Colour, animation_length).Loop();
                }

                subtractionCache.Invalidate();
            }

            protected override void Update()
            {
                base.Update();

                if (!subtractionCache.IsValid)
                {
                    subtractionLayer.Width = 5;
                    subtractionLayer.Height = Math.Max(0, DrawHeight - DrawWidth);
                    subtractionLayer.EdgeEffect = new EdgeEffectParameters
                    {
                        Colour = Color4.White,
                        Type = EdgeEffectType.Glow,
                        Radius = DrawWidth
                    };

                    foregroundBuffer.ForceRedraw();
                    subtractionBuffer.ForceRedraw();

                    subtractionCache.Validate();
                }
            }
```

Shape, stated plainly:

* whole piece: `Blending = BlendingParameters.Additive`;
* layer 1: `Background` — a full-size `Box` at `accent.Opacity(0.7f)`;
* layer 2: a `BufferedContainer` (`foregroundBuffer`, also additive) at `accent.Opacity(0.5f)`
  containing (a) a full-size white `Box` and (b) `subtractionBuffer`, a `BufferedContainer` whose
  blending is `AlphaEquation = ReverseSubtract` with `BackgroundColour = White.Opacity(0)` and which
  contains the `CircularContainer` "hole" of width `5`, height `Math.Max(0, DrawHeight − DrawWidth)`,
  centred, with a white **glow EdgeEffect of `Radius = DrawWidth`**;
* both buffers are explicitly `ForceRedraw()`n whenever the height changes (the `subtractionCache`
  is a `LayoutValue` invalidated on `Invalidation.DrawSize`), so the ReverseSubtract hole is
  re-rasterised per size. `DrawWidth`/`DrawHeight` here are the *body rect's* dimensions, i.e. the
  hole is `5 px` wide and as tall as the body minus the column width, with a glow as wide as the
  column;
* while `IsHitting`, `foregroundBuffer.Colour` pulses in an infinite 2×50 ms loop
  (`accent.Lighten(0.2f)` → back), synchronised to a 100 ms grid via
  `animation_length * 2 - Time.Current % (animation_length * 2)`;
* `Recycle()` replaces the entire foreground child (called on load and from
  `DrawableHoldNote.OnKilled`), which is the pooled-hitobject reset path for this piece
  (`IHoldNoteBody.cs:9-15`: *"Recycles the contents of this `IHoldNoteBody` to free used resources."*);
* `AccentColour` is bound to `drawableObject.AccentColour` (`DrawableHitObject.AccentColour`,
  default `Color4.Gray`), which for mania is bound to the **column's** accent colour in
  `Column.OnNewDrawableHitObject` (`Column.cs:166-174`: `maniaObject.AccentColour.BindTo(AccentColour);`),
  itself sourced from `skin.GetManiaSkinConfig<Color4>(ColumnBackgroundColour, Index)?.Value ?? Color4.Black`
  (`Column.cs:129-140`).

### 8.3 Contrast with `LegacyBodyPiece`

| | `LegacyBodyPiece` | `DefaultBodyPiece` |
|---|---|---|
| selection | legacy skin with `Version:` **and** a key texture (§8.1) | fallback when no transformer claims the component; Argon has its own (`ArgonHoldBodyPiece`) |
| content | the skin's `mania-noteXL` animation (or `lightingL` light) | two additive layers + ReverseSubtract hole |
| vertical sizing | body rect from §2, then the `32800` scale of §5.3 (non-Stretch styles) | exactly the body rect; the hole is recomputed per size |
| hit feedback | animation plays / rewinds; `lightContainer` added at column level | accent-colour pulse loop on the foreground buffer |
| `MissingStartTime` | fades the whole piece to `DarkGray` over 60 ms | **not handled at all** (no such binding in `DefaultBodyPiece`) |
| `IHoldNoteBody` | **not implemented** — `OnKilled`'s `Recycle()` cast no-ops for it | implemented (`Recycle()` rebuilds the foreground) |

---

## 9. Ambiguity ledger

1. **No revision pin.** The checkout has no `.git`, so no commit/hash can be cited; the file mtimes
   (`2026-08-03`) and `ppy.osu.Framework 2026.731.0` are the era evidence. Behaviour described here
   may differ on other snapshots.
2. **Framework behaviour is quoted from the network, not the checkout.** `CreateProxy()`
   ("*Will cause the original instance to not render itself*"), `ChildSize`/`ChildOffset`, the
   anchor arithmetic, `AnchorPosition`, `Drawable.DrawSize/DrawHeight`, `Sprite.Texture`'s size
   behaviour and `TextureAnimation`'s frame sprite were read from
   `osu-framework` at tag `2026.731.0` (the version pinned at `osu.Game/osu.Game.csproj:42`), because
   the framework is a NuGet dependency and is not vendored. If a claim in §1.3, §2.5, §3.4 or §5.3
   needs to be treated as load-bearing, re-verify it against the pinned package.
3. **`32800` (see §5.4).** The arithmetic is certain; the *reason* (legacy body textures being 32800
   px tall, making the branch a 1:1 pixel mapping) is an inference. The texture files live in
   `ppy.osu.Game.Resources`, absent from the checkout and from the local NuGet cache.
4. **`sprite.DrawHeight`'s meaning.** `LegacyBodyPiece`'s guard comment only makes sense if it is the
   *body rect height* (0 for a zero-length hold). That holds for a plain `Sprite` (it is given
   `RelativeSizeAxes = Axes.Both; Size = Vector2.One`) and for a `TextureAnimation` frame sprite
   (**[framework]** `TextureAnimation.CreateContent()` sizes the frame `RelativeSizeAxes = Axes.Both`).
   If a skin animation exposed a frame sprite that is *not* relatively sized, the guard would instead
   be reading a texture height and its comment would be wrong. Not resolvable from this checkout.
5. **`sizingContainer.Height` is not restored** when the inner `if` of §3.3 goes false after having
   shrunk (only `Time.Current < StartTime` resets it to `1`); the last shrunk value persists until the
   next `OnApply` (`sizingContainer.Size = Vector2.One`). Whether that is intentional is not stated.
6. **All non-`Up` directions take the Down branch.** Every `Direction.Value == ScrollingDirection.Up ? … : …`
   test in this path (body `Y` sign, body/sizing anchors, both paddings) treats `Left`/`Right` as Down.
   Harmless for mania, a trap if the code is reused.
7. **The head/tail constructor anchors are dead code** (§4.1): `Anchor/Origin = TopCentre` is
   overwritten by `DrawableManiaHitObject.OnDirectionChanged` during `LoadComplete`, before the first
   update. On Down the effective value is `BottomCentre`. Any reasoning that reads the constructor as
   authoritative (e.g. "the head hangs below its time position") is wrong for Down.
8. **`Height` vs `DrawHeight` in the formulas.** §2.1 uses `Head.Height`/`Tail.Height` (`Size.Y`, not
   `DrawHeight`). They coincide here only because nothing scales the head/tail drawables themselves.
   A renderer that scales a head/tail (e.g. to match a skin's `WidthForNoteHeightScale` numerically
   instead of via layout) must use the same quantity the formula uses.
9. **First-frame height availability.** `DrawableHoldNote.Update()` reads `Head.Height`/`Tail.Height`
   while the head/tail are nested pooled drawables added during `Apply`. `Column.load` pre-registers
   the pools (`Column.cs:119-123`, `RegisterPool<HeadNote, DrawableHoldNoteHead>(10, 50);` …), so they
   are loaded before use in normal gameplay; a non-pooled construction path could observe 0 on the
   first update. Flagged as a caveat, not an observed defect.
10. **`bodyContainer`'s logic body also receives `Height = L`** from the scroll container (it is
    `IHasDuration`, `HoldNoteBody.cs:17`) and `Y = 0`; it draws nothing, so this is inert — but a
    reimplementation that draws the *object* rather than the *piece* would double up.
11. **Negative-length holds** (`EndTime < StartTime`) are rejected by the editor but not defended
    against in the drawing path; `Height_body` of §7 can then be negative.
12. **Tail clipping near the end of the hold** (§3.5) is a derived consequence of the mask's fixed
    bottom edge, not something the source documents in a comment. If a reimplementation needs visual
    parity, this is the place where an "obvious" implementation (clip the body only) will differ.
13. **The `WrapMode` chosen for the body sprite may be inert.** §5.1 picks `Repeat` for every
    non-`Stretch` style, but §5.3 forces `FillMode.Stretch`, under which the texture's `[0,1]`
    rectangle is mapped exactly over the sprite's quad, so nothing samples outside the texture and no
    repetition can occur. The enum names (`RepeatTop`, `RepeatBottom`, `RepeatTopAndBottom`) suggest
    that stable repeated the body texture, and the source's own comment calls this area
    *"where things get a bit messed up"* / *"i dunno this looks about right??"*; whether lazer
    reproduces stable's repeat/tile behaviour here is **not** established by this source, and no
    tiling claim is made in this document beyond the literal `Scale` arithmetic of §5.4.
14. **`DrawableHitObject` does not define `Y`/`Height`/`DrawHeight`.** The task brief lists
    `osu.Game/Rulesets/Objects/Drawables/DrawableHitObject.cs` as the place to read those semantics;
    it contains no occurrence of `Height`, `Size`, `Anchor` or `RelativeSizeAxes` at all. Its
    declaration is `public abstract partial class DrawableHitObject : PoolableDrawableWithLifetime<HitObjectLifetimeEntry>, IAnimationTimeReference`
    (`DrawableHitObject.cs:34`), so all of those properties come from osu.Framework's `Drawable`, and
    the *values* used here come from `ScrollingHitObjectContainer` (§2.3, §4.2) and from the mania
    drawables' own anchor/size settings.

---

## 10. Compact restatement (implementation checklist)

For DOWNSCROLL (mania default), within one `DrawableHoldNote` whose own `Height`/`DrawHeight` is `L`
and whose rectangle spans `[y(tail time), y(head time)]`:

1. `y(t)` = the scroll-algorithm position of `t` plus the container's height (the leading/bottom edge
   of a note whose time is `t`); `L = y(head time) − y(tail time) > 0`.
2. Body rect: top `= y(tail time) − Tail.Height/2`, bottom `= y(head time) − Head.Height/2`
   (i.e. the body spans the two notes' vertical **centres**), width = the column width.
3. Mask rect (only when the hold is being held and `Time.Current >= StartTime` and the head was hit
   and the hold was not dropped): top `= y(tail time) − Tail.Height`, bottom `= judgement line − Head.Height/2`
   — a constant offset above the line, independent of time. At rest the mask is a no-op superset.
4. Paint order: **body (clipped) → tail (clipped) → head (unclipped)**; the real `bodyPiece` and
   `tailContainer` do not draw at all once proxied.
5. Head: bottom edge on the judgement line while held (frozen), otherwise following the hold's own
   motion; tail: bottom edge on its own time position, descending. The head is not clipped by the
   mask at all; the tail is clipped only by the mask.
6. Any hold with `L > 0` has a body of exactly `L + (Tail.Height − Head.Height)/2` px — no minimum,
   no clamp; only `L ≤ (Head.Height − Tail.Height)/2` removes it.
