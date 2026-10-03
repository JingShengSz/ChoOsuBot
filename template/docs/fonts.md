# 字体清单 — osu! 成绩图模板

全部为 **SIL Open Font License 1.1**：免费商用、可再分发。成绩图是公开分享的，这几个字体的授权是干净的。

## 下载

| 字体 | 地址 |
|---|---|
| Montserrat | https://fonts.google.com/specimen/Montserrat |
| Inter | https://fonts.google.com/specimen/Inter |
| JetBrains Mono（备用） | https://www.jetbrains.com/lp/mono/ |

## 装哪些字重

至少装这四档，多加无害：

- **Montserrat Black (900)** — 只给 Rank 大字用（SS / XH / S / SH / A / B / C / D）
- **Inter Bold (700)** — 全部数值：accuracy / pp / score / max_combo / 判定数
- **Inter Medium (500)** — 曲名、难度名
- **Inter Regular (400)** — 标签、谱师、玩家名、BPM、CS/OD/HP

## ⚠️ 装完必做：把数字设成等宽

Inter 的数字默认是**比例宽度**——`1,111` 和 `9,999` 宽度不同。插件填进去之后数字会左右跳动、对不齐，这正是原始需求里点名要避免的坑。

操作：**窗口 → 字符 → 右上角菜单 → OpenType → 勾选「表格数字 / Tabular Figures」**。

每个数值图层都要勾一次。如果嫌烦，数值直接改用 **JetBrains Mono Bold**——等宽字体，天生对齐，不用勾任何选项。

## 各字体在模板里的分工

| 图层 | 字体 | 字重 | 字号 |
|---|---|---|---|
| `rank_ss` … `rank_d` | Montserrat | Black 900 | 170px |
| `accuracy` / `pp` | Inter | Bold 700 | 62px |
| `score` / `max_combo` | Inter | Bold 700 | 46px |
| `star_rating` | Inter | Bold 700 | 40px |
| `beatmap_title` | Inter | Medium 500 | 42px |
| `beatmap_artist` / `beatmap_difficulty` | Inter | Medium 500 | 24px |
| `beatmap_mapper` / `beatmap_id` | Inter | Regular 400 | 18px |
| `bpm` / `diff_stats` / `play_date` | Inter | Regular 400 | 22px / 20px |
| `player_name` | Inter | Bold 700 | 26px |
| `rank_change` | Inter | Bold 700 | 30px |
| `count_max` … `count_miss` | Inter | Regular 400 | 26px |

> 上表字号是当前模板里的实际值，来自 `layer_mapping.json`，字体换掉后字号可能需要微调——Montserrat 和 Inter 的字面宽度跟 Arial 不同，换完我会重新量一遍字符上限并更新映射表。

## 装完之后

告诉我一声，我会做三件事：

1. 把 30 个文字图层的字体全部换成新字体
2. 用新字体**重新实测每个字段的字符宽度上限**，更新 `layer_mapping.json`
3. 检查字号是否需要微调（换字体会改变文字占宽，原来量的 29 字符上限可能变）
