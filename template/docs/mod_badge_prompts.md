# mod 徽章 · 提示词（带图案版）

每个徽章 = **图案 + 两位代号**。DT / HT 另外还有一行**倍率**——但那一行**不能画进图里**，原因见第 6 节。

---

## 1. 出图规格

| 项目 | 要求 |
|---|---|
| 画布 | **512 × 512**，正方形（和其他图标组统一） |
| 徽章本体 | 横向圆角矩形，占画布 **90% 宽 × 64% 高**，居中 → 比例约 **1.4 : 1** |
| 圆角 | 本体宽度的 **20%** |
| 描边 | 近黑 `#0C0A09`，约画布宽 **1.6%**（8px @512），圆角连接 |
| 内容 | **图案在左、代号在右**，两者垂直居中，整体占本体宽度约 **72%** |
| 颜色 | 图案与字母都是**纯白**，带极细深色描边 |
| 禁止 | 投影、外发光、纹理、噪点、多徽章拼版 |

**关键比例检查**：图案的高度要和字母的**视觉高度相当**。图案做成小点缀、字母做很大，两者就不成套了。

---

## 2. 主提示词（复制，替换 `{图案}` `{代号}` `{浅色}` `{深色}`）

```
A single flat vector game badge icon, centred on a fully transparent
background.

The badge is a horizontal rounded rectangle occupying 90% of the canvas width
and 64% of its height, with a corner radius of about 20% of its width, filled
with a smooth vertical gradient from {浅色} at the top to {深色} at the bottom,
enclosed by a crisp near-black outline about 1.6% of the canvas width with
rounded joins.

Inside the badge there are exactly two elements, side by side, vertically
centred, together occupying about 72% of the badge width:
- on the left, a bold solid pictogram of {图案}, filled pure white;
- on the right, the two heavy uppercase letters "{代号}" in a bold geometric
  sans-serif, filled pure white.
The pictogram and the letters must be optically balanced — the pictogram is
roughly the same visual height as the letters, with a clear gap between them.

Style: clean flat vector game UI, chunky, high contrast, no texture, no bevel,
no drop shadow, no inner shadow. The whole thing must stay clearly legible when
scaled down to 80 x 56 pixels.

Square 512x512. No background, no frame outside the badge, no watermark, no
caption, no extra symbols, exactly one pictogram and exactly two letters.
```

---

## 3. 每个 mod 的图案与配色

`{图案}` 一列是给模型的英文描述，**同一个 mod 每次出图都用同一句**，不要换说法，否则形状会飘。

| `{代号}` | `{图案}` | `{浅色}` → `{深色}` | 为什么用这个图案 |
|---|---|---|---|
| `HD` | `an eye with one bold diagonal slash across it` | `#E8D27A` → `#C9A227` | Hidden = 被遮住的眼睛 |
| `DT` | `two thick chevrons side by side, both pointing right` | `#B39AE0` → `#7E57C2` | 双箭头 = 加速。**两个**箭头是关键 |
| `HT` | `a single thick chevron pointing right` | `#A0C8E0` → `#5E8FB0` | **一个**箭头 = 半速。和 DT 只差箭头数量，成套 |
| `HR` | `a thick arrow pointing straight up` | `#F09090` → `#D0483F` | 属性上调 |
| `EZ` | `a thick arrow pointing straight down` | `#9AD8A0` → `#5FAE6A` | 属性下调。和 HR 成对 |
| `FL` | `a torch with a wide triangular light beam` | `#8A8FD0` → `#4A4FA8` | Flashlight |
| `NF` | `a shield` | `#A8C4D8` → `#6E93AE` | No Fail |
| `SO` | `a spiral` | `#C8B8A0` → `#8A7660` | Spun Out |
| `SD` | `a skull` | `#B0B4C4` → `#5A5E70` | Sudden Death |
| `PF` | `a five-pointed star` | `#E8D27A` → `#C9A227` | Perfect |

> **DT 和 HT 是一对**：两个箭头 vs 一个箭头，同一形状语言、只差数量。**这两张一定要用同一个 seed 或同一批出**，否则箭头粗细和角度会对不上。

> **键数模组**（mania 的 `1K`–`18K`）：图案用 `a small keyboard rectangle divided into vertical key slots`，代号换成 `4K` 这类。**注意这是「数字+字母」**，AI 渲染数字容易出错，出完必须逐个核对。

---

## 4. 负面提示词

```
blurry, photorealistic, 3d render, bevel, emboss, drop shadow, inner shadow,
glow, background, frame, caption, watermark, signature, multiple badges,
badge set sheet, grid of badges, extra symbols, extra letters, lowercase,
thin strokes, low contrast, gradient mesh, texture, noise
```

**再补一条**（防止字母渲染出错，这是文生图最常翻车的地方）：

```
"HO" instead of "HD", "H0", "DT" misspelled, "HT" rendered as "Ht" or "H7",
garbled letters, mirrored text, distorted letterforms, wrong chevron count
```

> 特别注意 `badge set sheet` / `grid of badges`——模型很喜欢一次把 8 个徽章排成一张图，那样切出来的尺寸和基线全部对不齐。

---

## 5. 让整组像一套

1. **锁种子（seed）** —— 同一 seed，只改 `{图案}`、`{代号}`、配色。最有效。
2. **图生图（img2img）** —— 先出 `DT`，挑最满意的当参考，其余用重绘强度 **0.25–0.35** 生成。
3. **一次跑完** —— 别分几天做。
4. **形状语言只改「数量」不改「风格」** —— DT/HT 的箭头、HR/EZ 的上下箭头，都是"同一形状反过来 / 少一个"，这是成套感的主要来源。

**验收**：整组缩到 **80 × 56 px** 并排看。

- [ ] 所有徽章的圆角、描边粗细一致吗
- [ ] 图案和字母的视觉高度相当吗（不是图案很小、字母很大）
- [ ] DT 是两个箭头、HT 是一个箭头吗
- [ ] 缩到 80px 后，图案还认得出是什么吗

---

## 6. ⚠️ 倍率（x1.5）**不要画进图里**

你写的是「下面并且写着 x1.5（可能会有其他数字，因为 lazer mod 可自定义）」。

**正因为它是可变的，就绝不能烤进图片。** 理由：

- osu!lazer 的 DT 倍率可以是 1.1–2.0 之间任意值，HT 同理。**穷举不完**，不可能为每个值出一张图。
- 如果图里烤死 `x1.5`，玩家用 x1.8 时就会显示错误的数字——**比不显示还糟**。

**正确做法**：徽章图案只画「图案 + 代号」这一行；**倍率单独做一个文字图层**，插件按数值填字符串。

所以模板这边我会这样搭：

```
📁 mods_block
   mod_1         ← 徽章图（图案 + 代号）
   mod_1_mult    ← 文字图层，插件填 "x1.5"
   mod_2
   mod_2_mult
   …
```

**画图时请把下方留白留出来**：徽章本体占画布 64% 高度并**居中**，即上下各留 18%。下面这 18% 就是给倍率文字的位置——**但不要在里面画任何东西**。

只有 DT / HT / 以及 lazer 的自定义速率模组需要倍率；HD、NF、FL 这些没有倍率，对应的 `mod_*_mult` 图层插件会隐藏。

---

## 7. 透明底

跟其他几组一样：把 `on a fully transparent background` 换成
`on a solid flat #FF00FF magenta background`，后期用「选择 → 色彩范围」抠掉。

**这组尤其要注意**：徽章本身有大量纯白（图案和字母都是白的），**绝不能用白色做键出背景**。

---

## 8. 交付

- 格式：**PNG，透明底，512 × 512**
- 文件名：**按模组名**（沿用你现在这套）

| 文件 | 代号 | 图案 |
|---|---|---|
| `mod_hd.png` | HD | 带斜杠的眼睛 |
| `mod_dt.png` | DT | 双箭头 |
| `mod_ht.png` | HT | 单箭头 |
| `mod_hr.png` | HR | 上箭头 |
| `mod_ez.png` | EZ | 下箭头 |
| `mod_fl.png` | FL | 火炬 |
| `mod_nf.png` | NF | 盾牌 |
| `mod_so.png` | SO | 螺旋 |
| `mod_sd.png` | SD | 骷髅 |
| `mod_pf.png` | PF | 星星 |

- 自查：
  - [ ] 真透明，不是白底
  - [ ] 缩到 80 × 56 后图案仍可辨认
  - [ ] 整组并排，圆角和描边一致
  - [ ] 徽章下方 18% 是空的（留给倍率文字）
  - [ ] DT 两个箭头 / HT 一个箭头
