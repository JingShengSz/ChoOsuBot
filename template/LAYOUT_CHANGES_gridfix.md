# 成绩卡 v1 · 玩家铭牌右移 + 服务器部署记录

| 项 | 值 |
|---|---|
| 设计源 | `D:\Cho Osu Bot\template\osu_score_template_v1.psd`（**原位修改**） |
| 线上 | `root@www.liuliyue.com` · `/opt/astrbot/data/plugin_data/astrbot_plugin_osu_scorecard/` |
| 本机备份 | `*.before_sync`（同名同目录，改动前的原件） |
| 服务器备份 | `/root/osu-before-avatar-move-20261005/` |
| 时间 | 2026-10-05 00:26（PSD）/ 00:42（服务器上线） |

---

## §0 先记住这条链路

线上出图走**纯 Pillow**（`renderer: "pil"`），版式全部读 `layer_mapping.json` + `assets/`，
**PSD 完全不参与渲染**。所以「改 PSD」和「改线上」是两件独立的事，都要做。

```
PSD (设计源，只给人看)
  └─ 导出的 ink 框 ──► layer_mapping.json ──┐
                                            ├──► render.py (Pillow) ──► 成绩卡 PNG
  头像/立绘/徽章 ─────► main.py 的坐标 ─────┘
```

---

## §1 本机改动

### 1.1 PSD（`osu_score_template_v1.psd`）
只有玩家铭牌一组 5 个图层，其余一律未动。`ink` = `[left, top, right, bottom]`。

| 图层 | 改动前 ink | 改动后 ink | 字号 | 对齐 |
|---|---|---|---|---|
| `player_avatar` | 720,75,836,191 | **1124,74,1240,190** | —（光栅） | 位移 |
| `player_name` | 915,95,1022,116 | **972,95,1104,121** | 26 → **32** | left → right |
| `_deco_total_pp_label` | 860,147,930,159 | **1034,147,1104,159** | 15（不变） | left → right |
| `total_pp` | 860,172,993,201 | **987,172,1104,198** | 30 → **26** | left → right |
| `rank_change` | 910,218,1008,247 | **1032,218,1104,239** | 30 → **22** | left → right |

定位依据：头像右缘 **1240**（右轨）、头像顶线 **74**（与主标题同一刊头线）、
铭牌文字右缘 **1104** = 头像左缘 1124 − 20px。头像 116×116 不变。

### 1.2 仓库文件

| 文件 | 改动 |
|---|---|
| `plugins/.../render.py` | 第 318 行新增 `justify == "right"` 分支（原来只有 `center`） |
| `plugins/.../main.py` | 第 603 行头像坐标 `(720, 75)` → **`(1124, 74)`**；第 596 行过期注释 `(922,60)` 一并修掉 |
| `template/layer_mapping.json` | 上表 4 个文字层的 `sizePx` / `justify` / `ink`；`server_tag` 的 `note` 更新 |
| `plugins/.../self_test.py` | 第 813/818 行断言 `「官方」` → **`「Lazer」`** |
| `plugins/.../card.py` | 第 662 行同一条过期注释 |
| `plugins/.../README.md` | 分服标识表补 Lazer / Stable 两行 |

`render.py` 新增的分支：

```python
if spec.get("justify") == "right":
    # 右对齐：实际墨迹的右缘贴到示例墨迹的右缘（ink[2]）。
    # 数值长度会变，右对齐才能让右栏始终维持同一条竖线。
    tw = draw.textbbox((0, 0), str(value), font=font)
    ox = ink[2] - tw[2]
elif spec.get("justify") == "center":
    ...
```

> `layer_mapping.json` 的 `example` / `ink` 是定位依据：`render.py` 用示例墨迹的
> 左上角反推笔原点。**改 `example` 会平移渲染位置**，所以 `server_tag` 只更新了
> `note`，`example` 仍是 `官方`。

---

## §2 服务器部署（只推了头像这一部分）

上传 3 个文件，MD5 双向校验一致：

| 文件 | MD5 |
|---|---|
| `main.py` | `961481885af1ed1b90995b8c43c12ad4` |
| `render.py` | `2cea24aeea222e58a2887fe4887c5101` |
| `layer_mapping.json` | `efabd5fc16d99b8625e232f06efade0f` |

`systemctl restart astrbot` → `active`。

### 验证方式（自测跑不通的替代方案）

服务器上跑 `self_test.py` 有两条路都断了：系统 python 没有 `astrbot` 包；
用 AstrBot 自己的解释器又卡在 OAuth 回调端口被在跑的服务占用。
所以改为**直接调用渲染器真实的 `_draw_texts`**，用不同长度的值检验右缘：

| 图层 | 值 | 实测墨迹框 | 右缘 |
|---|---|---|---|
| `player_name` | `Cookiezi` | (971, 95, 1102, 120) | 1102 |
| `player_name` | `a_very_long_player_name` | (709, 96, 1103, 127) | 1103 |
| `player_name` | `A` | (1081, 96, 1103, 120) | 1103 |
| `_deco_total_pp_label` | `TOTAL PP` | (1035, 147, 1104, 158) | 1104 |
| `total_pp` | `12,345pp` | (988, 172, 1104, 196) | 1104 |
| `total_pp` | `9,486pp` | (998, 172, 1104, 196) | 1104 |
| `rank_change` | `+1,204` | (1032, 218, 1102, 238) | 1102 |
| `rank_change` | `-999` | (1052, 218, 1103, 234) | 1103 |

**结论**：值长短变化时右缘稳定在 1102–1104，右对齐生效。
1102 与 1104 的 2px 差是 Pillow 的推进宽度与字形墨迹的侧距差（如 `i`、`4` 的右边距），
属正常现象；定位用的是推进宽度，所以六个文本框的右缘是一致的。

---

## §3 从服务器同步下来的东西

你说服务器把左上角的分服标识从「官方」改成了 **Lazer / Stable / SB**。
排查结果：**这个改动的代码本机早就有了，两边逐字节相同** ——

```python
# card.py:664（服务器与本机一致）
server_tag=("SB 私服" if _server == "sb" else "Stable" if is_stable else "Lazer"),
```

真正没跟上的是文档与自测，已在本机补齐（见 §1.2 的 `self_test.py` / `card.py` / `README.md`）。
**这一项不需要往服务器推任何东西。**

### 一并确认的服务器 vs 本机差异

| 对比项 | 服务器 | 本机 | 处置 |
|---|---|---|---|
| 插件 13 个 `.py` | — | — | 改动前逐字节一致 |
| `layer_mapping.json` | — | — | 改动前逐字节一致 |
| `assets/` | 145 文件 / 19 MB | 448 文件 / 78 MB | **未动**。本机多出的 303 个是字体、`rank_svg`、未用到的立绘等 |
| `assets/mods/line_v1/manifest.json` | 22:01 · 12 个 mod | 23:46 · 29 个 mod | **未动**（按你的要求，新 mod 不碰）。该文件运行时不读取，仅素材构建元数据 |

---

## §4 未改动

- 本机 `osu_score_template_v1_gridfix.psd`（完整重构版）与 `osu_score_template_v2.psd` —— 时间戳未变
- 服务器 `assets/` 全目录、`osu_score_template_v2.psd`、AstrBot 配置、其它 10 个 `.py`
- 本机 `template/layer_mapping.json` 里除上述 5 层外的 50 层
- 早前在 gridfix 副本里做过的其它版面改动（右栏统一右轨、判定等宽栅格、分隔线合并、
  日期/星级条对齐、描边降透明、景深层、波形槽）**都没有进 v1，也没有上服务器**

---

## §5 回滚

```bash
# 服务器：恢复改动前的三个文件，重启
cp /root/osu-before-avatar-move-20261005/{main.py,render.py} \
   /opt/astrbot/data/plugins/astrbot_plugin_osu_scorecard/
cp /root/osu-before-avatar-move-20261005/layer_mapping.json \
   /opt/astrbot/data/plugin_data/astrbot_plugin_osu_scorecard/template/
systemctl restart astrbot
```

本机：把同目录下的 `*.before_sync` 去掉后缀覆盖回去即可。
PSD：`osu_score_template_v1.before_avatar_move.psd`。

---

## §6 坐标速查

```
头像            1124,74  → 1240,190      （116 × 116）
姓名            右对齐 1104，字号 32
TOTAL PP 标签   右对齐 1104，字号 15
总 PP 值        右对齐 1104，字号 26
排名增量        右对齐 1104，字号 22

头像右缘 = 右轨     1240
铭牌文字右缘        1104 = 1124 − 20
头像顶线 = 刊头顶线  74
```

代码位置：`main.py:603`（头像坐标）、`render.py:318`（右对齐分支）、
`layer_mapping.json` 的 `textLayers` 里 `player_name` / `_deco_total_pp_label` /
`total_pp` / `rank_change` 四项。
