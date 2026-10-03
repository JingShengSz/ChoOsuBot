# Mania 离线渲染器 — 原理说明

> 对应实现：`mania_render/`。凡与 osu!lazer 行为有关的部分，均标注源码依据（仓库：`ppy/osu` / `osu-master`，参考文件在 `osu-gh/yumu-bot-src/`）。

---

## 1. 目标与边界

| 项 | 约定 |
|---|---|
| 模式 | 仅 osu!mania |
| 画幅 | 1920×1080（16:9） |
| 产出 | 离线 MP4（H.264 + AAC）；架构预留 Web/服务器（D），首版不做 |
| 输入主路径 | **谱面 ID**（拉 `.osu` + 音频 + 背景）；可选 `--osu-file` / `--audio` 本地覆盖 |
| 皮肤 | `.osk`（或解包目录）；`skin.ini` + 可选 Layout JSON |
| 滚动速度 | ScrollSpeed=30 → UI 显示 382ms（`11485/30`） |
| 片段 | 秒、闭区间 `[起, 止]`；`止` 越过谱面时长则报错 |
| 键数 | 跟谱面 CS；皮肤无对应 `[Mania]` 时回落次选；**>10K 拒绝渲染** |

---

## 2. 数据链路（按 ID）

```
谱面ID (bid)
  ├─ https://osu.ppy.sh/osu/{bid}          → .osu 全文（yumu-bot 同款接口）
  ├─ sayobot get_beatmaps?b= / ?h=md5      → 元数据（sid、星级、状态…）
  ├─ [General] AudioFilename               → sayobot /files/{sid}/{name} 音频
  └─ [Events] 0,0,"bg.jpg"                 → 同上拉背景
```

- **AudioFilename / 背景文件名必须以 `.osu` 为准**，不能写死 `audio.mp3`。
- 官方 `beatmapsets/{sid}/download` 需登录；镜像用 sayobot（`files/` 直链或 `download/mini` 再解压）。
- 回放 `.osr` 可选：`--replay`；无回放走 FC Sim。

缓存：`cache/osu/`、`cache/audio/`、`cache/renders/`。

---

## 3. `.osu` 解析（`osu_file.py`）

### 3.1 HitObject 类型位（对齐 `HitObjectType`）

| 位 | 含义 | 本项目 |
|---|---|---|
| `1<<0` (1) | Circle | mania **单点（rice）** |
| `1<<1` (2) | Slider | （mania 基本不用） |
| `1<<3` (8) | Spinner | 忽略 |
| `1<<7` (128) | HoldNote | **长条（LN）** |

判别顺序：先 LONGNOTE 再 CIRCLE（type 可能同时置位）。

- LN 头 = `time`；尾 = extras 第一段 `endTime`（`parts[5].split(":")[0]`）。
- 列号：`column = x * keys / 512` 截断到 `[0, keys)`（`ManiaBeatmapAttributes`）。

### 3.2 TimingPoints

- **红线**（uninherited=1）：`bpm = 60000 / beatLength`（`Timing.kt`）。
- 绿线：SV，本版滚动不用 Multiplier，只取红线做 BPM 显示。
- **BPM Counter** = 当前时刻之前最近一条红线的 BPM（多段变速会随时间跳变）。

### 3.3 难度字段

`CircleSize`→键数 CS、`OverallDifficulty`→OD（判定窗）、`HPDrainRate`、`ApproachRate`。

---

## 4. `.osr` 回放（`osr.py`）

### 4.1 文件结构

```
byte  mode (3=mania)
int32 version (lazer >= 30000000)
string  beatmap MD5     ← 0x0b + ULEB128 长度 + UTF-8
string  username
string  replay hash
u16×6  300/100/50/geki/katu/miss
int32  score
u16    max combo
bool   perfect
int32  mods
string  HP graph
datetime timestamp
byte[]  LZMA 压缩动作帧
int32/64  online score id
（lazer）byte[]  LZMA JSON 元数据
```

字符串不是 4 字节定长，是 **`0x0b` + ULEB128**（`SerializationReader`）。

### 4.2 动作帧

LZMA 解压后为 `w|x|y|z, …`（逗号分隔）：

| 字段 | 含义（mania） |
|---|---|
| `w` | 与上一帧的 **Δms**（累加成绝对时间） |
| `x` | **20-bit 键位掩码**（bit0=第1列…bit19） |
| `y` | 忽略 |
| `z` | 忽略 |

- 丢掉 `-12345`（RNG 种子）与 `(256,-500)` 哨兵帧。
- 掩码 `0→1` = **Press**；`1→0` = Release。
- 版本 &lt;5 的谱面可能有 +24ms 偏移（`EARLY_VERSION_TIMING_OFFSET`）。

### 4.3 从回放推 HUD

| 量 | 算法 |
|---|---|
| CPS | 滑动 1000ms 内 **Press** 次数（不含松开） |
| Combo | 按物件时间轴模拟判定（见 §8） |
| 判定误差 δ | `press − note.StartTime`（mania 单点 `EndTime==StartTime`） |

---

## 5. 皮肤系统（`skin.py`）

### 5.1 `skin.ini` `[Mania]`（`LegacyManiaSkinDecoder`）

| 键 | 解码 |
|---|---|
| `HitPosition` | `(480 - clamp(y,240,480)) × 1.6` → **离底距离**（768 空间） |
| `ColumnWidth` | 值 × 1.6（`parseArrayValue` 默认缩放） |
| `ColumnLineWidth` | **不** ×1.6 |
| `ComboPosition` / `ScorePosition` | 值 × 1.6（自顶） |
| `WidthForNoteHeightScale` | 值 × 1.6（note 高度参考宽） |
| `NoteImage{n} / {n}H / {n}L / {n}T` | note / LN头 / LN身 / LN尾 |
| `UpsideDown` / `KeysUnderNotes` / `JudgementLine` | 开关 |

行尾 `//` 注释必须剥掉（含中文注释皮肤）。

多段 `[Mania]`（Keys:4 / Keys:7）按 **谱面键数** 选块。

### 5.2 Layout JSON（lazer 皮肤布局，**不是** `skin.json`）

包内三选一文件名（枚举 `GlobalSkinnableContainers`）：

- `MainHUDComponents.json`（全屏 HUD，本项目主用）
- `Playfield.json`（相对舞台）
- `SongSelect.json`（忽略）

结构：`SkinLayoutInfo → DrawableInfo[global|mania] → SerialisedDrawableInfo[]`

字段：`Type`（CLR 全名）、`Position/Rotation/Scale/Width/Height`、`Anchor/Origin`、`UsesFixedAnchor`、`Settings`、`Children`。

**Anchor 整型（磁盘 JSON 实证）**：x=1|2|4（左|中|右），y=8|16|32（上|中|下）：

| | L | C | R |
|---|---|---|---|
| **T** | 9 | 10 | 12 |
| **M** | 17 | 18 | 20 |
| **B** | 33 | 34 | 36 |

### 5.3 贴图加载优先级

根目录同名文件 **优先于** `!Extras/` 色包（否则 note 全被覆盖成同色）。

### 5.4 皮肤回落

```
默认皮肤（现 owc，待换 1–18K）
  └─ 无该键数 [Mania] → 次选 boj pl0x 1–10K
       └─ 键数 >10 → 直接报「暂不支持」
```

### 5.5 必选 HUD（6 件）

ComboCounter、ClicksPerSecondCounter、SongProgress、BeatmapAttributeText、BPMCounter、**AccuracyCounter**。

- Layout JSON 有 → 按 JSON 摆放；同类多份 **Legacy\* → Default\* → 列表首个**。
- 无 JSON → **Default Layout**（项目约定，非 lazer 默认）：

| 组件 | Anchor | Position |
|---|---|---|
| Combo | TopLeft 9 | (20, 20) |
| BeatmapAttributeText | TopRight 12 | (−20, 20) |
| BPMCounter | TopRight 12 | (−20, 55) |
| SongProgress | TopRight 12 | (−20, 100) |
| AccuracyCounter | BottomRight 36 | (−20, −50) |
| ClicksPerSecondCounter | BottomRight 36 | (−20, −90) |
| BarHitErrorMeter* | BottomCentre 34 | (0, 0) |

\* 仅 Replay 时存在。

- JSON 里其它组件也渲；**联机类**（SpectatorList / PlayerAvatar / DrawableGameplayLeaderboard…）跳过。
- **BarHitErrorMeter**：原需求「永不渲」已被改写为「**有 Replay 才渲**」（见 ADR / CONTEXT）。

---

## 6. 舞台几何与滚动（`playfield.py`）

### 6.1 坐标空间

- 逻辑空间 **768 高**（lazer `STABLE_MAGIC_SCALE_FACTOR=1.6`，480→768）。
- 视窗 1080 高：`view_scale = 1080/768`。
- 舞台水平 **居中**（与 lazer `Stage` 一致；`ColumnStart` 不参与定位）。

### 6.2 判定线

```
hitPosition_from_bottom = (480 - clamp(skin.ini HitPosition, 240, 480)) × 1.6
lengthToHitPosition     = 768 - hitPosition_from_bottom   // 自顶到线
hit_y_view              = lengthToHitPosition × view_scale
```

### 6.3 ScrollSpeed → TimeRange（`DrawableManiaRuleset`）

```
TimeRange_raw     = 11485 / ScrollSpeed          // ScrollSpeed ∈ [1,40]
                  = 11485 / 30 ≈ 382.83ms        // UI 显示 382ms

scale             = lengthToHitPosition / (768 - DEFAULT_HIT_POSITION)
                  = lengthToHit / 643.2           // DEFAULT=(480-402)×1.6=124.8

TimeRange         = TimeRange_raw × rate × scale // 保持 px/ms 恒定
```

坐标（Constant 简化；本版未做 Sequential/SV 积分）：

```
Y(t) = hit_y − (t − now) / TimeRange × scrollLength
scrollLength = hit_y（自顶到判定线的像素）
```

`t=now` 在判定线上；`t=now+TimeRange` 在屏顶。

### 6.4 note 高度（`LegacyNotePiece`）

```
scale = (DrawWidth, noteHeight) / texture.DisplayWidth
noteHeight = WidthForNoteHeightScale ? : columnWidth
→ 绘制高 = 纹理高 × noteHeight / 纹理宽
```

即 **不** 把贴图拉成正方形，而按纹理宽作分母。

### 6.5 列贴图编号（`LegacyManiaColumnElement.FallbackColumnIndex`）

无 `NoteImage{n}` 时：特殊列→`S`；否则 `distanceToEdge = min(col, keys-1-col)`，`distanceToEdge % 2` → `"1"` / `"2"`。

4K 边缘距离为 `0,1,1,0` → **1,2,2,1**（owc：白蓝蓝白）。

---

## 7. note / LN 绘制与判定消失

**规则：压判定线即消失，不掉到线下。**

| 类型 | 未判定 | 判定后 |
|---|---|---|
| 单点 | 完整画在 `Y(start)` | `now ≥ start` → **不画** |
| LN 头 | `now < start` 时画在头 | 头消失 |
| LN 身 | tail→头（或线）的整条；**tail 未进屏时从屏顶裁切**，禁止 `top < −80` 整根丢掉 | 线下部分被吃掉，身随 tail 下落变短 |
| LN 尾 | 尾进入视口才画 | `now ≥ end` 整根消失 |

时间窗裁剪：`span = TimeRange×3 + max_hold_ms`（长条跨度必须算进窗，否则按住中途会消失）。

---

## 8. 判定 / Combo / CPS / ACC

### 8.1 时间源

| 模式 | Combo | CPS | δ / 误差条 |
|---|---|---|---|
| **Replay** | 沿物件轴匹配 press→note，推 `HitResult` | 真实 Press 滑窗 1s | `press − start` |
| **FC Sim** | 全连 +1（LN 头尾各 +1） | 单点+LN头+**LN尾**各 1 次（ADR-0001） | 全 0 |

### 8.2 判定窗（`ManiaHitWindows`，半宽 ms）

非 convert 路径（`DifficultyRange`：hi@OD0 / mid@OD5 / lo@OD10）：

| 结果 | 范围 (hi, mid, lo) |
|---|---|
| perfect | 22.4 / 19.4 / 13.9 |
| great | 64 / 49 / 34 |
| good | 97 / 82 / 67 |
| ok | 127 / 112 / 97 |
| meh | 151 / 136 / 121 |
| miss | 188 / 173 / 158 |

实现：`floor(w)+0.5`，与源码一致。

### 8.3 SongProgress（lazer 语义）

**当前曲内时间 / 全曲时长**（不是片段长度）。禁止「绝对时间 / 片段长」混用。

---

## 9. BarHitErrorMeter（`BarHitErrorMeter.cs`）

竖条几何 + **`Rotation = −90°`** → 画面为 **横条**。

```
bar_height=200（误差轴长，横放）
judgement_line_width=14（色轴宽）
chevron_size=8
margin=2
```

### 9.1 落点

```
TimeOffset δ = press − note.StartTime          // JudgementResult.TimeOffset
Y_rel       = clamp((δ / maxHitWindow + 1) / 2, 0, 1)
```

旋转后写到 **X**：δ&lt;0 早=左，δ=0 中，δ&gt;0 晚=右。

`maxHitWindow` = `GetAllAvailableWindows()` 过滤 `IsHit()` 后 **First()** 的长度 = **meh 窗**（Miss..Perfect 升序枚举后第一个命中档）。

### 9.2 每刀一条样条（`JudgementLine`）

- 仅 **scorable hit**；miss / 不计分不画。
- 淡入 100ms 到 α=0.6，同时宽度长出；再 **淡出 5000ms** 收缩。
- 颜色按 `ResultFor(|δ|)`：perfect/great/good/ok/meh 色段（与色轴一致）。
- 横放后为 **竖短线**，X=落点，Y 向上下撑开。

### 9.3 色轴与滑动平均

- 色轴：以 meh 窗为全长，按窗宽从中心向早/晚两侧铺色。
- 中心白标。
- 箭头：`avg = avg*0.9 + δ*0.1`（`floatingAverage`），横放后指向误差增大方向。

---

## 10. 命中闪光（Hit Lighting）

| 资源 | 用途 | 时序（lazer） |
|---|---|---|
| `lightingN` / `lightingN-0…` | 判定线打击闪 | FadeInFromZero 80ms → FadeOut 120ms（共 200ms） |
| `lightingL` / `lightingL-0…` | LN 按住亮 | 按住 FadeIn 80ms；松开再 120ms 淡出 |

- **加算混合**（additive）。
- 尺寸：`ExplosionWidth/HoldNoteLightWidth` ÷ `DEFAULT_COLUMN_SIZE(48)`，否则按列宽。
- **严格跟皮肤**：贴图全透明则不画、不合成默认光晕（lazer 一致；owc 的 N/L 为空）。

---

## 11. 合成与编码

```
每帧:
  1. 拷贝静态层（背景+列+键+判定线，只建一次）
  2. 时间窗内画 note / LN（裁到判定线）
  3. lightingN/L
  4. HUD 文本与组件
  5. RGB24 原始帧 → ffmpeg stdin
```

| 优化 | 说明 |
|---|---|
| 静态层缓存 | 背景/列/键不每帧重算 |
| 时间窗 | bisect 只取 `now±span` 内物件 |
| 贴图缩放缓存 | 同尺寸不重复 resize |
| 空 lighting 跳过 | `getbbox() is None` 直接 return |
| 空闲帧复用 | playfield 空且 HUD 未变 → 重发上帧（replay 下 CPS 每帧变，几乎复用不到） |
| 流式编码 | 不落临时 PNG，避免磁盘写爆 |
| lead-in | `range` 从 0 起默认 1s，时钟从 −1s 开跑，note 滚入而不是贴线出生；音频前垫静音 |

**注意**：ffmpeg `stderr` 若用 PIPE 且结束前不读，会写满管道导致 **死锁**；须 DEVNULL/文件或独立线程消费。

帧率：`--fps`（默认 60）；时间采样为闭区间，`n ≈ (end−start+lead)×fps + 1`。

---

## 12. 背景

- `[Events]` 行 `0,0,"file",…` 取文件名 → 按 ID 下载。
- 按 lazer 习惯 **暗化**（约 60% 黑罩）；`--no-background` 可关。
- 无背景时可退回皮肤 `menu-background`。
- **填充方式：cover**（等比放大到铺满，再居中裁切），不是拉伸。
  `scale = max(VIEW_W/w, VIEW_H/h)` 然后居中裁剪成 1920×1080
  （`renderer.py::_background()`；网页端 `Renderer.coverUV()` 用同一个公式）。
  背景很少正好 16:9 —— 缓存里就有 1439×1439、1004×640、640×480 的，
  拉伸会肉眼可见地变形。

### 网页端的两条坑（2026-09 修复）

1. **背景曾经是倒置的。** 精灵用的 `VS` 里有 `ndc.y = -ndc.y;`（屏幕 Y 向下、NDC Y 向上），
   而全屏背景用的 `VS_BG` 漏了这一句，于是 `aPos.y=0` 的行（图像第一行，
   因为从未设置 `UNPACK_FLIP_Y_WEBGL`，纹理 v=0 就是图像顶端）被贴到了屏幕**底部**。
   修法：`gl_Position = vec4(aPos.x*2-1, 1-aPos.y*2, 0, 1)`，让 `aPos.y=0` 同样是屏幕顶端。
2. **换谱面时背景不更新。** GPU 纹理按角色名 `'bg'` 缓存，`uploadTexture` 命中缓存就直接返回，
   于是第二张谱面继续画第一张的背景，而且还会套上**新图**的 UV 裁切矩形（更明显的变形）。
   修法：`loadAudioAndBackground()` 开头 `renderer.dropTexture('bg')` 并清空 `bgImage`；
   新增 `Renderer.dropTexture(key)`。顺手也让背景拉取失败时显示空白，而不是上一首的图。

验证方式（不靠肉眼）：`bg_probe.mjs` 把背景调成不透明后截一条没有精灵的画面，
`bg_check.py` 把这条画面的逐行亮度曲线分别与「cover 正置 / cover 倒置 / 拉伸正置 / 拉伸倒置」
四种候选做相关。修复前最佳匹配是 `stretched, FLIPPED` (+0.9993)，修复后是
`cover-crop, upright` (+0.996)。

---

## 13. 已拍板的设计决策（摘要）

| 决策 | 内容 |
|---|---|
| ADR-0001 | FC Sim 把 LN 尾计入 CPS；Replay 只计 Press（刻意不对称） |
| BarHitErrorMeter | 有 Replay 才渲；横条；δ 分点 |
| 必选 6 HUD | 含 AccuracyCounter |
| Default Layout | 无 Layout JSON 时的项目内坐标表（§5.5） |
| >10K | 拒渲 |
| 闪光 | 严格跟皮肤，无兜底 |
| 片段 | 秒闭区间；越界报错 |
| SongProgress | 曲内时间/全曲长 |

---

## 14. CLI 速查

```bash
python -m mania_render --id 4764345
python -m mania_render --id 4764345 --range 0-10 --fps 30
python -m mania_render --id 2467450 --replay "xx.osr" --range 30-40
python -m mania_render --id 5838687 --skin "D:\osu-lazer\exports\....osk" --range 30-60
```

| 参数 | 含义 |
|---|---|
| `--id` | 谱面 ID |
| `--osu-file` / `--audio` | 本地覆盖 |
| `--skin` | `.osk` 或目录 |
| `--replay` | `.osr` |
| `--range a-b` | 秒闭区间 |
| `--lead-in` | 片头引入；`range` 从 0 起默认 1.0 |
| `--scroll-speed` | 默认 30 |
| `--fps` | 默认 60 |
| `--no-hit-effects` / `--no-background` | 关特效 / 关背景 |
| `-o` | 输出 mp4 |

---

## 15. 已知边界

- 滚动为 **Constant**，未实现 Sequential / SV Multiplier（复杂变速图与实机可能有差）。
- 无 Replay 时误差条不出现（约定）。
- owc 的 `lightingN/L` 为空，无打击闪属预期。
- 联机 HUD 只跳过、不画占位。
