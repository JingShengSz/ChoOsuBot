# osu!mania legacy skin-loading chain — source reference

A literal, quote-backed statement of what the osu!lazer source does when it resolves a
mania skin component. **This document does not describe this renderer.** It describes the
source only.

## Provenance

| Item | Value |
|---|---|
| Source checkout | `C:\Users\OwO\Desktop\osu-master` (read-only) |
| VCS revision | **unavailable** — the checkout has no `.git` directory (`git rev-parse HEAD` → `fatal: not a git repository`). Cite by path + line, not by commit. |
| File mtimes | `osu.Game.Rulesets.Mania/Skinning/Legacy/ManiaLegacySkinTransformer.cs` — 2026-08-03 14:02 |
| Framework reference | `osu.Game/osu.Game.csproj:42` — `<PackageReference Include="ppy.osu.Framework" Version="2026.731.0" />` |
| Era pin | `osu.Game/Skinning/SkinConfiguration.cs:17` — `public const decimal LATEST_VERSION = 2.7m;` |

All `file:line` citations below are relative to that checkout unless the path is absolute.
Code quotes are verbatim, including the source's own typos and stale comments.

### Files read

Ruleset side:

- `osu.Game.Rulesets.Mania/Skinning/Legacy/ManiaLegacySkinTransformer.cs`
- `osu.Game.Rulesets.Mania/Skinning/Legacy/LegacyManiaColumnElement.cs`
- `osu.Game.Rulesets.Mania/Skinning/Legacy/LegacyNotePiece.cs`
- `osu.Game.Rulesets.Mania/Skinning/Legacy/LegacyHoldNoteHeadPiece.cs`
- `osu.Game.Rulesets.Mania/Skinning/Legacy/LegacyHoldNoteTailPiece.cs`
- `osu.Game.Rulesets.Mania/Skinning/Legacy/LegacyBodyPiece.cs`
- `osu.Game.Rulesets.Mania/Skinning/Legacy/LegacyKeyArea.cs`
- `osu.Game.Rulesets.Mania/Skinning/Legacy/LegacyHitTarget.cs`
- `osu.Game.Rulesets.Mania/Skinning/Legacy/LegacyHitExplosion.cs`
- `osu.Game.Rulesets.Mania/Skinning/Legacy/LegacyManiaJudgementPiece.cs`
- `osu.Game.Rulesets.Mania/Skinning/Legacy/LegacyStageBackground.cs`
- `osu.Game.Rulesets.Mania/Skinning/Legacy/LegacyStageForeground.cs`
- `osu.Game.Rulesets.Mania/Skinning/Legacy/LegacyColumnBackground.cs`
- `osu.Game.Rulesets.Mania/Skinning/Legacy/LegacyBarLine.cs`
- `osu.Game.Rulesets.Mania/Skinning/Legacy/LegacyManiaComboCounter.cs`
- `osu.Game.Rulesets.Mania/Skinning/Legacy/HitTargetInsetContainer.cs`
- `osu.Game.Rulesets.Mania/Skinning/Legacy/ManiaClassicSkinTransformer.cs`
- `osu.Game.Rulesets.Mania/Skinning/ManiaSkinConfigurationLookup.cs`
- `osu.Game.Rulesets.Mania/Skinning/ManiaSkinConfigExtensions.cs`
- `osu.Game.Rulesets.Mania/Skinning/Argon/ManiaArgonSkinTransformer.cs`
- `osu.Game.Rulesets.Mania/Skinning/Default/ManiaTrianglesSkinTransformer.cs`
- `osu.Game.Rulesets.Mania/ManiaSkinComponentLookup.cs`, `ManiaRuleset.cs`
- `osu.Game.Rulesets.Mania/UI/{Column,Stage,ManiaPlayfield,ColumnFlow,PoolableHitExplosion,DefaultHitExplosion,DrawableManiaJudgement}.cs`
- `osu.Game.Rulesets.Mania/UI/Components/{ColumnHitObjectArea,DefaultKeyArea,DefaultColumnBackground,DefaultHitTarget,DefaultStageBackground}.cs`
- `osu.Game.Rulesets.Mania/Skinning/Default/{DefaultNotePiece,DefaultBodyPiece,DefaultBarLine}.cs`
- `osu.Game.Rulesets.Mania/Objects/Drawables/{DrawableManiaHitObject,DrawableNote,DrawableHoldNote,DrawableBarLine}.cs`
- `osu.Game.Rulesets.Mania/Beatmaps/{StageDefinition,ManiaBeatmap}.cs`

Skin side:

- `osu.Game/Skinning/LegacySkin.cs`, `LegacySkinTransformer.cs`, `SkinTransformer.cs`
- `osu.Game/Skinning/LegacySkinExtensions.cs`, `LegacySkinDecoder.cs`, `LegacySkinEncoder.cs`
- `osu.Game/Skinning/LegacyManiaSkinConfiguration.cs`, `LegacyManiaSkinConfigurationLookup.cs`, `LegacyManiaSkinDecoder.cs`
- `osu.Game/Skinning/Skin.cs`, `SkinConfiguration.cs`, `SkinUtils.cs`, `SkinnableDrawable.cs`, `SkinReloadableDrawable.cs`
- `osu.Game/Skinning/SkinProvidingContainer.cs`, `RulesetSkinProvidingContainer.cs`, `BeatmapSkinProvidingContainer.cs`
- `osu.Game/Skinning/LegacyBeatmapSkin.cs`, `DefaultLegacySkin.cs`, `RetroSkin.cs`, `LegacyColourCompatibility.cs`
- `osu.Game/Beatmaps/Formats/LegacyDecoder.cs`, `osu.Game/Rulesets/Judgements/DrawableJudgement.cs`

---

## 1. The gate

### 1.1 The three predicates

**`IsProvidingLegacyResources`** — base definition, `osu.Game/Skinning/LegacySkinTransformer.cs:16-19`:

```csharp
/// <summary>
/// Whether the skin being transformed is able to provide legacy resources for the ruleset.
/// </summary>
public virtual bool IsProvidingLegacyResources => this.HasFont(LegacyFont.Combo);
```

Mania override, `ManiaLegacySkinTransformer.cs:26`:

```csharp
public override bool IsProvidingLegacyResources => base.IsProvidingLegacyResources || hasKeyTexture.Value;
```

`HasFont` is `osu.Game/Skinning/LegacySkinExtensions.cs:135-138`:

```csharp
public static bool HasFont(this ISkin source, LegacyFont font)
{
    return source.GetTexture($"{source.GetFontPrefix(font)}-0") != null;
}
```

with the prefix for `LegacyFont.Combo` at `LegacySkinExtensions.cs:150-151`:

```csharp
case LegacyFont.Combo:
    return source.GetConfig<LegacySetting, string>(LegacySetting.ComboPrefix)?.Value ?? "score";
```

So `IsProvidingLegacyResources` is literally:

```
texture("score-0") != null                       // ComboPrefix from skin.ini, default "score"
    OR keyTextureExists                          // hasKeyTexture
```

Note the `-0` suffix: this probe asks for the **first animation frame name**
(`LegacySkinExtensions.cs:109` — `string getFrameName(int frameIndex) => $"{componentName}{animationSeparator}{frameIndex}";`,
where `animationSeparator` defaults to `"-"` at `:22`), not the bare component name. A skin
that ships `score.png` but not `score-0.png` fails the font half of this check. The
bare-name fallback is *not* consulted here.

**`hasKeyTexture`** — `ManiaLegacySkinTransformer.cs:60-64` (declaration), `76-80` (computation):

```csharp
/// <summary>
/// Whether texture for the keys exists.
/// Used to determine if the mania ruleset is skinned.
/// </summary>
private readonly Lazy<bool> hasKeyTexture;
```

```csharp
hasKeyTexture = new Lazy<bool>(() =>
{
    string keyImage = this.GetManiaSkinConfig<string>(LegacyManiaSkinConfigurationLookups.KeyImage, 0)?.Value ?? "mania-key1";
    return this.GetAnimation(keyImage, true, true) != null;
});
```

Literal reading:

1. Ask skin.ini for mania key image of **column index 0** — i.e. `LegacyManiaSkinConfiguration.ImageLookups["KeyImage0"]`.
2. If absent, use the literal string `"mania-key1"` — **note the `1`, not the `0`**. The
   fallback name does not correspond to the column index that was queried; it is the
   osu!stable default-skin filename.
3. Animate-resolve it with `animatable: true, looping: true` and require a non-null result.

Because the argument is `0`, this probe is an **absolute column index 0**, not a
`FallbackColumnIndex`. A skin that supplies only `KeyImage1`/`KeyImage2` (the typical
1/2-alternating convention) and no `KeyImage0` is probed with `mania-key1`.

`GetManiaSkinConfig` is the extension at `osu.Game.Rulesets.Mania/Skinning/ManiaSkinConfigExtensions.cs:17-19`:

```csharp
public static IBindable<T>? GetManiaSkinConfig<T>(this ISkin skin, LegacyManiaSkinConfigurationLookups lookup, int? columnIndex = null)
    where T : notnull
    => skin.GetConfig<ManiaSkinConfigurationLookup, T>(new ManiaSkinConfigurationLookup(lookup, columnIndex));
```

**`isLegacySkin`** — `ManiaLegacySkinTransformer.cs:58` (declaration), `75` (computation):

```csharp
private readonly Lazy<bool> isLegacySkin;
```

```csharp
isLegacySkin = new Lazy<bool>(() => GetConfig<SkinConfiguration.LegacySetting, decimal>(SkinConfiguration.LegacySetting.Version) != null);
```

The value therefore depends entirely on whether the wrapped skin can answer
`LegacySetting.Version` **as a `decimal`**. That path is:

- `LegacySkin.GetConfig` — `LegacySkin.cs:120-121`:
  ```csharp
  case SkinConfiguration.LegacySetting legacy:
      return legacySettingLookup<TValue>(legacy);
  ```
- `LegacySkin.legacySettingLookup` — `LegacySkin.cs:334-335`:
  ```csharp
  case SkinConfiguration.LegacySetting.Version:
      return SkinUtils.As<TValue>(new Bindable<decimal>(Configuration.LegacyVersion ?? SkinConfiguration.LATEST_VERSION));
  ```
- `SkinUtils.As` — `osu.Game/Skinning/SkinUtils.cs:19`:
  ```csharp
  public static Bindable<TValue>? As<TValue>(object? value) => (Bindable<TValue>?)value;
  ```
  An unchecked reference cast: a type mismatch yields `null`, it does not throw.
- `Configuration.LegacyVersion` is seeded to `1.0m` when a legacy skin.ini is decoded
  without a `Version:` line — `LegacySkinDecoder.cs:66-72`:
  ```csharp
  protected override SkinConfiguration CreateTemplateObject()
  {
      var config = base.CreateTemplateObject();
      config.LegacyVersion = 1.0m;
      config.IsLatestVersion = false;
      return config;
  }
  ```
  and overridden from the ini at `LegacySkinDecoder.cs:35-45`:
  ```csharp
  case @"Version":
      if (pair.Value == "latest")
      {
          skin.LegacyVersion = SkinConfiguration.LATEST_VERSION;
          skin.IsLatestVersion = true;
      }
      else if (decimal.TryParse(pair.Value, NumberStyles.AllowDecimalPoint, CultureInfo.InvariantCulture, out decimal version))
      {
          skin.LegacyVersion = version;
          skin.IsLatestVersion = false;
      }
  ```

**The one case where `isLegacySkin` is `false` for a `LegacySkin`** is the beatmap skin.
`LegacyBeatmapSkin.GetConfig` — `osu.Game/Skinning/LegacyBeatmapSkin.cs:71-87`:

```csharp
public override IBindable<TValue>? GetConfig<TLookup, TValue>(TLookup lookup)
{
    switch (lookup)
    {
        case SkinConfiguration.LegacySetting s when s == SkinConfiguration.LegacySetting.Version:
            // For lookup simplicity, ignore beatmap-level versioning completely.

            // If it is decided that we need this due to beatmaps somehow using it, the default (1.0 specified in LegacySkinDecoder.CreateTemplateObject)
            // needs to be removed else it will cause incorrect skin behaviours. This is due to the config lookup having no context of which skin
            // it should be returning the version for.

            LogLookupDebug(this, lookup, LookupDebugType.Miss);
            return null;
    }

    return base.GetConfig<TLookup, TValue>(lookup);
}
```

So for a beatmap-provided skin, `GetConfig<LegacySetting, decimal>(Version)` is `null` →
`isLegacySkin.Value == false` → the gate fails. (It would fail anyway, because
`LegacyBeatmapSkin.AllowManiaConfigLookups => false` — `LegacyBeatmapSkin.cs:21` — makes
`lookupForMania` unreachable. See §1.4.)

### 1.2 The gate itself

`ManiaLegacySkinTransformer.cs:83-143`, with the `GlobalSkinnableContainers.MainHUDComponents`
body (lines 96-134) elided at the `...` marker:

```csharp
public override Drawable GetDrawableComponent(ISkinComponentLookup lookup)
{
    switch (lookup)
    {
        case GlobalSkinnableContainerLookup containerLookup:
            // Modifications for global components.
            if (containerLookup.Ruleset == null)
                return base.GetDrawableComponent(lookup);

            // we don't have enough assets to display these components (this is especially the case on a "beatmap" skin).
            if (!IsProvidingLegacyResources)
                return null;
            ...
        case SkinComponentLookup<HitResult> resultComponent:
            return getResult(resultComponent.Component);

        case ManiaSkinComponentLookup maniaComponent:
            if (!isLegacySkin.Value || !hasKeyTexture.Value)
                return null;
```

Precisely:

- **`GlobalSkinnableContainerLookup`** (line 87) — gated on `IsProvidingLegacyResources`
  *only*, and *only* when `containerLookup.Ruleset != null`. With `Ruleset == null` it
  delegates immediately to `base.GetDrawableComponent(lookup)`
  (`SkinTransformer.cs:29` → `Skin.GetDrawableComponent`). This is the MainHUD components
  container (combo counter / spectator list / leaderboard) — **not** a
  `ManiaSkinComponents` value.
- **`SkinComponentLookup<HitResult>`** (line 138) — **NOT GATED.** `getResult` is called
  before any `isLegacySkin` / `hasKeyTexture` check. See §2.12.
- **`ManiaSkinComponentLookup`** (lines 141-143) — gated on
  `isLegacySkin.Value && hasKeyTexture.Value`. This is the *only* gated path.
- Anything else falls to `return base.GetDrawableComponent(lookup);` (line 187).

Note the two gates use **different** predicates: the global container gate uses
`IsProvidingLegacyResources` (font **or** key texture); the component gate uses
`hasKeyTexture` (key texture only, **and** `isLegacySkin`).

### 1.3 What happens to every mania component when the gate fails

When the gate fails, `GetDrawableComponent` returns `null` for that lookup. The consequence
is not "nothing is drawn" — it is a two-stage waterfall:

**Stage A — the `ISkinSource` chain keeps looking.** `SkinProvidingContainer.GetDrawableComponent`
(`SkinProvidingContainer.cs:117-130`):

```csharp
public Drawable? GetDrawableComponent(ISkinComponentLookup lookup)
{
    foreach (var (_, lookupWrapper) in skinSources)
    {
        Drawable? sourceDrawable;
        if ((sourceDrawable = lookupWrapper.GetDrawableComponent(lookup)) != null)
            return sourceDrawable;
    }

    if (!AllowFallingBackToParent)
        return null;

    return ParentSource?.GetDrawableComponent(lookup);
}
```

The gameplay chain is assembled in `RulesetSkinProvidingContainer`
(`osu.Game/Skinning/RulesetSkinProvidingContainer.cs`):

- line 43: `protected override bool AllowFallingBackToParent => false;`
- lines 60-66:
  ```csharp
  InternalChild = new BeatmapSkinProvidingContainer(GetRulesetTransformedSkin(beatmapSkin), GetRulesetTransformedSkin(skinManager.DefaultClassicSkin))
  ```
- lines 79-112 (`RefreshSources`): every parent source is passed through
  `Ruleset.CreateSkinTransformer(skin, Beatmap)` (line 91) and the ruleset resource skin is
  inserted before the last `TrianglesSkin` (lines 101-109).
- `ManiaRuleset.CreateSkinTransformer` (`ManiaRuleset.cs:71-90`) chooses by concrete skin type:
  ```csharp
  case TrianglesSkin:
      return new ManiaTrianglesSkinTransformer(skin, beatmap);

  case ArgonSkin:
      return new ManiaArgonSkinTransformer(skin, beatmap);

  case DefaultLegacySkin:
  case RetroSkin:
      return new ManiaClassicSkinTransformer(skin, beatmap);

  case LegacySkin:
      return new ManiaLegacySkinTransformer(skin, beatmap);
  ```
  So a `ManiaLegacySkinTransformer` exists only for plain `LegacySkin` (i.e. a user skin or
  a beatmap skin); the default classic skin and Retro get `ManiaClassicSkinTransformer`,
  which **inherits** the gated `GetDrawableComponent` unchanged
  (`ManiaClassicSkinTransformer.cs:11-16` overrides only `GetConfig`).

The resulting source order a gameplay drawable sees (outermost first) is:

1. the **beatmap** skin, transformed — `BeatmapSkinProvidingContainer`, whose
   `SetSources` is driven by `BeatmapSkinProvidingContainer.cs:50-69`:
   ```csharp
   if (!userSkinIsLegacy && beatmapProvidingResources && classicFallback != null)
       SetSources(new[] { skin, classicFallback });
   else
       SetSources(new[] { skin });
   ```
   where `beatmapProvidingResources` is literally
   `skin is LegacySkinTransformer legacySkin && legacySkin.IsProvidingLegacyResources`
   (line 53) — the *same* predicate as §1.1, evaluated a second time here.
2. the **classic** default skin, transformed (only in the `SetSources(new[] { skin, classicFallback })` branch);
3. then, because `SkinProvidingContainer.AllowFallingBackToParent` defaults to `true`
   (`SkinProvidingContainer.cs:36`) while `RulesetSkinProvidingContainer` sets it to `false`
   (line 43), everything the ruleset container exposes: every parent source transformed
   (line 91), plus `rulesetResourcesSkin` inserted before the last `TrianglesSkin`
   (lines 101-109). The parent list is `SkinManager.AllSources`
   (`SkinManager.cs:329-345`):
   ```csharp
   yield return CurrentSkin.Value;

   // Skin manager provides default fallbacks.
   // This handles cases where a user skin doesn't have the required resources for complete display of
   // certain elements.

   if (CurrentSkin.Value is LegacySkin && CurrentSkin.Value != DefaultClassicSkin)
       yield return DefaultClassicSkin;

   if (CurrentSkin.Value != trianglesSkin)
       yield return trianglesSkin;
   ```

Because every one of those sources is itself a transformed skin, a failing gate on one
source does **not** stop the walk. A user `LegacySkin` that fails `hasKeyTexture` still
reaches `DefaultClassicSkin` later in the list, and `DefaultLegacySkin` passes the gate
(`Configuration.LegacyVersion = 2.7m;` — `DefaultLegacySkin.cs:50` — so `isLegacySkin` is
true), so legacy mania drawables are usually still produced, textured from the classic
default skin. Reaching the `Default*` fallbacks of Stage B requires that **every** source in
the chain returns `null`.

**Stage B — `SkinnableDrawable` builds the hard-coded default.** If no source in the chain
returns a drawable, `SkinnableDrawable.SkinChanged` (`osu.Game/Skinning/SkinnableDrawable.cs:76-100`):

```csharp
protected override void SkinChanged(ISkinSource skin)
{
    var retrieved = skin.GetDrawableComponent(ComponentLookup);

    if (retrieved == null)
    {
        Drawable = CreateDefault(ComponentLookup);
        isDefault = true;
    }
    else
    {
        Drawable = retrieved;
        isDefault = false;
    }

    scaling.Invalidate();

    if (CentreComponent)
    {
        Drawable.Origin = Anchor.Centre;
        Drawable.Anchor = Anchor.Centre;
    }

    InternalChild = Drawable;
}
```

with `CreateDefault` at line 69:

```csharp
protected virtual Drawable CreateDefault(ISkinComponentLookup lookup) => createDefault?.Invoke(lookup) ?? Empty();
```

The `createDefault` delegate is the second constructor argument at each mania construction
site. Site-by-site (this is the definitive answer to "what does each component fall back
to"):

| Component | Construction site | Default when the gate fails |
|---|---|---|
| `ColumnBackground` | `Column.cs:108` | `new DefaultColumnBackground()` |
| `HitTarget` | `ColumnHitObjectArea.cs:31` | `new DefaultHitTarget()` |
| `KeyArea` | `Column.cs:98` | `new DefaultKeyArea()` |
| `Note` | `DrawableNote.cs:57` | `new DefaultNotePiece()` |
| `HoldNoteHead` | via `DrawableHoldNoteHead.Component` → `DrawableNote.load` | `new DefaultNotePiece()` (there is no separate default head piece) |
| `HoldNoteTail` | via `DrawableHoldNoteTail.Component` → `DrawableNote.load` | `new DefaultNotePiece()` |
| `HoldNoteBody` | `DrawableHoldNote.cs:106` | `new DefaultBodyPiece { RelativeSizeAxes = Axes.Both }` |
| `HitExplosion` | `PoolableHitExplosion.cs:30` | `new DefaultHitExplosion()` |
| `StageBackground` | `Stage.cs:88` | `new DefaultStageBackground()` (a black `Box`, `DefaultStageBackground.cs:22-27`) |
| `StageForeground` | `Stage.cs:119` | **no delegate passed** → `Empty()` |
| `BarLine` | `DrawableBarLine.cs:35` | `new DefaultBarLine()` |

`DrawableHoldNoteHead` / `DrawableHoldNoteTail` do not create their own skinnable drawable;
they only override the component enum — `DrawableHoldNoteTail.cs:24` and
`DrawableHoldNoteHead.cs:24`:

```csharp
protected override ManiaSkinComponents Component => ManiaSkinComponents.HoldNoteTail;
```

```csharp
protected override ManiaSkinComponents Component => ManiaSkinComponents.HoldNoteHead;
```

(`DrawableNote.cs:37` declares the base: `protected virtual ManiaSkinComponents Component => ManiaSkinComponents.Note;`.)
They inherit `DrawableNote.load`'s `new SkinnableDrawable(new ManiaSkinComponentLookup(Component), _ => new DefaultNotePiece())`.

**A special case that is *not* a gate failure.** `ManiaSkinComponents.HitTarget` returns
a **non-null** `Drawable.Empty()` when the gate passes
(`ManiaLegacySkinTransformer.cs:150-153`):

```csharp
case ManiaSkinComponents.HitTarget:
    // Legacy skins sandwich the hit target between the column background and the column light.
    // To preserve this ordering, it's created manually inside LegacyStageBackground.
    return Drawable.Empty();
```

`Drawable.Empty()` is non-null, so `SkinnableDrawable` takes the `else` branch
(`isDefault = false`) and the per-column `ColumnHitObjectArea` hit-target slot stays empty.
The real legacy hit target — `LegacyHitTarget` — is constructed by hand inside
`LegacyStageBackground.load` (`LegacyStageBackground.cs:60-63`):

```csharp
new HitTargetInsetContainer
{
    Child = new LegacyHitTarget { RelativeSizeAxes = Axes.Both }
}
```

Consequence: **when the gate fails for `HitTarget`, the fallback is `DefaultHitTarget`**
(the coloured per-column bar, `UI/Components/DefaultHitTarget.cs`), not `Empty()`; and when
the gate passes, the `Empty()` result means the *stage-wide* `LegacyHitTarget` is the only
hit target drawn.

Also note **when** the gate is evaluated. `isLegacySkin` and `hasKeyTexture` are
`Lazy<bool>` fields (`ManiaLegacySkinTransformer.cs:58, 64`), so each is computed at most
once per transformer instance and the answer is then frozen. Transformer instances are not
long-lived: `RulesetSkinProvidingContainer.RefreshSources` constructs a fresh one for every
source on every refresh (`RulesetSkinProvidingContainer.cs:86-98`, via
`GetRulesetTransformedSkin` → `Ruleset.CreateSkinTransformer`), and `RefreshSources` runs
from `TriggerSourceChanged` (`SkinProvidingContainer.cs:224-230`), which fires once during
`CreateChildDependencies` (`:83`) and again whenever any consumed source changes.
On top of that, `SkinnableDrawable` re-queries `GetDrawableComponent` on every
`ISkinSource.SourceChanged` (`SkinReloadableDrawable.cs:30-41, 71-85`). The practical effect
is that a skin switch re-runs the whole gate from scratch; within one unchanged skin, the
gate result is stable.

### 1.4 The `ManiaSkinConfigurationLookup` side-channel

Separately from drawables, configuration lookups are re-routed by
`ManiaLegacySkinTransformer.GetConfig` (`ManiaLegacySkinTransformer.cs:211-219`):

```csharp
public override IBindable<TValue> GetConfig<TLookup, TValue>(TLookup lookup)
{
    if (lookup is ManiaSkinConfigurationLookup maniaLookup)
    {
        return base.GetConfig<LegacyManiaSkinConfigurationLookup, TValue>(new LegacyManiaSkinConfigurationLookup(beatmap.TotalColumns, maniaLookup.Lookup, maniaLookup.ColumnIndex));
    }

    return base.GetConfig<TLookup, TValue>(lookup);
}
```

This translation is **not gated**. `LegacySkin.GetConfig` then dispatches at
`LegacySkin.cs:110-118`:

```csharp
case LegacyManiaSkinConfigurationLookup maniaLookup:
    if (!AllowManiaConfigLookups)
        break;

    var result = lookupForMania<TValue>(maniaLookup);
    if (result != null)
        return result;

    break;
```

`AllowManiaConfigLookups` is `true` on `LegacySkin` (`LegacySkin.cs:33`) and `false` on
`LegacyBeatmapSkin` (`LegacyBeatmapSkin.cs:21`).

---

## 2. Component table

`ManiaSkinComponents` has exactly 11 values — `ManiaSkinComponentLookup.cs:20-33`:

```csharp
public enum ManiaSkinComponents
{
    ColumnBackground,
    HitTarget,
    KeyArea,
    Note,
    HoldNoteHead,
    HoldNoteTail,
    HoldNoteBody,
    HitExplosion,
    StageBackground,
    StageForeground,
    BarLine
}
```

`ManiaLegacySkinTransformer.GetDrawableComponent` (`ManiaLegacySkinTransformer.cs:145-184`)
covers **all 11**; its `default:` arm is therefore unreachable for a well-formed lookup:

```csharp
default:
    throw new UnsupportedSkinComponentException(lookup);
```

In the tables below, **"key"** is the literal dictionary key used against
`LegacyManiaSkinConfiguration.ImageLookups` (a `Dictionary<string,string>`,
`LegacyManiaSkinConfiguration.cs:30`), and **"resolver"** is the `LegacySkin` line that
performs the lookup. `ColumnIndex` is the value carried by `LegacyManiaSkinConfigurationLookup.ColumnIndex`.

`{n}` means the raw `ColumnIndex` — **0-based**, absolute across all stages — **not**
`FallbackColumnIndex`.

### 2.1 `ColumnBackground` → `LegacyColumnBackground`

Return site: `ManiaLegacySkinTransformer.cs:147-148`. Implementation: `Legacy/LegacyColumnBackground.cs:29-64`.

| Lookup | Col? | Key | Resolver | Hard-coded fallback (drawable) | Config default |
|---|---|---|---|---|---|
| `LightImage` | **no** (`LegacyColumnBackground.cs:32`) | `StageLight` | `LegacySkin.cs:243-244` | `"mania-stage-light"` (`:33`) | — |
| `LightPosition` | yes (`:35`) | — (numeric; `LegacySkin.cs:162-163`) | — | `0` (`:36`) | `(480 - 413) * POSITION_SCALE_FACTOR` (`LegacyManiaSkinConfiguration.cs:41`) |
| `ColumnLightColour` | yes (`:38`) | `ColourLight{n+1}` | `LegacySkin.cs:181-183` | `Color4.White` (`:39`) | — |
| `LightFramePerSecond` | **no** (`:41`) | — (numeric; `LegacySkin.cs:260-261`) | — | `60` (`:41`) | `60` (`:47`); decoder clamps `>0` else `24` (`LegacyManiaSkinDecoder.cs:134-137`) |

`LightImage` is looked up **without** a column index, so the `skin.ini` key is the global
`StageLight`, never a per-column variant. The light is created through
`skin.GetAnimation(lightImage, true, true, frameLength: 1000d / lightFramePerSecond)` (`:50`).

### 2.2 `HitTarget` → `Drawable.Empty()`

Return site: `ManiaLegacySkinTransformer.cs:150-153`. The class that actually renders the
legacy hit target is `LegacyHitTarget` (`Legacy/LegacyHitTarget.cs:23-62`), constructed by
`LegacyStageBackground.cs:60-63`.

| Lookup | Col? | Key | Resolver | Hard-coded fallback |
|---|---|---|---|---|
| `HitTargetImage` | no (`LegacyHitTarget.cs:26`) | `StageHint` | `LegacySkin.cs:246-247` | `"mania-stage-hint"` (`:27`) |
| `ShowJudgementLine` | no (`:29`) | — (numeric; `LegacySkin.cs:165-166`) | — | `true` (`:30`), config default `true` (`LegacyManiaSkinConfiguration.cs:45`) |
| `JudgementLineColour` | no (`:32`) | `ColourJudgementLine` | `LegacySkin.cs:174-175` | `Color4.White` (`:33`) |

Texture fetch is `skin.GetTexture(targetImage)` — **not** `GetAnimation` — at
`LegacyHitTarget.cs:44`, and the sprite is scaled `new Vector2(1, 0.9f * 1.6025f)` (`:45`).
The judgement line colour passes through `LegacyColourCompatibility.DisallowZeroAlpha`
(`:54`), which forces `A = 1` when `A == 0` (`LegacyColourCompatibility.cs:22-27`).

### 2.3 `KeyArea` → `LegacyKeyArea`

Return site: `ManiaLegacySkinTransformer.cs:155-156`. Implementation: `Legacy/LegacyKeyArea.cs:35-74`.

| Lookup | Col? | Key | Resolver | Hard-coded fallback |
|---|---|---|---|---|
| `KeyImage` | yes (`:38`) | `KeyImage{n}` | `LegacySkin.cs:226-228` | `$"mania-key{FallbackColumnIndex}"` (`:39`) |
| `KeyImageDown` | yes (`:41`) | `KeyImage{n}D` | `LegacySkin.cs:230-232` | `$"mania-key{FallbackColumnIndex}D"` (`:42`) |
| `KeysUnderNotes` | no (`:72`) | — (numeric; `LegacySkin.cs:257-258`) | — | `false` (`:72`); config default `false` (`LegacyManiaSkinConfiguration.cs:46`) |

Both key images go through `skin.GetTexture(name, WrapMode.ClampToEdge, default)` (`:54`, `:61`) —
**not** `GetAnimation`. Comment at `:50`: *"Key images are placed side-to-side on the
playfield, therefore ClampToEdge must be used to prevent any gaps between each key."*

When `KeysUnderNotes` is true, the key area adds `CreateProxy()` into
`Column.UnderlayElements` (`:72-73`).

### 2.4 `Note` → `LegacyNotePiece`

Return site: `ManiaLegacySkinTransformer.cs:158-159`. Implementation: `Legacy/LegacyNotePiece.cs`.

| Lookup | Col? | Key | Resolver | Hard-coded fallback |
|---|---|---|---|---|
| `WidthForNoteHeightScale` | **no** (`LegacyNotePiece.cs:36`) | — (numeric; `LegacySkin.cs:147-151`) | — | `null` → `DrawWidth` (`:63`) |
| `NoteImage` | yes (`:99` via `GetColumnSkinConfig`) | `NoteImage{n}` | `LegacySkin.cs:207-209` | `$"mania-note{FallbackColumnIndex}"` (`LegacyNotePiece.cs:100`, suffix `""` at `:86`) |

`WidthForNoteHeightScale` resolution is not a plain field read —
`LegacySkin.cs:147-151`:

```csharp
case LegacyManiaSkinConfigurationLookups.WidthForNoteHeightScale:
    float width = existing.WidthForNoteHeightScale;
    if (width <= 0)
        width = existing.MinimumColumnWidth;
    return SkinUtils.As<TValue>(new Bindable<float>(width));
```

so when the ini value is absent (field default `0`, `LegacyManiaSkinConfiguration.cs:32`)
the value is `MinimumColumnWidth` = `ColumnWidth.Min()` (`:82`), which itself defaults to
`DEFAULT_COLUMN_SIZE = 30 * POSITION_SCALE_FACTOR = 48` (`:22`, `:79`).

The sprite is scaled in `Update` (`LegacyNotePiece.cs:54-65`):

```csharp
if (noteAnimation is Sprite sprite)
    texture = sprite.Texture;
else if (noteAnimation is TextureAnimation textureAnimation && textureAnimation.FrameCount > 0)
    texture = textureAnimation.CurrentFrame;

if (texture != null)
{
    float noteHeight = widthForNoteHeightScale ?? DrawWidth;
    noteAnimation.Scale = Vector2.Divide(new Vector2(DrawWidth, noteHeight), texture.DisplayWidth);
}
```

`DisplayWidth` is the `@2x`-adjusted width (`Texture.ScaleAdjust`); see §5.1.

### 2.5 `HoldNoteHead` → `LegacyHoldNoteHeadPiece`

Return site: `ManiaLegacySkinTransformer.cs:161-162`. Implementation: `Legacy/LegacyHoldNoteHeadPiece.cs`.

| Lookup | Col? | Key | Resolver | Hard-coded fallback |
|---|---|---|---|---|
| `HoldNoteHeadImage` | yes | `NoteImage{n}H` | `LegacySkin.cs:211-213` | `$"mania-note{FallbackColumnIndex}H"` (`LegacyNotePiece.cs:100`, suffix `"H"` at `:90-92`) |
| `NoteImage` (fallback) | yes | `NoteImage{n}` | `LegacySkin.cs:207-209` | `$"mania-note{FallbackColumnIndex}"` |

`LegacyHoldNoteHeadPiece.cs:46-51`:

```csharp
protected override Drawable? GetAnimation(ISkinSource skin)
{
    // TODO: Should fallback to the head from default legacy skin instead of note.
    return GetAnimationFromLookup(skin, LegacyManiaSkinConfigurationLookups.HoldNoteHeadImage)
           ?? GetAnimationFromLookup(skin, LegacyManiaSkinConfigurationLookups.NoteImage);
}
```

The `??` chains **resolved drawables**, not names. `GetAnimationFromLookup` returns `null`
only when `GetAnimation` returns `null`, i.e. when *no* texture (numbered or not) was found
for that name (§5). A skin with a `NoteImage{n}H` ini entry pointing at a file that does
not exist therefore falls through to the entire `NoteImage{n}` chain.

Head pieces also dim to `Colour4.DarkGray` once `MissingStartTime` is non-null
(`LegacyHoldNoteHeadPiece.cs:37-44`), via `FadeColour(Colour4.DarkGray, 60)`.

### 2.6 `HoldNoteTail` → `LegacyHoldNoteTailPiece`

Return site: `ManiaLegacySkinTransformer.cs:164-165`. Implementation: `Legacy/LegacyHoldNoteTailPiece.cs`.

| Lookup | Col? | Key | Resolver | Hard-coded fallback |
|---|---|---|---|---|
| `HoldNoteTailImage` | yes | `NoteImage{n}T` | `LegacySkin.cs:215-217` | `$"mania-note{FallbackColumnIndex}T"` (suffix `"T"`, `LegacyNotePiece.cs:94-96`) |
| `HoldNoteHeadImage` (fallback) | yes | `NoteImage{n}H` | `LegacySkin.cs:211-213` | `$"mania-note{FallbackColumnIndex}H"` |
| `NoteImage` (fallback) | yes | `NoteImage{n}` | `LegacySkin.cs:207-209` | `$"mania-note{FallbackColumnIndex}"` |

`LegacyHoldNoteTailPiece.cs:55-61`:

```csharp
protected override Drawable? GetAnimation(ISkinSource skin)
{
    // TODO: Should fallback to the head from default legacy skin instead of note.
    return GetAnimationFromLookup(skin, LegacyManiaSkinConfigurationLookups.HoldNoteTailImage)
           ?? GetAnimationFromLookup(skin, LegacyManiaSkinConfigurationLookups.HoldNoteHeadImage)
           ?? GetAnimationFromLookup(skin, LegacyManiaSkinConfigurationLookups.NoteImage);
}
```

The tail additionally inverts the scroll direction for its own container
(`LegacyHoldNoteTailPiece.cs:47-53`):

```csharp
protected override void OnDirectionChanged(ValueChangedEvent<ScrollingDirection> direction)
{
    // Invert the direction
    base.OnDirectionChanged(direction.NewValue == ScrollingDirection.Up
        ? new ValueChangedEvent<ScrollingDirection>(ScrollingDirection.Down, ScrollingDirection.Down)
        : new ValueChangedEvent<ScrollingDirection>(ScrollingDirection.Up, ScrollingDirection.Up));
}
```

### 2.7 `HoldNoteBody` → `LegacyBodyPiece`

Return site: `ManiaLegacySkinTransformer.cs:167-168`. Implementation: `Legacy/LegacyBodyPiece.cs:40-98`.

| Lookup | Col? | Key | Resolver | Hard-coded fallback |
|---|---|---|---|---|
| `HoldNoteBodyImage` | yes (`:45`) | `NoteImage{n}L` | `LegacySkin.cs:219-221` | `$"mania-note{FallbackColumnIndex}L"` (`:46`) |
| `HoldNoteLightImage` | yes as *passed* (`:48`), **ignored by the resolver** | `LightingL` | `LegacySkin.cs:223-224` | `"lightingL"` (`:49`) |
| `HoldNoteLightScale` | yes (`:51`) | `LightingLWidth` (array) | `LegacySkin.cs:296-305` | `1` (`:52`) |
| `NoteBodyStyle` | **no** (`:77`) | `NoteBodyStyle` | `LegacySkin.cs:197-205` | see below (`:79`, `:192-216`) |

`HoldNoteLightImage` is **not** per-column despite being fetched with
`GetColumnSkinConfig<...>(skin, ..., )` — the resolver hard-codes `"LightingL"`
(`LegacySkin.cs:224`). The same is true of `ExplosionImage` → `"LightingN"`
(`LegacySkin.cs:169`). Only `Lighting*Width` is a per-column numeric array.

`NoteBodyStyle` has a three-way default at `LegacySkin.cs:197-205`:

```csharp
case LegacyManiaSkinConfigurationLookups.NoteBodyStyle:

    if (existing.NoteBodyStyle != null)
        return SkinUtils.As<TValue>(new Bindable<LegacyManiaSkinConfiguration.LegacyNoteBodyStyle>(existing.NoteBodyStyle.Value));

    if (GetConfig<SkinConfiguration.LegacySetting, decimal>(SkinConfiguration.LegacySetting.Version)?.Value < 2.5m)
        return SkinUtils.As<TValue>(new Bindable<LegacyManiaSkinConfiguration.LegacyNoteBodyStyle>());

    return SkinUtils.As<TValue>(new Bindable<LegacyManiaSkinConfiguration.LegacyNoteBodyStyle>(LegacyManiaSkinConfiguration.LegacyNoteBodyStyle.RepeatBottom));
```

`new Bindable<LegacyNoteBodyStyle>()` is `default(LegacyNoteBodyStyle)` = `Stretch = 0`
(`LegacyManiaSkinConfiguration.cs:93-103`). So: skin.ini version `< 2.5` → `Stretch`;
version `>= 2.5` (or unparsable/null) → `RepeatBottom`. Note `null` propagates as
`null < 2.5m == false`, so a missing version line yields `RepeatBottom` here (but `1.0m`
is seeded by `LegacySkinDecoder.cs:69`, so in practice `< 2.5` wins for a bare skin.ini).

Body geometry (`LegacyBodyPiece.cs:192-216`): for `Stretch`, `bodySprite.Scale = new Vector2(1, scaleDirection)`.
For everything else:

```csharp
var sprite = bodySprite as Sprite ?? bodySprite.ChildrenOfType<Sprite>().Single();

bodySprite.FillMode = FillMode.Stretch;
// i dunno this looks about right??
// the guard against zero draw height is intended for zero-length hold notes. yes, such cases have been spotted in the wild.
if (sprite.DrawHeight > 0)
    bodySprite.Scale = new Vector2(1, scaleDirection * MathF.Max(1, 32800 / sprite.DrawHeight));
```

`LegacyManiaSkinConfiguration.LegacyNoteBodyStyle` declares only four members
(`:93-103`), with `Repeat = 1` commented out:

```csharp
public enum LegacyNoteBodyStyle
{
    Stretch = 0,

    // listed as the default on https://osu.ppy.sh/wiki/en/Skinning/skin.ini, but is seemingly not according to the source.
    // Repeat = 1,

    RepeatTop = 2,
    RepeatBottom = 3,
    RepeatTopAndBottom = 4,
}
```

`Enum.TryParse<LegacyNoteBodyStyle>` (`LegacyManiaSkinDecoder.cs:125-128`) will still
accept the strings `"Repeat"` and `"1"`, producing the *undefined* value `1`, which then
falls into `LegacyBodyPiece`'s `default:` arm (`:200`).

Wrap mode is chosen from the body style (`LegacyBodyPiece.cs:79`):

```csharp
var wrapMode = bodyStyle == LegacyManiaSkinConfiguration.LegacyNoteBodyStyle.Stretch ? WrapMode.ClampToEdge : WrapMode.Repeat;
```

### 2.8 `HitExplosion` → `LegacyHitExplosion`

Return site: `ManiaLegacySkinTransformer.cs:170-171`. Implementation: `Legacy/LegacyHitExplosion.cs:30-58`.

| Lookup | Col? | Key | Resolver | Hard-coded fallback |
|---|---|---|---|---|
| `ExplosionImage` | yes as *passed* (`:33`), **ignored by the resolver** | `LightingN` | `LegacySkin.cs:168-169` | `"lightingN"` (`:34`) |
| `ExplosionScale` | yes (`:36`) | `LightingNWidth` (array) | `LegacySkin.cs:285-294` | `1` (`:37`) |

The explosion's frame length is derived from the frame count
(`LegacyHitExplosion.cs:39-51`):

```csharp
// Create a temporary animation to retrieve the number of frames, in an effort to calculate the intended frame length.
// This animation is discarded and re-queried with the appropriate frame length afterwards.
var tmp = skin.GetAnimation(imageName, true, false);
double frameLength = 0;
if (tmp is IFramedAnimation tmpAnimation && tmpAnimation.FrameCount > 0)
    frameLength = Math.Max(1000 / 60.0, 170.0 / tmpAnimation.FrameCount);

explosion = skin.GetAnimation(imageName, true, false, frameLength: frameLength)?.With(d =>
```

Note `looping: false` on both queries — the explosion animation does **not** loop. The
same "temporary animation" trick appears in `LegacyBodyPiece.cs:54-59` for the hold light,
with the same formula (`Math.Max(1000 / 60.0, 170.0 / FrameCount)`) but `looping: true`.

`ExplosionScale` (`LegacySkin.cs:285-294`):

```csharp
case LegacyManiaSkinConfigurationLookups.ExplosionScale:
    Debug.Assert(maniaLookup.ColumnIndex != null);

    if (GetConfig<SkinConfiguration.LegacySetting, decimal>(SkinConfiguration.LegacySetting.Version)?.Value < 2.5m)
        return SkinUtils.As<TValue>(new Bindable<float>(1));

    if (existing.ExplosionWidth[maniaLookup.ColumnIndex.Value] != 0)
        return SkinUtils.As<TValue>(new Bindable<float>(existing.ExplosionWidth[maniaLookup.ColumnIndex.Value] / LegacyManiaSkinConfiguration.DEFAULT_COLUMN_SIZE));

    return SkinUtils.As<TValue>(new Bindable<float>(existing.ColumnWidth[maniaLookup.ColumnIndex.Value] / LegacyManiaSkinConfiguration.DEFAULT_COLUMN_SIZE));
```

### 2.9 `StageBackground` → `LegacyStageBackground`

Return site: `ManiaLegacySkinTransformer.cs:173-174`. Implementation: `Legacy/LegacyStageBackground.cs:30-79`.

| Lookup | Col? | Key | Resolver | Hard-coded fallback |
|---|---|---|---|---|
| `LeftStageImage` | no (`:33`) | `StageLeft` | `LegacySkin.cs:234-235` | `"mania-stage-left"` (`:34`) |
| `RightStageImage` | no (`:36`) | `StageRight` | `LegacySkin.cs:237-238` | `"mania-stage-right"` (`:37`) |
| `HitPosition` (via `HitTargetInsetContainer`) | no | — (numeric) | `LegacySkin.cs:153-154` | `Stage.HIT_TARGET_POSITION` = `110` (`HitTargetInsetContainer.cs:33`, `Stage.cs:38`) |
| `LeftLineWidth` | yes, **stage-local** (`:97`) | `ColumnLineWidth` (array) | `LegacySkin.cs:277-279` | `1` (`:97`) |
| `RightLineWidth` | yes, **stage-local** (`:98`) | `ColumnLineWidth` (array) | `LegacySkin.cs:281-283` | `1` (`:98`) |
| `ColumnLineColour` | yes, **stage-local** (`:103`) | `ColourColumnLine` | `LegacySkin.cs:171-172` | `Color4.White` (`:103`) |
| `ColumnBackgroundColour` | yes, **stage-local** (`:104`) | `Colour{n+1}` | `LegacySkin.cs:177-179` | `Color4.Black` (`:104`) |
| `SkinConfiguration.LegacySetting.Version` | no (`:101`) | `Version` | `LegacySkin.cs:334-335` | — (`>= 2.4m` test) |

The stage images are fetched with `skin.GetTexture(...)` (`:46`, `:53`) and stretched
vertically in `Update` (`:70-79`):

```csharp
if (leftSprite?.Height > 0)
    leftSprite.Scale = new Vector2(1, DrawHeight / leftSprite.Height);
```

The left/right line visibility rule (`LegacyStageBackground.cs:100-101`):

```csharp
bool hasLeftLine = leftLineWidth > 0;
bool hasRightLine = (rightLineWidth > 0 && skin.GetConfig<SkinConfiguration.LegacySetting, decimal>(SkinConfiguration.LegacySetting.Version)?.Value >= 2.4m) || isLastColumn;
```

Both line containers are additionally `Scale = new Vector2(0.740f, 1)` (`:121`, `:134`), and
the last column's right line is offset `X = isLastColumn ? -0.16f : 0` (`:130`).

> **Inconsistency worth flagging.** `LegacyStageBackground` enumerates its own columns
> `for (int i = 0; i < stageDefinition.Columns; i++)` (`:66`) and passes the **stage-local**
> `i` to the inner `ColumnBackground` (`:67`). The `ColumnIndex` it forwards to
> `GetManiaSkinConfig(..., columnIndex)` is therefore stage-local and 0-based. Every other
> per-column consumer (`LegacyManiaColumnElement.GetColumnSkinConfig` →
> `Column.Index`) uses the **absolute** index across all stages. On a dual-stage beatmap the
> two disagree for the second stage. `ManiaSkinConfigurationLookup.cs:19` states the intended
> convention: *"Note that this is the absolute index across all stages."* — which
> `LegacyStageBackground` violates.

### 2.10 `StageForeground` → `LegacyStageForeground`

Return site: `ManiaLegacySkinTransformer.cs:176-177`. Implementation: `Legacy/LegacyStageForeground.cs:25-38`.

| Lookup | Col? | Key | Resolver | Hard-coded fallback |
|---|---|---|---|---|
| `BottomStageImage` | no (`:28`) | `StageBottom` | `LegacySkin.cs:240-241` | `"mania-stage-bottom"` (`:29`) |

Fetched with `skin.GetAnimation(bottomImage, true, true)` (`:31`) — an **animation** query,
unlike the left/right stage images — and hard-scaled `Scale = new Vector2(1.6f)` (`:31`).

### 2.11 `BarLine` → `LegacyBarLine`

Return site: `ManiaLegacySkinTransformer.cs:179-180`. Implementation: `Legacy/LegacyBarLine.cs:16-36`.

| Lookup | Col? | Key | Resolver | Hard-coded fallback |
|---|---|---|---|---|
| `BarLineHeight` | no (`:19`) | `BarlineHeight` (numeric) | `LegacySkin.cs:194-195` | `1.2f` (`:19`); config default `1.2f` (`LegacyManiaSkinConfiguration.cs:44`) |
| `BarLineColour` | no (`:23`) | `ColourBarline` | `LegacySkin.cs:188-189` | `Color4.White` (`:23`) |

Note the **key casing**: the drawable reads the numeric via `BarlineHeight` in the ini
(`LegacyManiaSkinDecoder.cs:89` — `case "BarlineHeight":`) but the colour via
`ColourBarline` (lower-case `l`, `LegacySkin.cs:189`). `ColourBarline` reaches
`CustomColours` through the generic `Colour*` catch-all (`LegacyManiaSkinDecoder.cs:173-175`).

The bar line is a plain `Box` with `EdgeSmoothness = new Vector2(0.3f)` (`:26`, `:31`);
`LegacyBarLine` has no `Major` distinction, unlike `DefaultBarLine`
(`Skinning/Default/DefaultBarLine.cs:76-82`, which sets height `1.7f` major / `1.2f` minor).

### 2.12 Not a `ManiaSkinComponents` value: `SkinComponentLookup<HitResult>` → `LegacyManiaJudgementPiece`

Handled at `ManiaLegacySkinTransformer.cs:138-139` **before the gate**, by
`getResult` (`:190-200`):

```csharp
private Drawable getResult(HitResult result)
{
    if (!hit_result_mapping.TryGetValue(result, out var value))
        return null;

    string filename = this.GetManiaSkinConfig<string>(value)?.Value
                      ?? default_hit_result_skin_filenames[result];

    var animation = this.GetAnimation(filename, true, true, frameLength: 1000 / 20d);
    return animation == null ? null : new LegacyManiaJudgementPiece(result, animation);
}
```

The two mappings (`:32-56`):

| `HitResult` | Lookup | skin.ini key | Default filename |
|---|---|---|---|
| `Perfect` | `Hit300g` | `Hit300g` | `mania-hit300g` |
| `Great` | `Hit300` | `Hit300` | `mania-hit300` |
| `Good` | `Hit200` | `Hit200` | `mania-hit200` |
| `Ok` | `Hit100` | `Hit100` | `mania-hit100` |
| `Meh` | `Hit50` | `Hit50` | `mania-hit50` |
| `Miss` | `Hit0` | `Hit0` | `mania-hit0` |

The ini key is generated, not literal — `LegacySkin.cs:249-255`:

```csharp
case LegacyManiaSkinConfigurationLookups.Hit0:
case LegacyManiaSkinConfigurationLookups.Hit50:
case LegacyManiaSkinConfigurationLookups.Hit100:
case LegacyManiaSkinConfigurationLookups.Hit200:
case LegacyManiaSkinConfigurationLookups.Hit300:
case LegacyManiaSkinConfigurationLookups.Hit300g:
    return SkinUtils.As<TValue>(getManiaImage(existing, maniaLookup.Lookup.ToString()));
```

`maniaLookup.Lookup.ToString()` yields the enum member name verbatim (`Hit300g`, etc.).

`hit_result_mapping` covers only 6 `HitResult` values; `HitResult.None` and every other
value produce `null` (line 192-193). The lookup is created by `DrawableJudgement`
(`osu.Game/Rulesets/Judgements/DrawableJudgement.cs:166-167`):

```csharp
AddInternal(JudgementBody = new SkinnableDrawable(new SkinComponentLookup<HitResult>(type), _ =>
    CreateDefaultJudgement(type), confineMode: ConfineMode.NoScaling));
```

with the mania default being `DefaultManiaJudgementPiece`
(`osu.Game.Rulesets.Mania/UI/DrawableManiaJudgement.cs:25`).

`LegacyManiaJudgementPiece` positions itself from two more lookups
(`Legacy/LegacyManiaJudgementPiece.cs:50-67`):

```csharp
private void onDirectionChanged()
{
    float hitPosition = skin.GetManiaSkinConfig<float>(LegacyManiaSkinConfigurationLookups.HitPosition)?.Value ?? 0;
    float scorePosition = skin.GetManiaSkinConfig<float>(LegacyManiaSkinConfigurationLookups.ScorePosition)?.Value ?? 0;

    float hitPositionFromTop = 480f * LegacyManiaSkinConfiguration.POSITION_SCALE_FACTOR - hitPosition;

    if (scorePosition > hitPositionFromTop / 2f)
    {
        Anchor = direction.Value == ScrollingDirection.Up ? Anchor.TopCentre : Anchor.BottomCentre;
        Y = direction.Value == ScrollingDirection.Up ? hitPositionFromTop - scorePosition : scorePosition - hitPositionFromTop;
    }
    else
    {
        Anchor = direction.Value == ScrollingDirection.Up ? Anchor.BottomCentre : Anchor.TopCentre;
        Y = direction.Value == ScrollingDirection.Up ? -scorePosition : scorePosition;
    }
}
```

Both are looked up **without** a column index and both default to `0` when the bindable is
missing (not to the config's own defaults — the config defaults
`HitPosition = (480 - 402) * 1.6f`, `ScorePosition = 300 * 1.6f`
(`LegacyManiaSkinConfiguration.cs:24, 40, 43`) only apply when the lookup itself succeeds,
which it always does for `LegacySkin`; the `?? 0` arms are for non-legacy sources).

The judgement animation frame length is hard-coded: `frameLength: 1000 / 20d` = **50 ms**
(`ManiaLegacySkinTransformer.cs:198`). Animation playback (`LegacyManiaJudgementPiece.cs:69-99`):
`FadeInFromZero(20, Easing.Out).Then().Delay(160).FadeOutFromOne(40, Easing.In)`; `Miss`
does a scale/rotate wobble using `RNG.NextSingle(-5.73f, 5.73f)` (`:86`); everything else
uses a fixed 5-step scale sequence (`:90-96`).

### 2.13 Lookups that exist in the enum but are never resolved by `LegacySkin`

`lookupForMania` (`LegacySkin.cs:136-309`) has **no `case`** for:

- `StagePaddingTop`
- `StagePaddingBottom`

They are declared at `LegacyManiaSkinConfigurationLookup.cs:45-46`, are consumed by
`Stage.onSkinChanged` (`osu.Game.Rulesets.Mania/UI/Stage.cs:174-184`):

```csharp
float paddingTop = currentSkin.GetConfig<ManiaSkinConfigurationLookup, float>(new ManiaSkinConfigurationLookup(LegacyManiaSkinConfigurationLookups.StagePaddingTop))?.Value ?? 0;
float paddingBottom = currentSkin.GetConfig<ManiaSkinConfigurationLookup, float>(new ManiaSkinConfigurationLookup(LegacyManiaSkinConfigurationLookups.StagePaddingBottom))?.Value ?? 0;
```

…and are only ever non-null under `ManiaArgonSkinTransformer`, which hard-codes them
(`Skinning/Argon/ManiaArgonSkinTransformer.cs:146-148`):

```csharp
case LegacyManiaSkinConfigurationLookups.StagePaddingBottom:
case LegacyManiaSkinConfigurationLookups.StagePaddingTop:
    return SkinUtils.As<TValue>(new Bindable<float>(30));
```

For a legacy skin the switch falls through to `return null;` (`LegacySkin.cs:308`), so the
stage padding is always `0`. **There is no skin.ini key for stage padding in lazer.**

Likewise `ColumnNoteBodyStyles` (`LegacyManiaSkinConfiguration.cs:63`) is written out by the
encoder (`LegacySkinEncoder.cs:145-146`, `NoteBodyStyle{i}`) but never read back by the
decoder (no `NoteBodyStyle{n}` prefix arm at `LegacyManiaSkinDecoder.cs:178-185`) and never
consulted by any lookup.

`LeftColumnSpacing` / `RightColumnSpacing` are half-values, from `LegacySkin.cs:263-275`:

```csharp
case LegacyManiaSkinConfigurationLookups.LeftColumnSpacing:
    Debug.Assert(maniaLookup.ColumnIndex != null);
    if (maniaLookup.ColumnIndex == 0)
        return SkinUtils.As<TValue>(new Bindable<float>());

    return SkinUtils.As<TValue>(new Bindable<float>(existing.ColumnSpacing[maniaLookup.ColumnIndex.Value - 1] / 2));

case LegacyManiaSkinConfigurationLookups.RightColumnSpacing:
    Debug.Assert(maniaLookup.ColumnIndex != null);
    if (maniaLookup.ColumnIndex == existing.ColumnSpacing.Length)
        return SkinUtils.As<TValue>(new Bindable<float>());

    return SkinUtils.As<TValue>(new Bindable<float>(existing.ColumnSpacing[maniaLookup.ColumnIndex.Value] / 2));
```

They are consumed by `Column.onSourceChanged` (`Column.cs:133-139`) and `ColumnFlow`
(`UI/ColumnFlow.cs:127-135`), both falling back to `Stage.COLUMN_SPACING = 1` (`Stage.cs:36`).

---

## 3. Per-column resolution

### 3.1 Two different indices

There are **three** distinct column identifiers in play, and they are not interchangeable:

| Identifier | Definition | Example (7K stage 2 of a dual-stage beatmap, column 8 overall) |
|---|---|---|
| `Column.Index` | `Column.cs:36-38` — *"The index of this column as part of the whole playfield."* | `8` |
| stage-local index | `Stage.cs:136-142` — `for (int i = 0; i < definition.Columns; i++)` | `1` |
| `LegacyManiaColumnElement.FallbackColumnIndex` | `LegacyManiaColumnElement.cs:28` | `"2"` |

`ManiaSkinConfigurationLookup.ColumnIndex` is documented as absolute
(`ManiaSkinConfigurationLookup.cs:16-21`):

```csharp
/// <summary>
/// The column which is being looked up.
/// May be null if the configuration does not apply to a <see cref="Column"/>.
/// Note that this is the absolute index across all stages.
/// </summary>
public readonly int? ColumnIndex;
```

…and `LegacyManiaSkinConfigurationLookup.ColumnIndex` repeats it
(`LegacyManiaSkinConfigurationLookup.cs:18-23`). `TotalColumns` comes from
`beatmap.TotalColumns` (`ManiaLegacySkinTransformer.cs:215`) and selects the `[Mania]` block:
`LegacySkin.lookupForMania` picks `ManiaConfigurations[maniaLookup.TotalColumns]`, creating
an empty default config if absent (`LegacySkin.cs:138-139`):

```csharp
if (!ManiaConfigurations.TryGetValue(maniaLookup.TotalColumns, out var existing))
    ManiaConfigurations[maniaLookup.TotalColumns] = existing = new LegacyManiaSkinConfiguration(maniaLookup.TotalColumns);
```

### 3.2 `FallbackColumnIndex`

`LegacyManiaColumnElement.cs:25-42`:

```csharp
/// <summary>
/// The column type identifier to use for texture lookups, in the case of no user-provided configuration.
/// </summary>
protected string FallbackColumnIndex { get; private set; } = null!;

[BackgroundDependencyLoader]
private void load()
{
    if (Column.IsSpecial)
        FallbackColumnIndex = "S";
    else
    {
        // Account for cases like dual-stage (assume that all stages have the same column count for now).
        int columnInStage = Column.Index % stage.Columns;
        int distanceToEdge = Math.Min(columnInStage, (stage.Columns - 1) - columnInStage);
        FallbackColumnIndex = distanceToEdge % 2 == 0 ? "1" : "2";
    }
}
```

Literal rules:

1. `Column.IsSpecial` (`Column.cs:54-57`, `:69`) → `"S"`.
2. Otherwise: `columnInStage = Column.Index % stage.Columns` — note it uses the
   **absolute** index modulo the stage width, not the stage-local index. For stages of equal
   width these coincide; `LegacyManiaColumnElement.cs:37` states the assumption explicitly
   (*"assume that all stages have the same column count for now"*).
3. `distanceToEdge = min(columnInStage, (stage.Columns - 1) - columnInStage)`.
4. `"1"` if that distance is even, `"2"` if odd.

Worked values for a 7K stage (`Columns = 7`). Remember that step 1 short-circuits first:
`StageDefinition.IsSpecialColumn(3)` is `7 % 2 == 1 && 3 == 7 / 2` → `true`, so the middle
column never reaches the parity formula.

| columnInStage | `IsSpecial`? | distanceToEdge | FallbackColumnIndex |
|---|---|---|---|
| 0 | no | 0 | `"1"` |
| 1 | no | 1 | `"2"` |
| 2 | no | 2 | `"1"` |
| 3 | **yes** | 3 | **`"S"`** |
| 4 | no | 2 | `"1"` |
| 5 | no | 1 | `"2"` |
| 6 | no | 0 | `"1"` |

Worked values for a 4K stage (`Columns = 4`) — `4 % 2 == 1` is `false`, so there is no
special column and the parity formula decides every column:

| columnInStage | distanceToEdge | FallbackColumnIndex |
|---|---|---|
| 0 | 0 | `"1"` |
| 1 | 1 | `"2"` |
| 2 | 1 | `"2"` |
| 3 | 0 | `"1"` |

The pattern is *not* a simple 1/2 alternation: it is symmetric about the centre
(`d` then mirrored `d`), and it is `"1"` on both edges for every key count.

`Column.IsSpecial` comes from `StageDefinition.IsSpecialColumn`
(`osu.Game.Rulesets.Mania/Beatmaps/StageDefinition.cs:32`):

```csharp
public bool IsSpecialColumn(int column) => Columns % 2 == 1 && column == Columns / 2;
```

i.e. **only odd column counts have a special column**, and it is the exact middle one
(3K → index 1, 5K → 2, 7K → 3, 9K → 4). `Stage.cs:136-147` passes the stage-local index to
`IsSpecialColumn` and the absolute index to `Column`'s constructor:

```csharp
for (int i = 0; i < definition.Columns; i++)
{
    bool isSpecial = definition.IsSpecialColumn(i);

    var action = columnStartAction;
    columnStartAction++;
    var column = CreateColumn(firstColumnIndex + i, isSpecial).With(c =>
    {
        c.RelativeSizeAxes = Axes.Both;
        c.Width = 1;
        c.Action.Value = action;
    });
```

### 3.3 `GetColumnSkinConfig`

`LegacyManiaColumnElement.cs:44-45`:

```csharp
protected IBindable<T>? GetColumnSkinConfig<T>(ISkin skin, LegacyManiaSkinConfigurationLookups lookup) where T : notnull
    => skin.GetManiaSkinConfig<T>(lookup, Column.Index);
```

`Column.Index` — **absolute**, 0-based.

Consumers of `GetColumnSkinConfig` (all pass `Column.Index`):

| Site | Lookups |
|---|---|
| `LegacyNotePiece.cs:99` | `NoteImage`, `HoldNoteHeadImage`, `HoldNoteTailImage` |
| `LegacyBodyPiece.cs:45, 48, 51` | `HoldNoteBodyImage`, `HoldNoteLightImage`, `HoldNoteLightScale` |
| `LegacyKeyArea.cs:38, 41, 72` | `KeyImage`, `KeyImageDown`, `KeysUnderNotes` |
| `LegacyColumnBackground.cs:35, 38` | `LightPosition`, `ColumnLightColour` |
| `LegacyHitExplosion.cs:33, 36` | `ExplosionImage`, `ExplosionScale` |

Lookups fetched *without* a column index anywhere in legacy mania:

| Site | Lookup |
|---|---|
| `ManiaLegacySkinTransformer.cs:78` | `KeyImage` with literal `0` (the gate probe) |
| `ManiaLegacySkinTransformer.cs:109` | `ComboPosition` |
| `ManiaLegacySkinTransformer.cs:195` | one of `Hit0/50/100/200/300/300g` |
| `LegacyNotePiece.cs:36` | `WidthForNoteHeightScale` |
| `LegacyBodyPiece.cs:77` | `NoteBodyStyle` |
| `LegacyColumnBackground.cs:32, 41` | `LightImage`, `LightFramePerSecond` |
| `LegacyHitTarget.cs:26, 29, 32` | `HitTargetImage`, `ShowJudgementLine`, `JudgementLineColour` |
| `LegacyStageBackground.cs:33, 36` | `LeftStageImage`, `RightStageImage` |
| `LegacyStageForeground.cs:28` | `BottomStageImage` |
| `LegacyBarLine.cs:19, 23` | `BarLineHeight`, `BarLineColour` |
| `LegacyManiaJudgementPiece.cs:52, 53` | `HitPosition`, `ScorePosition` |
| `LegacyManiaComboCounter.cs:73` | `ComboBreakColour` |
| `HitTargetInsetContainer.cs:33` | `HitPosition` |
| `Stage.cs:176, 177` | `StagePaddingTop`, `StagePaddingBottom` |
| `Column.cs:131, 133-139` | `ColumnBackgroundColour`, `LeftColumnSpacing`, `RightColumnSpacing` |

> **Ambiguity / unverifiable ordering.** `FallbackColumnIndex` is assigned in
> `LegacyManiaColumnElement.load()` (`[BackgroundDependencyLoader]`, line 30-42) and read in
> derived classes' own `[BackgroundDependencyLoader]` methods
> (`LegacyKeyArea.load`, `LegacyNotePiece.load` via the virtual `GetAnimation`). This only
> works if osu.Framework invokes dependency-loader methods **base-type-first**. I could not
> verify that ordering from this checkout: `osu.Framework` is a binary
> `PackageReference` (`osu.Game/osu.Game.csproj:42`), and the shipped
> `osu.Framework.xml` documentation for `BackgroundDependencyLoaderAttribute` does **not**
> state any ordering rule. If the framework ever changed that order, `FallbackColumnIndex`
> would be `null` inside the derived loader and the fallback names would degrade to
> `mania-note`, `mania-key`, `mania-keyD`.

A second, related reading hazard: `LegacyNotePiece.load` calls the **virtual**
`GetAnimation(skin)`, which for `LegacyHoldNoteHeadPiece` / `LegacyHoldNoteTailPiece`
executes their overrides *during* the base class's loader (`LegacyNotePiece.cs:43-44`):

```csharp
Child = noteAnimation = GetAnimation(skin) ?? Empty()
```

### 3.4 skin.ini key construction for `ColumnIndex`

`LegacySkin.lookupForMania` names the key from `maniaLookup.ColumnIndex` — note it uses the
index **verbatim and 0-based** for image keys, but **+1** for colour keys:

| Lookup | Key expression | Source line |
|---|---|---|
| `NoteImage` | `$"NoteImage{maniaLookup.ColumnIndex}"` | `LegacySkin.cs:209` |
| `HoldNoteHeadImage` | `$"NoteImage{maniaLookup.ColumnIndex}H"` | `:213` |
| `HoldNoteTailImage` | `$"NoteImage{maniaLookup.ColumnIndex}T"` | `:217` |
| `HoldNoteBodyImage` | `$"NoteImage{maniaLookup.ColumnIndex}L"` | `:221` |
| `KeyImage` | `$"KeyImage{maniaLookup.ColumnIndex}"` | `:228` |
| `KeyImageDown` | `$"KeyImage{maniaLookup.ColumnIndex}D"` | `:232` |
| `ColumnBackgroundColour` | `$"Colour{maniaLookup.ColumnIndex + 1}"` | `:179` |
| `ColumnLightColour` | `$"ColourLight{maniaLookup.ColumnIndex + 1}"` | `:183` |

So column index `0` → `NoteImage0`, `KeyImage0`, but `Colour1`, `ColourLight1`.

---

## 4. skin.ini key name mapping

### 4.1 Image keys → `LegacyManiaSkinConfiguration.ImageLookups`

`ImageLookups` is a plain `Dictionary<string, string>` (`LegacyManiaSkinConfiguration.cs:30`),
populated **verbatim from the ini line keys** (`LegacyManiaSkinDecoder.cs:177-185`):

```csharp
// Custom sprite paths
case string when pair.Key.StartsWith("NoteImage", StringComparison.Ordinal):
case string when pair.Key.StartsWith("KeyImage", StringComparison.Ordinal):
case string when pair.Key.StartsWith("Hit", StringComparison.Ordinal):
case string when pair.Key.StartsWith("Stage", StringComparison.Ordinal):
case string when pair.Key.StartsWith("Lighting", StringComparison.Ordinal):
case @"WarningArrow":
    currentConfig.ImageLookups[pair.Key] = pair.Value;
    break;
```

**The ini keys are case-sensitive** (`StringComparison.Ordinal`), and `getManiaImage`
(`LegacySkin.cs:326-327`) is an exact-match dictionary read:

```csharp
private IBindable<string>? getManiaImage(LegacyManiaSkinConfiguration source, string lookup)
    => source.ImageLookups.TryGetValue(lookup, out string? image) ? new Bindable<string>(image) : null;
```

A skin writing `noteimage0:` or `stagehint:` produces no match.

Complete mapping for every string-valued lookup the mania legacy code reads:

| `LegacyManiaSkinConfigurationLookups` | ini key (`ImageLookups`) | Resolver line |
|---|---|---|
| `NoteImage` | `NoteImage{n}` | `LegacySkin.cs:209` |
| `HoldNoteHeadImage` | `NoteImage{n}H` | `:213` |
| `HoldNoteTailImage` | `NoteImage{n}T` | `:217` |
| `HoldNoteBodyImage` | `NoteImage{n}L` | `:221` |
| `KeyImage` | `KeyImage{n}` | `:228` |
| `KeyImageDown` | `KeyImage{n}D` | `:232` |
| `HoldNoteLightImage` | `LightingL` | `:224` |
| `ExplosionImage` | `LightingN` | `:169` |
| `LightImage` | `StageLight` | `:244` |
| `HitTargetImage` | `StageHint` | `:247` |
| `LeftStageImage` | `StageLeft` | `:235` |
| `RightStageImage` | `StageRight` | `:238` |
| `BottomStageImage` | `StageBottom` | `:241` |
| `Hit300g` | `Hit300g` | `:255` |
| `Hit300` | `Hit300` | `:255` |
| `Hit200` | `Hit200` | `:255` |
| `Hit100` | `Hit100` | `:255` |
| `Hit50` | `Hit50` | `:255` |
| `Hit0` | `Hit0` | `:255` |

Note the naming asymmetry: the lazer fallback **filenames** are `mania-stage-light`,
`mania-stage-hint`, `mania-note1`, `mania-key1`, `lightingN`, `lightingL` — but the **ini
keys** are `StageLight`, `StageHint`, `NoteImage0`, `KeyImage0`, `LightingN`, `LightingL`.

Because the decoder matches on prefixes, a skin.ini key like `HitTargetImage:` (a
`Hit*` key) *would* be stored in `ImageLookups` as `HitTargetImage` — but no resolver ever
asks for that key. Only the exact strings in the table above are read.

### 4.2 Colour keys → `LegacyManiaSkinConfiguration.CustomColours`

Colours go through `LegacyManiaSkinDecoder.cs:173-175` → `LegacyDecoder.HandleColours`
(`osu.Game/Beatmaps/Formats/LegacyDecoder.cs:126-148`), which stores the raw ini key:

```csharp
tHasCustomColours.CustomColours[pair.Key] = colour;
```

| Lookup | ini key | Resolver line | Type constraint |
|---|---|---|---|
| `ColumnLineColour` | `ColourColumnLine` | `LegacySkin.cs:172` | global |
| `JudgementLineColour` | `ColourJudgementLine` | `:175` | global |
| `BarLineColour` | `ColourBarline` | `:189` | global |
| `ComboBreakColour` | `ColourBreak` | `:186` | global |
| `ColumnBackgroundColour` | `Colour{n+1}` | `:179` | per column, 1-based |
| `ColumnLightColour` | `ColourLight{n+1}` | `:183` | per column, 1-based |

`getCustomColour` (`LegacySkin.cs:323-324`) is again an exact-match read. All colour
lookups `Debug.Assert(maniaLookup.ColumnIndex != null)`; these asserts are compiled out in
Release (they are `Debug.Assert`, not runtime guards).

### 4.3 Numeric / array keys → fields

Parsed in `LegacyManiaSkinDecoder.flushPendingLines` (`LegacyManiaSkinDecoder.cs:67-195`).
`Keys:` must appear **before** any other key in the block or the lines are buffered and then
discarded (`:25-32`, `:43-60`):

```csharp
case "Keys":
    currentConfig = new LegacyManiaSkinConfiguration(int.Parse(pair.Value, CultureInfo.InvariantCulture));

    // Silently ignore duplicate configurations.
    if (output.All(c => c.Keys != currentConfig.Keys))
        output.Add(currentConfig);

    // All existing lines can be flushed now that we have a valid configuration.
    flushPendingLines();
    break;
```

| ini key | Field | Transform | Line |
|---|---|---|---|
| `Keys` | `LegacyManiaSkinConfiguration.Keys` | `int.Parse` | `:43-44` |
| `ColumnLineWidth` | `ColumnLineWidth[]` | `parseArrayValue(..., applyScaleFactor: false)` | `:77-79` |
| `ColumnSpacing` | `ColumnSpacing[]` | `× 1.6` | `:81-83` |
| `ColumnWidth` | `ColumnWidth[]` | `× 1.6` | `:85-87` |
| `BarlineHeight` | `BarLineHeight` | raw float | `:89-91` |
| `HitPosition` | `HitPosition` | `(480 - clamp(v, 240, 480)) * 1.6` | `:93-95` |
| `LightPosition` | `LightPosition` | `(480 - v) * 1.6` | `:97-99` |
| `ComboPosition` | `ComboPosition` | `v * 1.6` | `:101-103` |
| `ScorePosition` | `ScorePosition` | `v * 1.6` | `:105-107` |
| `JudgementLine` | `ShowJudgementLine` | `pair.Value == "1"` | `:109-111` |
| `KeysUnderNotes` | `KeysUnderNotes` | `pair.Value == "1"` | `:113-115` |
| `LightingNWidth` | `ExplosionWidth[]` | `× 1.6` | `:117-119` |
| `LightingLWidth` | `HoldNoteLightWidth[]` | `× 1.6` | `:121-123` |
| `NoteBodyStyle` | `NoteBodyStyle` | `Enum.TryParse` | `:125-128` |
| `WidthForNoteHeightScale` | `WidthForNoteHeightScale` | `× 1.6` | `:130-132` |
| `LightFramePerSecond` | `LightFramePerSecond` | `>0 ? v : 24` | `:134-137` |
| `SpecialStyle` | `SpecialStyle` | `Enum.TryParse` | `:139-142` |
| `ColumnStart` | `ColumnStart` | raw float (TODO: no scale) | `:144-146` |
| `ColumnRight` | `ColumnRight` | raw float (TODO: no scale) | `:148-150` |
| `UpsideDown` | `UpsideDown` | `== "1"` | `:152-154` |
| `SeparateScore` | `SeparateScore` | `== "1"` | `:156-158` |
| `SplitStages` | `SplitStages` | `== "1"` | `:160-162` |
| `StageSeparation` | `StageSeparation` | raw float | `:164-166` |
| `ComboBurstStyle` | `ComboBurstStyle` | `Enum.TryParse` | `:168-171` |
| `Colour*` | `CustomColours[key]` | `HandleColours` | `:173-175` |
| `NoteImage*` / `KeyImage*` / `Hit*` / `Stage*` / `Lighting*` / `WarningArrow` | `ImageLookups[key]` | verbatim | `:177-185` |
| `KeyFlipWhenUpsideDown*` / `NoteFlipWhenUpsideDown*` | `FlipSettings[key]` | verbatim (never read) | `:187-190` |

Array parsing (`LegacyManiaSkinDecoder.cs:197-216`):

```csharp
private void parseArrayValue(string value, float[] output, bool applyScaleFactor = true)
{
    string[] values = value.Split(',');

    for (int i = 0; i < values.Length; i++)
    {
        if (i >= output.Length)
            break;

        if (!float.TryParse(values[i], NumberStyles.Float, CultureInfo.InvariantCulture, out float parsedValue))
            // some skins may provide incorrect entries in array values. to match stable behaviour, read such entries as zero.
            // see: https://github.com/ppy/osu/issues/26464, stable code: https://github.com/peppy/osu-stable-reference/blob/3ea48705eb67172c430371dcfc8a16a002ed0d3d/osu!/Graphics/Skinning/Components/Section.cs#L134-L137
            parsedValue = 0;

        if (applyScaleFactor)
            parsedValue *= LegacyManiaSkinConfiguration.POSITION_SCALE_FACTOR;

        output[i] = parsedValue;
    }
}
```

A short array leaves trailing elements at their constructor default:
`ColumnLineWidth` is filled with `2`, `ColumnWidth` with `DEFAULT_COLUMN_SIZE`
(`LegacyManiaSkinConfiguration.cs:78-79`); `ColumnSpacing`, `ExplosionWidth`,
`HoldNoteLightWidth` are left at `0`.

### 4.4 Lookups with no ini key at all

These are computed, not stored:

| Lookup | Source |
|---|---|
| `ColumnWidth` | `existing.ColumnWidth[ColumnIndex]` (`LegacySkin.cs:143-145`) |
| `MinimumColumnWidth` | `existing.ColumnWidth.Min()` (`:191-192`, `LegacyManiaSkinConfiguration.cs:82`) |
| `WidthForNoteHeightScale` | field, else `MinimumColumnWidth` (`:147-151`) |
| `LeftLineWidth` / `RightLineWidth` | `ColumnLineWidth[n]` / `ColumnLineWidth[n+1]` (`:277-283`) |
| `LeftColumnSpacing` / `RightColumnSpacing` | `ColumnSpacing[n-1] / 2` / `ColumnSpacing[n] / 2` (`:263-275`) |
| `ExplosionScale` | `ExplosionWidth[n] / 48`, else `ColumnWidth[n] / 48`, else `1` (`:285-294`) |
| `HoldNoteLightScale` | `HoldNoteLightWidth[n] / 48`, else `ColumnWidth[n] / 48`, else `1` (`:296-305`) |
| `HitPosition`, `ComboPosition`, `ScorePosition`, `LightPosition` | plain field reads (`:153-163`) |
| `ShowJudgementLine`, `KeysUnderNotes`, `BarLineHeight`, `LightFramePerSecond` | plain field reads (`:165-166`, `:194-195`, `:257-261`) |
| `NoteBodyStyle` | field, else version-dependent (`:197-205`) |
| `StagePaddingTop` / `StagePaddingBottom` | **nothing** — falls through to `return null;` (`:308`) |

`POSITION_SCALE_FACTOR = 1.6f` and `DEFAULT_COLUMN_SIZE = 30 * POSITION_SCALE_FACTOR = 48`
(`LegacyManiaSkinConfiguration.cs:17, 22`).

---

## 5. Texture vs animation

### 5.1 `GetTexture` — single texture

`LegacySkin.GetTexture` (`LegacySkin.cs:545-582`):

```csharp
public override Texture? GetTexture(string componentName, WrapMode wrapModeS, WrapMode wrapModeT)
{
    switch (componentName)
    {
        case "Menu/fountain-star":
            componentName = "star2";
            break;

        case @"Intro/Welcome/welcome_text":
            componentName = @"welcome_text";
            break;
    }

    Texture? texture = null;
    float ratio = 1;

    if (AllowHighResolutionSprites)
    {
        // some component names (especially user-controlled ones, like `HitX` in mania)
        // may contain `@2x` scale specifications.
        // stable happens to check for that and strip them, so do the same to match stable behaviour.
        componentName = componentName.Replace(@"@2x", string.Empty);

        string twoTimesFilename = $"{Path.ChangeExtension(componentName, null)}@2x{Path.GetExtension(componentName)}";

        texture = Textures?.Get(twoTimesFilename, wrapModeS, wrapModeT);

        if (texture != null)
            ratio = 2;
    }

    texture ??= Textures?.Get(componentName, wrapModeS, wrapModeT);

    if (texture != null)
        texture.ScaleAdjust = ratio;

    return texture;
}
```

Three mania-relevant consequences:

1. **`@2x` is stripped** from the *component name* first (`:566`) — a skin.ini value of
   `NoteImage0: mania-note1@2x.png` becomes the lookup name `mania-note1.png`.
2. The `@2x` file is **tried first** (`:568-570`), and on success `ScaleAdjust = 2`
   (`:579`). `ScaleAdjust` affects `DisplayWidth`/`DisplayHeight`, which matters for the
   note scaling formula (§2.4).
3. `AllowHighResolutionSprites` is `true` on `LegacySkin` (`:543`) but **`false` on
   `LegacyBeatmapSkin`** (`LegacyBeatmapSkin.cs:27`), so beatmap-supplied art never picks
   up `@2x` variants.

`GetTexture` is reached through the transformer — `SkinTransformer.GetTexture`
(`SkinTransformer.cs:33`):

```csharp
public virtual Texture? GetTexture(string componentName, WrapMode wrapModeS, WrapMode wrapModeT) => Skin.GetTexture(componentName, wrapModeS, wrapModeT);
```

and through the container — `SkinProvidingContainer.GetTexture`
(`SkinProvidingContainer.cs:132-145`) walks the source list and returns the first non-null.

### 5.2 `GetAnimation` — texture *or* animation

`LegacySkinExtensions.cs:22-56`:

```csharp
public static Drawable? GetAnimation(this ISkin? source, string componentName, bool animatable, bool looping, bool applyConfigFrameRate = false, string animationSeparator = "-",
                                     bool startAtCurrentTime = true, double? frameLength = null, Vector2? maxSize = null)
    => source.GetAnimation(componentName, default, default, animatable, looping, applyConfigFrameRate, animationSeparator, startAtCurrentTime, frameLength, maxSize);

public static Drawable? GetAnimation(this ISkin? source, string componentName, WrapMode wrapModeS, WrapMode wrapModeT, bool animatable, bool looping, bool applyConfigFrameRate = false,
                                     string animationSeparator = "-", bool startAtCurrentTime = true, double? frameLength = null, Vector2? maxSize = null)
{
    if (source == null)
        return null;

    var textures = GetTextures(source, componentName, wrapModeS, wrapModeT, animatable, animationSeparator, maxSize, out var retrievalSource);

    switch (textures.Length)
    {
        case 0:
            return null;

        case 1:
            return new Sprite { Texture = textures[0] };

        default:
            Debug.Assert(retrievalSource != null);

            var animation = new SkinnableTextureAnimation(startAtCurrentTime)
            {
                DefaultFrameLength = frameLength ?? getFrameLength(retrievalSource, applyConfigFrameRate, textures),
                Loop = looping,
            };

            foreach (var t in textures)
                animation.AddFrame(t);

            return animation;
    }
}
```

The two overloads differ only in whether wrap modes are supplied; the 3-arg form passes
`default, default` (i.e. `WrapMode.ClampToEdge`).

**The return type is a function of the frame count, not of `animatable`:**

| `textures.Length` | Returned |
|---|---|
| `0` | `null` |
| `1` | `new Sprite { Texture = textures[0] }` |
| `>= 2` | `new SkinnableTextureAnimation(...)` |

Parameter semantics:

| Parameter | Meaning | If it changes what happens |
|---|---|---|
| `animatable` | attempt numbered-frame discovery at all | `false` → discovery is skipped entirely and only the bare name is fetched |
| `looping` | copied to `TextureAnimation.Loop` | **only observable with ≥ 2 frames** |
| `frameLength` | copied to `TextureAnimation.DefaultFrameLength` | **only observable with ≥ 2 frames** |
| `applyConfigFrameRate` | consult `LegacySetting.AnimationFramerate` for the frame length | only if `frameLength == null` and ≥ 2 frames |
| `animationSeparator` | inserted between the base name and the frame index (default `"-"`, so frames are `name-0`, `name-1`, …) | — |
| `startAtCurrentTime` | passed to the `TextureAnimation` ctor | — |
| `maxSize` | crop each texture to a maximum size (`WithMaximumSize`, `:112-133`) | — |

### 5.3 Frame file naming and discovery

`GetTextures` (`LegacySkinExtensions.cs:58-110`):

```csharp
public static Texture[] GetTextures(this ISkin? source, string componentName, WrapMode wrapModeS, WrapMode wrapModeT, bool animatable, string animationSeparator, Vector2? maxSize,
                                    out ISkin? retrievalSource)
{
    retrievalSource = null;

    if (source == null)
        return Array.Empty<Texture>();

    // find the first source which provides either the animated or non-animated version.
    retrievalSource = (source as ISkinSource)?.FindProvider(s =>
    {
        if (animatable && s.GetTexture(getFrameName(0)) != null)
            return true;

        return s.GetTexture(componentName, wrapModeS, wrapModeT) != null;
    }) ?? source;

    if (animatable)
    {
        var textures = getTextures(retrievalSource).ToArray();

        if (textures.Length > 0)
            return textures;
    }

    // if an animation was not allowed or not found, fall back to a sprite retrieval.
    var singleTexture = retrievalSource.GetTexture(componentName, wrapModeS, wrapModeT);

    if (singleTexture != null && maxSize != null)
        singleTexture = singleTexture.WithMaximumSize(maxSize.Value);

    return singleTexture != null
        ? new[] { singleTexture }
        : Array.Empty<Texture>();

    IEnumerable<Texture> getTextures(ISkin skin)
    {
        for (int i = 0; true; i++)
        {
            var texture = skin.GetTexture(getFrameName(i), wrapModeS, wrapModeT);

            if (texture == null)
                break;

            if (maxSize != null)
                texture = texture.WithMaximumSize(maxSize.Value);

            yield return texture;
        }
    }

    string getFrameName(int frameIndex) => $"{componentName}{animationSeparator}{frameIndex}";
}
```

Literal rules:

1. **Source selection first.** `retrievalSource` is the first source in the `ISkinSource`
   chain for which *either* `${name}-0` exists (only when `animatable`) *or* `${name}`
   exists. `FindProvider` (`SkinProvidingContainer.cs:88-100`) walks the sources in order and
   descends into `ParentSource` when `AllowFallingBackToParent` is true. The provider check
   for frame 0 uses the single-argument `GetTexture(getFrameName(0))` — i.e. default wrap
   modes, ignoring the wrap modes passed to `GetAnimation` (`:69`).
2. **Frames are `${name}-0`, `${name}-1`, … starting at 0, contiguous, stopping at the
   first missing index** (`:93-107`). There is no upper bound, no gap tolerance, and no
   `@2x`-style suffix handling beyond what `GetTexture` itself does.
3. Frames are read from `retrievalSource` **directly** (`skin.GetTexture(...)`, `:97`), not
   through the `DisableableSkinSource` wrapper — so `AllowTextureLookup` gating and parent
   fallback do not apply per frame.
4. If zero numbered frames were found, the **bare** `componentName` is fetched (`:84`).
5. The separator is a parameter; the default is `"-"`, so `mania-note1-0`, `mania-note1-1`, …

**"Only a single unnumbered file exists"** — the case worth pinning down:

- `mania-note1.png` exists, no `mania-note1-0.png` and no `mania-note1-2x`:
  `FindProvider` matches on the second predicate (`:72`), `getTextures` yields nothing,
  the bare lookup returns one texture → `GetAnimation` `case 1` → **`new Sprite { Texture = ... }`**.
  `looping`, `frameLength`, `applyConfigFrameRate` and `startAtCurrentTime` are all
  **ignored** — they are only read inside the `default:` arm.
- `mania-note1-0.png` exists alone: `getTextures` yields exactly 1 → **still a `Sprite`**,
  and the animation-only parameters are still ignored.
- `mania-note1-0.png` + `mania-note1-1.png`: `SkinnableTextureAnimation` with 2 frames.

Consumers that need to know which came back inspect the runtime type —
`LegacyNotePiece.cs:56-59`, `LegacyBodyPiece.cs:87-88`, `LegacyBodyPiece.cs:113-114`,
`LegacyBodyPiece.cs:129-130`, `LegacyBodyPiece.cs:187`, `LegacyHitExplosion.cs:68`,
`LegacyManiaJudgementPiece.cs:71`.

### 5.4 Frame length

`LegacySkinExtensions.cs:221-240`:

```csharp
/// <summary>
/// The frame length of each frame at a 60 FPS rate.
/// Default frame rate for legacy skin animations.
/// </summary>
public const double SIXTY_FRAME_TIME = 1000 / 60d;

private static double getFrameLength(ISkin source, bool applyConfigFrameRate, Texture[] textures)
{
    if (applyConfigFrameRate)
    {
        var iniRate = source.GetConfig<LegacySetting, int>(LegacySetting.AnimationFramerate);

        if (iniRate?.Value > 0)
            return 1000f / iniRate.Value;

        return 1000f / textures.Length;
    }

    return SIXTY_FRAME_TIME;
}
```

`DefaultFrameLength = frameLength ?? getFrameLength(retrievalSource, applyConfigFrameRate, textures)`
(`:47`).

**No mania legacy call site passes `applyConfigFrameRate: true`.** Every mania `GetAnimation`
call and its effective frame length:

| Site | Call | `animatable` | `looping` | frameLength |
|---|---|---|---|---|
| `ManiaLegacySkinTransformer.cs:79` (gate probe) | `GetAnimation(keyImage, true, true)` | true | true | `1000/60` |
| `ManiaLegacySkinTransformer.cs:198` (judgement) | `GetAnimation(filename, true, true, frameLength: 1000 / 20d)` | true | true | **50 ms** |
| `LegacyNotePiece.cs:102` | `skin.GetAnimation(noteImage, ClampToEdge, ClampToEdge, true, true)` | true | true | `1000/60` |
| `LegacyBodyPiece.cs:56` (probe) | `skin.GetAnimation(lightImage, true, false)` | true | false | `1000/60` |
| `LegacyBodyPiece.cs:61` (light) | `skin.GetAnimation(lightImage, true, true, frameLength: frameLength)` | true | true | `max(1000/60, 170/FrameCount)` |
| `LegacyBodyPiece.cs:85` (body) | `skin.GetAnimation(imageName, wrapMode, wrapMode, true, true, frameLength: 30)` | true | true | **30 ms** |
| `LegacyHitExplosion.cs:41` (probe) | `skin.GetAnimation(imageName, true, false)` | true | **false** | `1000/60` |
| `LegacyHitExplosion.cs:46` | `skin.GetAnimation(imageName, true, false, frameLength: frameLength)` | true | **false** | `max(1000/60, 170/FrameCount)` |
| `LegacyColumnBackground.cs:50` | `skin.GetAnimation(lightImage, true, true, frameLength: 1000d / lightFramePerSecond)` | true | true | `1000 / LightFramePerSecond` |
| `LegacyStageForeground.cs:31` | `skin.GetAnimation(bottomImage, true, true)` | true | true | `1000/60` |

`LegacyColumnBackground` is the only legacy mania component whose animation rate is a
skin.ini value — `LegacyManiaSkinConfigurationLookups.LightFramePerSecond`, whose config
default is `60` (`LegacyManiaSkinConfiguration.cs:47`) and whose decoder clamps a
non-positive value to `24` (`LegacyManiaSkinDecoder.cs:136`). Since the drawable's own
`?? 60` fallback (`LegacyColumnBackground.cs:41`) applies only when the lookup returns
`null`, and `lookupForMania` always returns a bindable for `LightFramePerSecond` on a
`LegacySkin`, an unset ini value yields **60**, not 24.

`skin.ini`'s `AnimationFramerate` (`SkinConfiguration.LegacySetting.AnimationFramerate`) is
therefore **inert for mania legacy components**.

### 5.5 `SkinnableTextureAnimation`

`LegacySkinExtensions.cs:187-219` — a `TextureAnimation` that rebases its playback position
on the animation-start clock:

```csharp
public partial class SkinnableTextureAnimation : TextureAnimation
{
    [Resolved(canBeNull: true)]
    private IAnimationTimeReference? timeReference { get; set; }

    private readonly Bindable<double> animationStartTime = new BindableDouble();

    public SkinnableTextureAnimation(bool startAtCurrentTime = true)
        : base(startAtCurrentTime)
    {
    }

    protected override void LoadComplete()
    {
        base.LoadComplete();

        if (timeReference != null)
        {
            Clock = timeReference.Clock;
            animationStartTime.BindTo(timeReference.AnimationStartTime);
        }

        animationStartTime.BindValueChanged(_ => updatePlaybackPosition(), true);
    }

    private void updatePlaybackPosition()
    {
        if (timeReference == null)
            return;

        PlaybackPosition = timeReference.Clock.CurrentTime - timeReference.AnimationStartTime.Value;
    }
}
```

If no `IAnimationTimeReference` is resolvable, the animation keeps its default clock.

`LegacyBodyPiece` halts the body animation explicitly — `LegacyBodyPiece.cs:85-94`:

```csharp
bodySprite = skin.GetAnimation(imageName, wrapMode, wrapMode, true, true, frameLength: 30)?.With(d =>
{
    if (d is TextureAnimation animation)
        animation.IsPlaying = false;

    d.Anchor = Anchor.TopCentre;
    d.RelativeSizeAxes = Axes.Both;
    d.Size = Vector2.One;
    // Todo: Wrap?
});
```

and drives it from the hold state (`:111-139`): `IsPlaying = isHitting`, `GotoFrame(0)` on
either transition, plus the separate hold-light container which is added to
`Column.TopLevelContainer` on press and removed on release
(`lightContainer.FadeOut(120).OnComplete(d => Column.TopLevelContainer.Remove(d, false))`).
The comment at `:128` records a framework workaround:

```csharp
// The light must be seeked only after being loaded, otherwise a nullref occurs (https://github.com/ppy/osu-framework/issues/3847).
```

### 5.6 What each mania component uses

| Component | Fetch | Why |
|---|---|---|
| `LegacyKeyArea` up/down | `GetTexture(..., ClampToEdge, default)` | keys tile horizontally; a numbered file is *never* tried |
| `LegacyHitTarget` | `GetTexture(targetImage)` | default wrap modes |
| `LegacyStageBackground` left/right | `GetTexture(...)` | — |
| `LegacyStageForeground` bottom | `GetAnimation(bottomImage, true, true)` | — |
| `LegacyNotePiece` (`Note`, `HoldNoteHead`, `HoldNoteTail`) | `GetAnimation(name, ClampToEdge, ClampToEdge, true, true)` | — |
| `LegacyBodyPiece` | `GetAnimation(..., wrapMode, wrapMode, true, true, frameLength: 30)` | wrap mode comes from `NoteBodyStyle` |
| `LegacyHitExplosion` | `GetAnimation(name, true, false, ...)` | additive blending, `GotoFrame(0)` then fade |
| `LegacyColumnBackground` | `GetAnimation(lightImage, true, true, frameLength: 1000d / fps)` | — |
| judgement (`getResult`) | `GetAnimation(filename, true, true, frameLength: 50)` | — |

---

## 6. `Column.AccentColour`

### 6.1 Origin

Declaration — `osu.Game.Rulesets.Mania/UI/Column.cs:59`:

```csharp
public readonly Bindable<Color4> AccentColour = new Bindable<Color4>(Color4.Black);
```

**Default: `Color4.Black`**, both as the bindable's initial value and as the fallback in the
assignment below.

Assignment — `Column.cs:85-91` and `:129-140`:

```csharp
[BackgroundDependencyLoader]
private void load(GameHost host, ManiaRulesetConfigManager? rulesetConfig)
{
    SkinnableDrawable keyArea;

    skin.SourceChanged += onSourceChanged;
    onSourceChanged();
```

```csharp
private void onSourceChanged()
{
    AccentColour.Value = skin.GetManiaSkinConfig<Color4>(LegacyManiaSkinConfigurationLookups.ColumnBackgroundColour, Index)?.Value ?? Color4.Black;

    leftColumnSpacing = skin.GetConfig<ManiaSkinConfigurationLookup, float>(
                                new ManiaSkinConfigurationLookup(LegacyManiaSkinConfigurationLookups.LeftColumnSpacing, Index))
                            ?.Value ?? Stage.COLUMN_SPACING;

    rightColumnSpacing = skin.GetConfig<ManiaSkinConfigurationLookup, float>(
                                 new ManiaSkinConfigurationLookup(LegacyManiaSkinConfigurationLookups.RightColumnSpacing, Index))
                             ?.Value ?? Stage.COLUMN_SPACING;
}
```

So `AccentColour` is literally **`ColumnBackgroundColour` for this column**, i.e. the
skin.ini key `Colour{Column.Index + 1}` (§4.2), defaulting to black. It is recomputed on
every `ISkinSource.SourceChanged` (`Column.cs:90`), and unsubscribed in `Dispose`
(`:155-156`). It is *not* gated: even when the mania legacy gate fails, this lookup still
runs, and a non-legacy transformer may answer it (see below).

Consumers of the same lookup that reach a different transformer implementation:

- `ManiaClassicSkinTransformer.GetConfig` (`Skinning/Legacy/ManiaClassicSkinTransformer.cs:18-36`):
  ```csharp
  var baseLookup = base.GetConfig<TLookup, TValue>(lookup);

  if (baseLookup != null)
      return baseLookup;

  // default provisioning.
  switch (maniaLookup.Lookup)
  {
      case LegacyManiaSkinConfigurationLookups.ColumnBackgroundColour:
          return SkinUtils.As<TValue>(new Bindable<Color4>(Color4.Black));
  }
  ```
  For the classic/retro skins a missing `Colour{n+1}` still yields `Color4.Black`.
- `ManiaTrianglesSkinTransformer.GetConfig` (`Skinning/Default/ManiaTrianglesSkinTransformer.cs:27-49`):
  `Colour{n+1}` missing → `colourSpecial` for the special column, else `colourOdd`
  (`new Color4(94, 0, 57, 255)`) / `colourEven` (`new Color4(6, 84, 0, 255)`) by
  `distanceToEdge % 2 == 0 ? colourOdd : colourEven` — the same parity formula as
  `FallbackColumnIndex`, but inverted naming.
- `ManiaArgonSkinTransformer.GetConfig` (`Skinning/Argon/ManiaArgonSkinTransformer.cs:157-160`
  → `getColourForLayout`, `:167-363`): a hard-coded per-column-count colour table, falling
  back to `colour_special_column = new Color4(169, 106, 255, 255)` (`:122`, `:344-345`).

### 6.2 Every consumer

Direct consumers of `Column.AccentColour` (7 sites):

| # | Site | Use |
|---|---|---|
| 1 | `osu.Game.Rulesets.Mania/UI/Components/DefaultColumnBackground.cs:60-66` | `background.Colour = colour.NewValue.Darken(5); brightColour = colour.NewValue.Opacity(0.6f); dimColour = colour.NewValue.Opacity(0);` |
| 2 | `osu.Game.Rulesets.Mania/UI/Components/DefaultKeyArea.cs:83-92` | `keyIcon.EdgeEffect` glow, `Colour = colour.NewValue.Opacity(0.5f)`, `Radius = 5` |
| 3 | `osu.Game.Rulesets.Mania/UI/Components/DefaultHitTarget.cs:59-68` | `hitTargetLine.EdgeEffect` glow, `Colour = colour.NewValue.Opacity(0.5f)`, `Radius = 5` |
| 4 | `osu.Game.Rulesets.Mania/UI/DefaultHitExplosion.cs:99` | `accentColour = column.AccentColour.GetBoundCopy();` |
| 5 | `osu.Game.Rulesets.Mania/Skinning/Argon/ArgonColumnBackground.cs:62` | `accentColour = column.AccentColour.GetBoundCopy();` |
| 6 | `osu.Game.Rulesets.Mania/Skinning/Argon/ArgonKeyArea.cs:154` | `accentColour = column.AccentColour.GetBoundCopy();` |
| 7 | `osu.Game.Rulesets.Mania/Skinning/Argon/ArgonHitExplosion.cs:62` | `accentColour = column.AccentColour.GetBoundCopy();` |

Indirect consumers — every mania hit object's `AccentColour` is **bound to the column's**.
`Column.OnNewDrawableHitObject` (`Column.cs:166-174`):

```csharp
protected override void OnNewDrawableHitObject(DrawableHitObject drawableHitObject)
{
    base.OnNewDrawableHitObject(drawableHitObject);

    DrawableManiaHitObject maniaObject = (DrawableManiaHitObject)drawableHitObject;

    maniaObject.AccentColour.BindTo(AccentColour);
    maniaObject.CheckHittable = hitPolicy.IsHittable;
}
```

`DrawableHitObject.AccentColour` — `osu.Game/Rulesets/Objects/Drawables/DrawableHitObject.cs:60`:

```csharp
public readonly Bindable<Color4> AccentColour = new Bindable<Color4>(Color4.Gray);
```

(the `Color4.Gray` default is immediately overwritten by the `BindTo` above) and set
generically at `:586` (`AccentColour.Value = colour;`).

Downstream readers of the hit-object-level bindable:

| Site | Use |
|---|---|
| `osu.Game.Rulesets.Mania/Skinning/Default/DefaultNotePiece.cs:60-61, 72-82` | `colouredBox.Colour = accent.NewValue.Lighten(0.9f)`; `EdgeEffect` glow `Lighten(1f).Opacity(0.2f)`, `Radius = 10` |
| `osu.Game.Rulesets.Mania/Skinning/Default/DefaultBodyPiece.cs:24, 48, 52` | `AccentColour.BindTo(drawableObject.AccentColour)` |
| `osu.Game.Rulesets.Mania/Skinning/Default/DefaultBodyPiece.cs:61, 69, 120-121` | the nested body/hitting layer rebinding |
| `osu.Game.Rulesets.Mania/Skinning/Argon/ArgonNotePiece.cs:92` | `accentColour.BindTo(drawableObject.AccentColour);` |
| `osu.Game.Rulesets.Mania/Skinning/Argon/ArgonHoldBodyPiece.cs:22, 49-54` | `AccentColour.BindTo(holdNote.AccentColour)`, `hittingLayer.AccentColour.BindTo(holdNote.AccentColour)` |
| `osu.Game.Rulesets.Mania/Skinning/Argon/ArgonHoldNoteTailPiece.cs:89, 102-103` | `accentColour.BindTo(drawableObject.AccentColour)`; `hittingLayer.AccentColour.UnbindBindings(); hittingLayer.AccentColour.BindTo(holdNoteTail.HoldNote.AccentColour);` |
| `osu.Game.Rulesets.Mania/Skinning/Argon/ArgonHoldNoteHittingLayer.cs:14, 28` | glow driven by `AccentColour` |

**The legacy mania drawables do not read `AccentColour` at all.** None of
`LegacyColumnBackground`, `LegacyKeyArea`, `LegacyHitTarget`, `LegacyNotePiece`,
`LegacyBodyPiece`, `LegacyHitExplosion`, `LegacyBarLine` or `LegacyStageBackground`
contains the identifier `AccentColour`. Their colours come from skin.ini colour keys
(`Colour{n+1}`, `ColourLight{n+1}`, `ColourColumnLine`, `ColourJudgementLine`,
`ColourBarline`, `ColourBreak`) or are hard-coded. So for a fully legacy-skinned playfield,
`Column.AccentColour` is computed, maintained and bound to hit objects, but **visually
inert** — it only becomes visible when a `Default*` or `Argon*` component is in the tree
(i.e. exactly when the gate failed, or when the user is on Argon/Triangles).

`Column.AccentColour` is also the reason `ManiaClassicSkinTransformer` and
`ManiaTrianglesSkinTransformer` bother to synthesise `ColumnBackgroundColour`: it is the
only path by which those skins colour the default key area / hit target / background.

---

## 7. Explicit ambiguities and hazards found in the source

1. **Two gates, two predicates, one ungated path.** `IsProvidingLegacyResources`
   (font **or** key texture) gates the global HUD container; `isLegacySkin && hasKeyTexture`
   (key texture **and** legacy version) gates the 11 mania components;
   `SkinComponentLookup<HitResult>` is **not gated at all**
   (`ManiaLegacySkinTransformer.cs:93, 138, 142`).

2. **`hasKeyTexture` probes column 0 but falls back to `mania-key1`**
   (`ManiaLegacySkinTransformer.cs:78`). The fallback filename's digit does not match the
   queried index.

3. **`HitTarget` returning `Drawable.Empty()` is not a gate failure**
   (`ManiaLegacySkinTransformer.cs:150-153`). It is a deliberate ordering hack; the real
   legacy hit target is built inside `LegacyStageBackground` (`:60-63`).

4. **`StagePaddingTop` / `StagePaddingBottom` are dead for legacy skins.** They are in the
   enum (`LegacyManiaSkinConfigurationLookup.cs:45-46`), consumed by `Stage.cs:176-177`, and
   have **no arm** in `lookupForMania`, so they hit `return null;` at `LegacySkin.cs:308`.
   Only `ManiaArgonSkinTransformer.cs:146-148` supplies them. There is no skin.ini key.

5. **`ExplosionImage` and `HoldNoteLightImage` are fetched with a column index but resolved
   globally** (`LegacySkin.cs:169, 224` → literal `"LightingN"` / `"LightingL"`). Only
   `LightingNWidth` / `LightingLWidth` are per-column arrays. A skin that writes
   `LightingN0:` gets nothing.

6. **Colour keys are 1-based while image keys are 0-based**, from the same absolute index:
   `$"Colour{maniaLookup.ColumnIndex + 1}"` (`LegacySkin.cs:179`) vs
   `$"NoteImage{maniaLookup.ColumnIndex}"` (`:209`).

7. **`LegacyStageBackground` uses a stage-local column index** while every other per-column
   consumer uses the absolute `Column.Index` (`LegacyStageBackground.cs:66-67` vs
   `LegacyManiaColumnElement.cs:45`). On dual-stage beatmaps `Colour{n}` therefore resolves
   differently for the stage background than for `Column.AccentColour`.

8. **A single resolved file always yields a `Sprite`, and `looping` / `frameLength` are then
   ignored** (`LegacySkinExtensions.cs:39-40`). A one-frame animation and a static image are
   indistinguishable downstream except by runtime type.

9. **`skin.ini` `AnimationFramerate` never applies to mania** — no mania call site passes
   `applyConfigFrameRate: true` (`LegacySkinExtensions.cs:227-240`).

10. **`NoteBodyStyle` default flips on `Version`** (`LegacySkin.cs:202-205`): `< 2.5` →
    `Stretch`; `>= 2.5` → `RepeatBottom`. The wiki-documented `Repeat = 1` is commented out
    of the enum (`LegacyManiaSkinConfiguration.cs:93-103`) but `Enum.TryParse` still accepts
    the literal `"1"` / `"Repeat"`, producing an undefined enum value that lands in
    `LegacyBodyPiece`'s `default:` arm.

11. **`FrameCount`-derived frame lengths use a magic 170 ms**
    (`LegacyHitExplosion.cs:44`, `LegacyBodyPiece.cs:59`):
    `frameLength = Math.Max(1000 / 60.0, 170.0 / tmpAnimation.FrameCount)`. The number 170 is
    unexplained in the source, and the probe animation is thrown away and re-queried.

12. **The `[BackgroundDependencyLoader]` ordering assumption is unverified here** — see the
    call-out in §3.2.

13. **`LegacyManiaJudgementPiece` reads `HitPosition`/`ScorePosition` with `?? 0`**
    (`LegacyManiaJudgementPiece.cs:52-53`), i.e. the *drawable's* fallback is 0, not the
    config's `DEFAULT_HIT_POSITION` (`(480 - 402) * 1.6f` = 124.8) / `ScorePosition`
    (`300 * 1.6f` = 480) — `LegacyManiaSkinConfiguration.cs:24, 43`. The config defaults only
    apply when the lookup succeeds.

14. **`LegacyHitExplosion` does not loop.** Both of its `GetAnimation` calls pass
    `looping: false` (`LegacyHitExplosion.cs:41, 46`), while the note, hold body, hold light,
    stage foreground and column light all pass `looping: true`. The hold light's *probe* call
    also passes `false` (`LegacyBodyPiece.cs:56`), but the real query passes `true`
    (`:61`) — the probe's `looping` argument is irrelevant, only its `FrameCount` is read.
