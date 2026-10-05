# ChoOsuBot

osu! 成绩卡与 osu!mania 回放渲染。给 AstrBot 用的两个插件，加一套自己维护的版式模板和渲染器。

```
ChoOsuBot/
├── plugins/                              AstrBot 插件（装到 data/plugins/ 下）
│   ├── astrbot_plugin_osu_scorecard/     成绩卡：把一局成绩渲成 1920x1080 PNG
│   └── astrbot_plugin_mania_render/      回放：把 .osr 渲成 MP4（调用外部 HTTP 服务）
├── renderer/                             mania_render Python 包 + web UI + 皮肤 + 工具
├── template/                             成绩卡的版式与素材
│   ├── layer_mapping.json                版式规格（渲染只读它）
│   ├── assets/                           静态层 / 立绘 / 评级配色位图 / mod 徽章
│   ├── build/                            施工脚本（Photoshop JSX + Python）
│   └── star_strip.js / rank_theme.js     星级条与评级配色生成器（零依赖）
├── docs/                                 文档
└── LICENSE                               Apache-2.0
```

---

## 成绩卡插件（`astrbot_plugin_osu_scorecard`）

### 指令

| 指令 | 作用 |
|---|---|
| `p` | 最近24h内**通过**的成绩 |
| `r` | 最近24h内**游玩**的成绩 |
| `s<谱面ID>` / `s <谱面ID>` | 绑定账号在该谱面的最近一次可查成绩，在线查不到时查询记录库 |
| `bind <osu用户名>` | 绑定官服账号（会回一个授权链接） |
| `bind <osu用户名> -sb` | 绑定 **SB 私服**（osu.ppy.sb）账号 |
| `unbind` / `解绑` | 解绑官服账号；解绑私服使用 `unbind -sb` |
| `bg` / `bg<谱面ID>` / `bg <谱面ID>` | 获取谱面原始背景；省略 ID 时使用本聊天最近一次成功发送的 p/r 成绩 |
| `song` / `song<谱面ID>` / `song <谱面ID>` | 发送从谱面预览起点开始的 30 秒语音；省略 ID 的规则同 bg |
| `mode <osu\|taiko\|fruits\|mania>` | 切换绑定的模式 |
| `help` | 指令一览 |

**消息里直接贴 `https://osu.ppy.sh/scores/<数字>` 会自动出图。**

`p/r` 没有符合条件的24h记录时回复 `24h没有游玩记录。`；成功查询的返回成绩
写入插件数据目录的 `plays.sqlite3`，重复查询不重复插入。封面只保存链接。
`s` 必须绑定对应服账号，不受24h限制；数据按 QQ、绑定账号、服务器和模式隔离。
数据库从上线开始积累，无法恢复 API 不提供且从未被机器人记录的历史成绩。
`bg/song` 不要求绑定；本聊天的最近谱面记录在重启后保留。音乐生成需要服务器安装
`ffmpeg` 和 `ffprobe`，首次获取时会下载并缓存背景或原曲。

### 官服 / 私服是两套独立体系

任何指令末尾加 **`-sb`** 就是查 SB 私服，不加是官服。**绑定也是分开的**（`bind A` 和 `bind A -sb` 互不影响）。

| | 官服 | SB 私服 |
|---|---|---|
| 数据源 | `osu.ppy.sh/api/v2` | `api.ppy.sb` |
| `p` / `r` | **需要 OAuth 授权** | **直接可用，不需要授权** |
| `s <id>` / 链接 | 需要应用凭据（client credentials） | 直接可用 |

官服「最近成绩」接口对**应用凭据一律返回 404**，必须有用户令牌 —— 所以 `p`/`r` 走授权码流程：
用户发 `bind <名字>` → 插件回一个 osu! 授权链接 → 用户点一下授权 → osu! 回调到本插件 → 绑定完成。

### 配置

按 `_conf_schema.json` 在 WebUI 里填。**部署到 Linux 时必须注意：**

- **`renderer` 必须设成 `pil`**（这是「成绩卡用哪套引擎画」的意思，和 om 回放渲染器无关）。
  Linux 上没有 Photoshop，`auto` 会退回 PIL 但会有一次失败尝试，`photoshop` 直接不可用。
- `photoshop_path` 留空。
- `assets_path` 指向 `template/assets`，`spec_path` 指向 `template/layer_mapping.json`。
- `osu_credential_file` 指向你的 `osu_oauth.local.json`（见下）。
- **`http_proxy`**：如果机器上需要代理才能访问 `api.ppy.sb` / `osu.ppy.sh`，在这里显式填
  （例 `http://127.0.0.1:7890`）。留空则自动探测。

  > 自动探测有个坑：环境里有 `NO_PROXY` 时，Python 的 `getproxies()` 会短路，
  > **Windows 注册表里的代理不会被读到**，请求会变成直连而静默失败。
  > 插件已经做了补偿（显式补注册表），但显式填这一项永远是最可靠的。

### 凭据

新建 `osu_oauth.local.json`：

```json
{ "osu_client_id": "<你的>", "osu_client_secret": "<你的>" }
```

去 <https://osu.ppy.sh/home/account/edit> → 拉到最下面 **OAuth** → **New OAuth Application** 创建。

> **这个文件绝不能提交。** `.gitignore` 已经排除。

### OAuth 回调（官服 `p`/`r` 需要）

回调地址**必须先在 osu! 的 OAuth 应用里登记**，且要和插件生成的一字不差（osu! 是字面比较）。

- 配置项 `oauth_callback_host` / `oauth_callback_port` / `oauth_redirect_base`
- 插件会自己起一个 aiohttp 服务，路由固定 `/oauth/callback`
- **本机测试**（浏览器和 AstrBot 同机）：`oauth_redirect_base` 填 `http://127.0.0.1:<port>` 即可
- **给多个 QQ 用户用**：回调是打到**用户浏览器**上的，`127.0.0.1` 他们访问不到 ——
  必须有公网地址（域名 + 反向代理，或端口转发）

---

## 回放插件（`astrbot_plugin_mania_render`）

`om <谱面ID>` / `om` 回复 `.osr` → 渲染成 MP4。**它自己不做渲染**，靠调用一个
HTTP 服务（配置项 `server`，默认 `http://127.0.0.1:8760`）—— 那个服务不在本仓库里。

---

## 字体

成绩卡用 Pillow 画字，需要这些字体：

| 用途 | 字体 | 许可 | 是否随仓库 |
|---|---|---|---|
| 正文 / 数字 | Inter 18pt（6 个字重） | OFL-1.1 | ✅ `plugins/.../fonts/` |
| 评级字母 | Montserrat（4 个字重） | OFL-1.1 | ✅ |
| 等宽 | JetBrains Mono（2 个字重） | OFL-1.1 | ✅ |
| **日文标题** | **Yu Gothic Medium** | **商业（微软/Adobe）** | ❌ **不随仓库** |

**日文标题需要 Yu Gothic**，它是商业字体，**不能进公开仓库**。
部署到 Linux 服务器时，从你自己的 Windows 复制：

```bash
cp /path/to/Windows/Fonts/YuGothM.ttc  plugins/astrbot_plugin_osu_scorecard/fonts_private/
```

（`fonts_private/` 已在 `.gitignore` 里。找不到 Yu Gothic 时，插件会退到系统里的
Noto Sans CJK —— Ubuntu 自带，也能显示日文，只是字形和设计稿略有差异。）

---

## 部署

```bash
# 1. 插件
cp -r plugins/astrbot_plugin_osu_scorecard   <AstrBot>/data/plugins/
cp -r plugins/astrbot_plugin_mania_render   <AstrBot>/data/plugins/

# 2. 模板素材（渲染要用，别漏）
mkdir -p <AstrBot>/data/plugin_data/astrbot_plugin_osu_scorecard/template
cp -r template/layer_mapping.json template/assets \
      <AstrBot>/data/plugin_data/astrbot_plugin_osu_scorecard/template/

# 3. 日文字体（见上）
# 4. 凭据 osu_oauth.local.json 放到你能记住的位置，路径填进配置
# 5. 配置里 renderer=pil，assets_path / spec_path 指向上面那两个
# 6. systemctl restart astrbot
```

---

## 改模板之后必须做的事

成绩卡的版式**不是硬编码的** —— Pillow 渲染只读 `template/layer_mapping.json` 和
`template/assets/` 下的导出素材。**改了 PSD 模板但不重新导出，出的图会和设计稿脱节。**

```bash
# 1. 记录每个文字层的精确 ink 框
<Photoshop 里跑>  template/build/dump_ink.jsx
# 2. 重导静态层 + 立绘
<Photoshop 里跑>  template/build/export_static.jsx
```

`export_static.jsx` 里每张立绘都要有一行 `exportSignboard("signboard_x")` ——
**加了新立绘但忘了加这一行，是静默失败**：不报错，但素材不会更新。

---

## 测试

```bash
cd plugins/astrbot_plugin_osu_scorecard
python self_test.py          # 离线，几秒，会真渲一张卡
```

---

## License

Apache-2.0（与 [yumu-bot](https://github.com/yumu-bot/yumu-bot) 一致）。
随包分发的字体遵循各自的 OFL-1.1 许可。
