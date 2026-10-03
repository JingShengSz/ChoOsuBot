# osu-mania-renderer

玩家资料、成绩和原始背景的公共调用入口见 [共享 osu! 素材接口](docs/shared_osu_assets.md)。

**osu!mania 渲染器 —— 把谱面或 `.osr` 回放渲染成 MP4。**

An osu!mania replay renderer: renders a beatmap or an `.osr` replay to MP4, driven from the
command line, a browser WebGL viewer, or an AstrBot chat plugin.

默认输出 **1920×1080 / 60fps / H.264 MP4**。

---

## 1. 项目组成

| 目录 | 内容 |
|---|---|
| `mania_render/` | Python 包：谱面/回放解析、皮肤加载、几何计算、HUD、MP4 渲染，以及 CLI 与 HTTP 服务 |
| `mania-web/` | 纯静态前端（WebGL 播放器、`.osr` 解析、MP4 录制），由 `mania_render` 的 HTTP 服务托管 |
| `astrbot_plugin_mania_render/` | AstrBot 插件：把渲染服务包装成聊天指令与 LLM 工具 |
| `docs/` | 设计文档：渲染器原则、皮肤一致性、HoldNote 与皮肤链路实测记录、ADR |
| `CONTEXT.md` | 领域词汇表（TimeRange / HoldNote / Anchor / FC Sim 等术语的唯一权威定义） |
| `beatmap_md.py` | 独立的 `.osu` 元数据快速读取脚本 |

渲染有两种路径，互不依赖：

- **浏览器侧** —— `mania-web` 在访问者的浏览器里用 WebGL 绘制，MP4/H.264 直接由
  `MediaRecorder` 产出，**不需要 ffmpeg**，服务端不加载 Pillow/numpy。
- **服务端** —— `POST /api/render` 或 CLI，由 Python 逐帧绘制后用 ffmpeg 编码。

## 2. 环境要求

- **Python 3.10+**（本仓库开发与验证于 3.14）。
- **渲染（服务端路径 / CLI）** 需要：

  ```bash
  pip install Pillow numpy
  ```

- **ffmpeg** 需要在 `PATH` 上（MP4 封装用；浏览器侧录制路径不需要）：

  ```bash
  # Debian/Ubuntu
  apt install ffmpeg fonts-dejavu-core
  # RHEL/Fedora
  dnf install ffmpeg
  ```

  字体不是可选项：系统里一个常见字体都没有时，`_load_font` 会退化成 PIL 的位图字体，
  HUD 上的数字尺寸会明显不对。

- **静态 + API 服务** 本身**只用标准库**，不需要任何第三方依赖 —— `webapp.py` 只在
  服务端渲染任务内部才 `import` Pillow/numpy。

- **AstrBot 插件** 只需 `aiohttp`（AstrBot 自带）。

## 3. 皮肤需要自备（本仓库不附带皮肤）

本仓库**不包含任何 `.osk` 皮肤**，也**不包含 `skins/` 目录**：项目用到的皮肤是第三方
作品，版权属于各自的作者，随仓库分发不合适。

请自行准备皮肤，二选一：

1. 把 `.osk` 文件放进项目根目录的 `skins/`；或
2. 设置环境变量 `MANIA_SKINS_DIR` 指向你放皮肤目录：

   ```bash
   export MANIA_SKINS_DIR=/opt/mania/skins
   ```

命令行用 `--skin <名字或路径>` 指定；Web UI 从 `/api/skins` 读取可选列表。

皮肤体积差异很大，大皮肤对内存影响明显：一个 1800 文件 / 181 MB 的皮肤，渲染器实际只会
引用其中 0.1% 的字节，建议只保留你要用的键数后再放进 `skins/`。

> 注：用来做上述瘦身的脚本属于开发工具，未随本仓库发布，见第 7 节。

## 4. 用 Web UI

```bash
python -m mania_render --web --host 127.0.0.1 --port 8760
```

然后打开 <http://127.0.0.1:8760/> 。

- `/` —— WebGL 播放器：上传 `.osr` 或填谱面 ID，鼠标移到屏幕底部拉出控制面板。
  支持皮肤、滚动速度、背景暗度/模糊、片段范围，以及「导出 MP4」（浏览器内录制）。
- `/diag` —— 渲染诊断页。
- `GET /api/skins` —— 确认服务当前能看到哪些皮肤。
- `POST /api/render` —— 提交服务端渲染任务；`GET /api/download/<任务号>` 取回 MP4。

其他相关环境变量见第 6 节。**默认绑定 127.0.0.1**；要对外提供服务需显式
`--host 0.0.0.0`（建议放在反向代理后面）。

> 2 核 2 GB 的机器上不要并发渲染：一个任务就会占掉大半内存。

## 5. 用 CLI

```bash
# 用谱面 ID 渲染整首，输出 out.mp4
python -m mania_render --id 2467450 -o out.mp4

# 指定皮肤、滚动速度、帧率
python -m mania_render --id 2467450 --skin "R Skin" --scroll-speed 30 --fps 60 -o out.mp4

# 带 .osr 回放（会启用真实 Combo/CPS 与 hitsound 误差条）
python -m mania_render --id 2467450 --replay score.osr -o out.mp4

# 只渲染 60–75 秒这一段
python -m mania_render --id 2467450 --range 60-75 -o clip.mp4

# 用本地 .osu / 音频覆盖下载来源，先干跑确认参数
python -m mania_render --id 2467450 --osu-file map.osu --audio song.mp3 --dry-run
```

常用参数：

| 参数 | 说明 |
|---|---|
| `--id` | 谱面 ID（bid）；与 `--osu-file` 至少给一个 |
| `--osu-file` / `--audio` | 本地 `.osu` / 音频覆盖下载来源 |
| `--skin` | `.osk` 文件或解包后的皮肤目录 |
| `--replay` | `.osr` 回放（可选） |
| `--range` | 渲染片段，秒，闭区间，如 `0-100` |
| `--lead-in` | 片头引入秒数；`range` 从 0 起时默认 1.0s，便于音符滚入 |
| `--scroll-speed` | 下落速度 1–40，默认 30 |
| `--fps` | 帧率，默认 60 |
| `--no-hit-effects` / `--no-background` | 关掉打击特效 / 背景 |
| `-o, --out` | 输出 mp4 路径 |
| `--cache` | 缓存目录，默认 `<项目>/cache` |
| `--dry-run` | 只解析并打印，不渲染 |

## 6. 环境变量

| 变量 | 作用 | 默认 |
|---|---|---|
| `MANIA_SKINS_DIR` | `.osk` 所在目录 | `<项目>/skins` |
| `MANIA_DEFAULT_SKIN` | UI 里预选的皮肤 | `boj 1-10K` |
| `MANIA_HOST` | `--web` 绑定地址 | `127.0.0.1` |
| `MANIA_PORT` | `--web` 端口 | `8760` |
| `MANIA_ENGINE` | 任务没带 `engine` 字段时用哪个渲染引擎：`webgl` 或 `python` | `webgl` |
| `MANIA_CHROME_HOST` / `MANIA_CHROME_PORT` | WebGL 引擎要连的 Chrome（CDP） | `127.0.0.1` / `9222` |
| `MANIA_WIDTH` / `MANIA_HEIGHT` | 任务没带 `width`/`height` 时的输出尺寸 | `1920` / `1080` |
| `MANIA_BITRATE` | 任务没带 `bitrate_kbps` 时的视频码率（kbps） | `2000` |
| `OSU_USER_TOKEN` | osu! 用户级 token，用于官方 `.osz` 下载 | 读 `cache/osu_token.json` |

### 两个渲染引擎

`POST /api/render` 可以带 `engine=webgl`（默认）或 `engine=python`：

- **webgl** —— 用 CDP 驱动 `/` 那个页面（就是浏览器里看到的那一套渲染），编码在页面里用
  WebCodecs 完成，帧数据流回服务端，再由 ffmpeg 封装成 MP4 并混入音频。因此它需要一台跑着
  的 Chrome（`127.0.0.1:9222`，GPU 必须是 D3D11/ANGLE；SwiftShader 实测慢约 7 倍）。
  本机部署里这个 Chrome 由 `tools/render-node/render-node.ps1` 负责拉起与守护，
  详见 `tools/render-node/README.md`。
- **python** —— Pillow 渲染器，不需要浏览器，作为备选保留。

两者画出来的画面**不一样**，耗时也不同，所以这是用户可见的开关，不是内部细节。

输出尺寸按任务请求走：`width`/`height` 会原样传给页面（页面按该尺寸编码，不是先编码再缩放），
没带这两个字段时才用上面的 `MANIA_WIDTH`/`MANIA_HEIGHT`。历史上这两个默认值是 1280x720，
于是"没写尺寸"在 WebGL 上得到 720p、在 Python 上仍是 1080p —— 同一个请求随引擎变尺寸，已改正为 1920x1080。

> WebGL 引擎会把**整首**谱面编码一遍，`range` 只是编码后的 ffmpeg 裁剪，所以它不会因为
> `range=0-10` 就变快；`python` 引擎则只渲染区间内的帧。

### 码率（`bitrate_kbps`）

码率决定成片体积，而体积决定这条视频**能不能发出去**：成片要经协议端上传，通道对体积有上限，
超了就是发送超时。所以这个默认值不是画质偏好，是投递约束。

- 请求字段 `bitrate_kbps`（kbps），服务端默认 `DEFAULT_BITRATE_KBPS`（`MANIA_BITRATE`，2000）。
  和 `width`/`height` 一个路子：请求里有就用请求的，没有才用服务端默认。
- 服务端把它换算成 bps 写进页面的 `window.__webglBitrate`，页面不再自己决定这个数。
  页面自身的默认（`MANUAL_BITRATE`，6 Mbps）只服务**手动导出**：人在浏览器里点「导出」拿到的是
  本地文件，不经过任何上传通道，所以不降质。
- 页面侧对 bot 任务还会强制 `bitrateMode: 'constant'`。**这一条是必须的**：WebCodecs 默认的
  可变码率会把目标码率让给画质，实测同一张图请求 2000 kbps，R Skin 出 2.22 Mbps，boj 出
  4.78 Mbps（239%，且三次复现到个位）。按 4 分钟图谱外推就是 ~146 MB，正好撞上限。
- 另有 `BOT_MAX_BYTES`（72 MB，含混流后音轨的预留）作为兜底：超过约 5 分钟的谱面会按体积反推
  码率，把整片压在这个数以内；手动导出不受此限。

实测（同一张 86.3 s 谱面，webgl 引擎，1920×1080/60fps/aac）：

| 码率 | 皮肤 | 成片 | 视频码率 |
|---|---|---|---|
| 6000（旧默认） | boj | 72.8 MiB | 7.02 Mbps |
| 2000 | boj | 21.9 MiB | 1.97 Mbps |
| 2000 | R Skin | 16.7 MiB | 1.46 Mbps |

4 分 11 秒谱面：boj 65.3 MiB / R Skin 52.6 MiB，均低于插件的 80 MB 文件阈值。


## 7. AstrBot 插件

插件自身**不做渲染**：它调用独立的 mania-render HTTP 服务，提任务 → 轮询进度 →
下载 MP4 → 交给平台适配器发送。

安装：

1. 把 `astrbot_plugin_mania_render/` 整个目录放进 `AstrBot/data/plugins/`。
2. 在 AstrBot WebUI 插件页点一次「**重载插件**」（新增插件目录后必须重载）。
3. 在插件配置里确认 **mania-render 服务地址**（同机部署填 `http://127.0.0.1:8760`）。
4. 先按第 4 节把渲染服务跑起来，用 `curl http://127.0.0.1:8760/api/skins` 确认能看到皮肤。

聊天里的用法：

| 命令 | 作用 |
|---|---|
| `om <谱面ID> [选项]` | 渲染并发视频（别名 `mania` / `渲染` / `osu`） |
| `om`（回复一条带 `.osr` 的消息） | 用被回复消息里的回放渲染 |
| `om皮肤` | 列出可用皮肤 |
| `om参数` | 显示当前默认参数与服务地址 |

```
om 2467450
om 2467450 -s R Skin -d 30 -v 25
om 2467450 --from 60 --to 75
```

同时注册了一个 LLM 工具 `render_mania_video`，让模型能代用户渲染。
完整的参数表、给模型的行为约定、投递方式（`file` / `url`）、缓存与排错都在
[`astrbot_plugin_mania_render/README.md`](astrbot_plugin_mania_render/README.md)。

> 补充说明：本仓库只发布了 `tools/osu_oauth.py`（osu! 官方下载所需的用户级 OAuth
> 小工具，其中的 `client_id` 已替换为占位符 `YOUR_CLIENT_ID`）。其余 `tools/*`
> 是开发期的临时探针脚本，`tools/render-node/` 还包含运维机信息，均未包含在这里；
> 因此插件 README 第 8 节提到的 `tools/plugin_*_check.py` 等自测脚本在本仓库中不存在。

## 8. 许可

本项目以 **MIT 许可证**发布，完整条文见仓库根目录的 [`LICENSE`](LICENSE)
（Copyright (c) 2026 JingShengSz）。

另外，osu! 的名称与相关素材归 ppy Pty Ltd 所有；本项目与 osu! 官方无隶属关系。
皮肤、谱面与音频的版权归各自作者所有，请自行确保你有权使用。
