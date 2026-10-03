# osu! 成绩图 · 图标提示词

只含两组：**判定图标**（MAX / 300 / 200 / 100 / 50 / MISS）和 **mod 徽章**。
模板里这两组图标的显示尺寸都是 **40 × 40 px**，下面所有提示词按 512×512 出图、后期缩到 40px。

---

## 0. 出图通用规范

| 项目 | 要求 |
|---|---|
| 画布 | 正方形 **512×512**（缩到 40px 留足余量） |
| 背景 | **不要指望模型出真透明** —— 见下面第 4 节 |
| 一图一个 | 不要在单张图里排 6 个图标再裁切，尺寸和基线会不一致 |
| 构图 | 图形居中，四周留 **10%** 内边距 |
| 描边 | 必须有深色描边（约画布宽度 2%）。成绩图会叠在谱面背景上，没描边的图标会糊进背景 |
| 禁止 | 投影、发光、水印、多图标拼板、额外文字 |

---

## 1. 判定图标（6 个，逐个生成）

### 基础提示词 — 直接复制，替换 `{字符}` 和两个颜色

```
A single flat vector game icon on a fully transparent background.

The icon is the bold stylized text "{字符}" drawn in a heavy rounded geometric
sans-serif with very thick strokes and tight letter spacing.
Fill: vertical gradient from {浅色} at the top to {深色} at the bottom.
Outline: crisp near-black outline about 2% of the canvas width, rounded joins.
Highlight: a thin bright line along the upper edge of the letterforms.

Style: chunky arcade game UI, high contrast, clean vector shapes, flat, no
texture, no bevel. Must stay legible when scaled down to 40 pixels tall.
Composition: perfectly centered, 10% margin on every side. Square 512x512.

No background, no frame, no drop shadow, no glow, no watermark, no caption,
no extra symbols, no additional characters.
```

### 6 个变体

| 替换 `{字符}` | `{浅色}` → `{深色}` | 判定 |
|---|---|---|
| `MAX` | `#FFE07A` → `#FFCC22` | MAX（mania 的彩 300 / 320） |
| `300` | `#8ECBF0` → `#4FA3E3` | 300 |
| `200` | `#9AD4E8` → `#5FB4CC` | 200 |
| `100` | `#B5DC77` → `#8CC63F` | 100 |
| `50` | `#EDC77A` → `#D9A441` | 50 |
| `X` | `#F09090` → `#E45B5B` | MISS。osu! 里 Miss 就是画成一个 X |

> 如果你想让 Miss 直接显示字母而不是 X，把 `{字符}` 换成 `MISS`。但 `MISS` 有 4 个字母，缩到 40px 后笔画会糊成一团，**建议用 X**。

### 负面提示词

```
blurry, photorealistic, 3d render, bevel, emboss, drop shadow, glow,
background, frame, border, caption, watermark, signature, multiple icons,
inconsistent weight, low contrast, thin strokes, extra digits, missing digits,
wrong characters, mirrored text
```

**再补一条**（针对文字渲染出错，把常见错误形式直接列进去）：

```
"30O", "3OO", "3O0", "O" used for zero, "l" used for one, extra letters,
garbled text, misspelled glyphs
```

---

## 2. mod 徽章

### 基础提示词 — 替换 `{字母}` 和两个颜色

```
A single flat vector game badge icon on a fully transparent background.

A rounded square badge with corner radius about 20% of its width, filled with
a vertical gradient from {浅色} at the top to {深色} at the bottom, with a crisp
near-black outline about 2% of the width.

Centered inside the badge: the two bold uppercase letters "{字母}" in a heavy
geometric sans-serif, pure white, with a thin dark outline. The letters are
perfectly centered both horizontally and vertically and occupy about 60% of
the badge width.

Style: chunky arcade game UI, high contrast, clean vector shapes, flat, no
texture, no bevel. Must stay legible when scaled down to 40 pixels.
Composition: badge centered, 10% margin on every side. Square 512x512.

No background, no drop shadow, no glow, no watermark, no caption,
no additional text.
```

### 常用 mod

| 替换 `{字母}` | `{浅色}` → `{深色}` | 模组 |
|---|---|---|
| `HD` | `#E8D27A` → `#C9A227` | Hidden |
| `DT` | `#B39AE0` → `#7E57C2` | Double Time |
| `HR` | `#F09090` → `#D0483F` | Hard Rock |
| `FL` | `#8A8FD0` → `#4A4FA8` | Flashlight |
| `EZ` | `#9AD8A0` → `#5FAE6A` | Easy |
| `NF` | `#A8C4D8` → `#6E93AE` | No Fail |
| `HT` | `#A0C8E0` → `#5E8FB0` | Half Time |
| `SO` | `#C8B8A0` → `#8A7660` | Spun Out |

### 负面提示词

```
blurry, photorealistic, 3d render, bevel, emboss, drop shadow, glow,
background, extra text, caption, watermark, signature, multiple badges,
inconsistent corner radius, inconsistent weight, low contrast, thin strokes,
garbled letters, wrong letters, lowercase
```

> **mania 特有情况**：mania 还有键数模组（`1K`–`18K`），徽章里是**数字 + 字母**的组合（如 `4K`、`7K`）。要出这批就把 `{字母}` 换成 `4K` 这类，同时把上面那条"数字渲染出错"的负面提示词也加上。

> 上面这些颜色是社区习惯值，**不是 osu! 官方精确色值**。要严格对齐游戏内配色就给我一张截图，我取色后重写这张表。

---

## 3. 让 6 个图标保持一致（这组图的真正难点）

单张好看不难，**6 张放一起粗细一致**才难。三个办法，按可靠性排序：

1. **锁种子（seed）** —— 工具支持就用同一个 seed，只改字符和颜色。这是最有效的一招。
2. **图生图（img2img）** —— 先生成 `300` 那张，挑一张最满意的当参考图，其余 5 张用低重绘强度（0.3–0.4）基于它生成。风格会被强制拉齐。
3. **同批生成** —— 6 个变体在一次会话里连着跑完，别分几天做。

**验收方法**：6 张全部生成后，在 PS 里并排缩到 40px，眯眼看。哪一张明显比别人粗或细，单独重跑那一张。

---

## 4. 透明底怎么拿到（别在这上面浪费时间）

多数模型输出的"透明背景"其实是**白底**，或者**画着灰白棋盘的假透明**。直接拿去用会带一块白方块盖住谱面背景图。

**可靠做法**：在提示词里主动要一个**纯色背景**，后期一键抠掉。把基础提示词里的 `on a fully transparent background` 换成：

```
on a solid flat #FF00FF magenta background
```

品红在图标里几乎不会自然出现，后期在 PS 里用「选择 → 色彩范围」点一下品红就能整块删掉，比魔棒干净得多。

**不要用纯白或纯黑做键出背景** —— 图标里有白色高光、黑色描边，抠色会连带把图标本体啃掉一块。

---

## 5. 交付规范

- 格式：**PNG，透明底，512×512**
- 文件名**直接用模板里的图层名**，我接手时不用猜：
  - 判定图标：`count_max` / `count_300` / `count_200` / `count_100` / `count_50` / `count_miss`
  - mod 徽章：`mod_1` … `mod_6`（按你实际要的 mod 顺序命名也行，但要给我一份对照表）
- 交付前自查：
  - [ ] 真透明，不是白底
  - [ ] 缩到 40px 还能认出形状
  - [ ] 6 张判定图标放一起，粗细和视觉重量一致
  - [ ] 描边宽度一致

---

## 备用方案

如果 AI 出的这几组反复对不上（文字错、粗细不齐、抠不干净），**这些图标我可以用 Photoshop 脚本直接画出来**：精确色值、统一描边、真透明底、一次跑完 6 个，零版权风险。这两组图形本质就是"粗体字形 + 渐变 + 描边"，脚本做这类东西是确定性的，不靠抽卡。需要就说一声。
