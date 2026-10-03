# 谱面属性图标 · 提示词（BPM / OD / HP · 简约高级风）

三个图标，用在左栏谱面信息里，**实际显示尺寸 32 × 32 px**。按 512 × 512 出图。

> 星级不需要这组图标了——它已经改成整条的星级色阶条（`star_strip.js` 生成）。

---

## 0. 先说一个硬约束：**"高级感"不等于"细线"**

图标最终只有 **32 × 32 px**。这决定了笔画粗细的下限：

| 笔画占画布 | 512 源图里 | 缩到 32px 后 | 结果 |
|---|---|---|---|
| 1.5% | 8px | 0.5px | ❌ 直接消失，剩一团灰 |
| 3% | 15px | 1px | ⚠️ 勉强，抗锯齿后发虚 |
| **5%** | **26px** | **1.6px** | ✅ 清晰，且仍是"线"的观感 |
| 8% | 41px | 2.6px | ✅ 很稳，但开始偏"粗" |

**所以这里有一个反直觉的结论**：提到"简约高级"，很多人的第一反应是"把线画细"。**但在 32px 下，1px 的线是不存在的。**

这个尺寸下"简约高级"的正确配方是三件事：

1. **减少元素数量** —— 一个图标只讲一件事，不要加装饰
2. **加大留白** —— 图形占画布 62–66%，四周留足空间
3. **统一笔画** —— 三个图标用同一个笔画宽度，这是"成套感"的唯一来源

**而不是**：把线画细、加很多细节、用复杂的曲线。

---

## 1. 出图规格

| 项目 | 要求 |
|---|---|
| 画布 | **512 × 512** |
| 图形占比 | **62–66%**，居中，四周留 17–19% |
| 笔画 | **统一为画布宽度的 5%**（约 26px），圆头圆角 |
| 造型 | **纯线条勾勒**，只有一个例外：OD 的中心圆点可以是实心 |
| 颜色 | **单一平色**，无渐变、无高光、无投影 |
| 禁止 | 描边（外圈黑边）、底色块、圆角方底、任何"游戏徽章"式的元素 |

**和前面几组的关键区别**：判定图标和 mod 徽章是**实心色块 + 深色描边 + 渐变**的游戏风格。**这一组要反过来**——纯线条、单一颜色、没有外框。它们应该是"标签"，不是"按钮"。

---

## 2. 主提示词（复制，替换 `{图形}` 和 `{颜色}`）

```
A single minimal line-art UI icon, centred on a fully transparent background.

The icon is a {图形}, drawn entirely as clean outlines with ONE uniform stroke
weight of about 5% of the canvas width — every line in the icon is exactly the
same thickness. The stroke has rounded caps and rounded joins. There are no
filled areas, no flat colour blocks, no shading, no highlights.

Composition is precise and symmetrical, with generous negative space: the
pictogram occupies about 64% of the canvas and sits perfectly centred, leaving
roughly 18% empty margin on every side.

Colour: a single flat {颜色}. Absolutely no gradient, no glow, no drop shadow,
no outline around the shape.

Style: refined and restrained premium UI iconography — the kind of pictogram a
high-end app or a luxury brand would use. Calm, precise, geometric, confident.
Not playful, not cartoonish, not bulky, not skeuomorphic.

The icon must stay crisp and legible when scaled down to 32 pixels.
Square 512x512. No background, no frame, no ring, no rounded-square backing,
no text, no numbers, no extra symbols — exactly one pictogram and nothing else.
```

---

## 3. 三个图标

| 文件 | `{图形}` | 说明 |
|---|---|---|
| `bpm.png` | `metronome: a tall narrow isosceles trapezoid standing upright, with a single straight pendulum rod rising through its centre and a small filled circle as the counterweight near the top of the rod` | 你点名的。**节拍器唯一的风险是容易画复杂**——如果缩到 32px 认不出，退化成 `a single straight pendulum rod pivoted at the top, with a small weight and a shallow arc above the pivot`（只留斜杆 + 支点弧） |
| `od.png` | `target: two concentric circles with a single filled dot at the exact centre` | 靶心。**外圈大、内圈小、中心一个实心点**——三个元素就够了，不要加十字准星 |
| `hp.png` | `heart: a clean symmetrical heart outline with two equal rounded lobes and a sharp point at the bottom` | 心形。**必须对称**，两瓣等大、底部尖角居中 |

**`{颜色}` 建议**：用模板里已有的灰 `#A8B2C4`。三个图标**必须同色**——这一组是标签，不是各带身份色的内容。

---

## 4. 负面提示词

```
blurry, photorealistic, 3d render, bevel, emboss, drop shadow, glow, reflection,
gradient, background, frame, border, rounded square, badge, button, tile, plate,
caption, watermark, signature, text, letters, numbers, multiple icons,
icon set sheet, grid of icons, filled shapes, thick outlines, cartoon, playful,
cluttered, ornate, sketch, hand-drawn, uneven stroke width, calligraphy
```

> 特别加 `rounded square` / `badge` / `button` / `plate` —— 模型看到"icon"这个词很容易自动加一个圆角方底。**这一组要的恰恰是裸线条，没有底。**

---

## 5. 让三个像一套

这一组的成套感**完全靠笔画宽度统一**，因为形状本身毫无关系（节拍器、靶心、心）。

1. **锁种子（seed）** —— 同一 seed，只改 `{图形}`。
2. **图生图（img2img）** —— 先出 `hp.png`（心形最简单、最容易判断笔画是否合适），把它当参考，其余两个用重绘强度 **0.30–0.40** 生成。
3. **主提示词里那三个数字一个字都别改**：`5% stroke`、`64% occupancy`、`18% margin`。改任何一个，三个图标就不成套了。

**验收**：三个并排缩到 **32 × 32 px**。

- [ ] 三个的**笔画粗细**看起来一致吗（这是第一位的）
- [ ] 32px 下还认得出是节拍器 / 靶心 / 心吗
- [ ] 有没有哪个图形比别人大或小（视觉重量应接近）
- [ ] 有没有被模型擅自加上圆角方底

---

## 6. 透明底

把 `on a fully transparent background` 换成
`on a solid flat #FF00FF magenta background`，后期用「选择 → 色彩范围」抠掉。

**注意**：这组图标是**细线**，抠底的容差要收紧（建议 15–20）。容差开大了会把线条边缘一起吃掉，线会变细、甚至断开。

---

## 7. 交付

- 格式：**PNG，透明底，512 × 512**
- 文件名对应模板图层名：

| 文件 | 对应图层 | 字段 |
|---|---|---|
| `bpm.png` | `_deco_attr_bpm` | BPM |
| `od.png` | `_deco_attr_od` | OD |
| `hp.png` | `_deco_attr_hp` | HP |

- 自查：
  - [ ] 真透明，没被加上圆角方底
  - [ ] 三个笔画粗细一致
  - [ ] 缩到 32px 仍可辨认
  - [ ] 单一颜色，无渐变无投影
  - [ ] 图形居中，四周留白均匀

---

## 附：如果想更"高级"一点

上面这套是**稳妥版**。如果你愿意承担小尺寸风险，可以再往前走一步：

- **笔画压到 4%**（512 里 20px → 32px 下 1.25px）：更纤细，但已经接近极限
- **颜色改成比标签更低一档的灰**（如 `#6E7A90`）：更含蓄，但对比度下降
- **图形占比加大到 72%**：更饱满，但留白的高级感会减弱

**这三条任意一条都会削弱 32px 下的可读性**，而且三条叠加基本必坏。要试就一次只动一条，并且**一定要在 32px 下实测**再决定。
