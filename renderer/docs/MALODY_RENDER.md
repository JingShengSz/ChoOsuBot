# Malody 与回放渲染

## AstrBot 用法

| 操作 | 用法 |
|---|---|
| osu!mania 回放 | 回复 `.osr` 文件发送 `.v`；可带谱面 ID 作为在线匹配失败的兜底 |
| Malody Key 谱面自动播放 | 回复含 `.mc` 和音频的 `.mcz/.zip` 文件发送 `.om` |
| 曲包选难度 | 回复机器人难度列表发送 `2`，可带 `@机器人` 和 `-s miku` 等选项 |
| Malody 4.x 回放 | 先导入对应谱面包，再回复 `.mr` 文件发送 `.v` |
| Malody V 回放 | 先回复对应 `.osz/.mcz/.zip` 发送 `.v` 导入，再回复 `.mrv` 发送 `.v` |
| 只导入对应谱面包 | 回复谱面包发送 `.v`，导入后会提示再回复回放文件 |
| Malody 手机判定窗口 | `.v --platform pe`；默认 `pc` |

`v` 固定使用 [Mania-Replay-Master 原仓库](https://github.com/Mania-Visualization-Project/Mania-Replay-Master) 的官方 v2.4.0 JVM 渲染器，调用其 `Render` 和
`Encoder` 类，输出判定颜色音符和按键轨迹。默认 540×960、60fps、速度 20。
支持 OM 同格式的滚动速度、分辨率、帧率、片段和平台参数；
皮肤与背景暗度参数仅用于 OM。OM 保留原 WebGL/Python 引擎。
osu 相关插件的全部指令名和别名支持大写及混合大小写，例如 `.P`、
`.SoNg123`、`.DTLP123`、`.OM`、`.V`；用户名及参数值保留原样。
`v 2` 没有回放时会提示提供回放，不会渲染谱面 ID 2。
OM 原有 `.osr/.osz` 支持保留。单独 `.mc` 没有音频：可以附上同一消息的
音频文件，或使用包含素材的谱面包。多难度选项有效期为 30 分钟。

## 支持范围

- `.mc` Key 模式 0/6，1–10K：音符、长条、变 BPM、音频 offset、非负 Scroll。
- Malody 4.x 和 Malody V 使用的 Key `.mc` 谱面包共用此导入路径。
- `.mr`：已核验 Malody 4.x 的二进制头部、按键/松键、A–E 判定档、
  Flip、Dash 1.2×、Rash 1.5×、Slow 0.8×；视频和音频使用相同倍率。
- Malody 判定采用头部一次判定，使用 BEST/COOL/GOOD/MISS 标签；
  不套用 osu 长条尾判定。判定还原沿用参考项目规则，不能保证每一条与游戏完全一致。
- 回放优先按原始谱面 MD5 精确匹配。Malody 导入 osu 谱面后 MD5 可能改变：
  V 回放可匹配原 OSZ，同时要求曲名、难度名、音符总数、各轨道数量和全部
  判定时间吻合（每个判定在对应音符的 150ms 内），并且仅有一份不同哈希的
  谱面符合条件。多份符合时要求选择难度，不仅凭曲名配对。
- Malody V `.mrv` 使用 Protobuf，直接读取原始按键、逐次判定和连击快照。
  已核验电脑端、原速、Const + 长条全部转单键的组合（位掩码 16392）；
  长条转为原开始时间的单键，Const 使用恒定时间距离，BPM 标签仍显示谱面 BPM。
  未核验的 V Mod 组合明确拒绝，不套用 4.x 的位定义。
- 不支持 Malody 特有皮肤、非 Key 模式及负数 Scroll。OM 使用现有 osu mania 皮肤，
  V 使用 MRM 自身的判定轨迹画面。

## 安装 MRM

渲染节点安装 JDK（推荐 17/21）与 FFmpeg，进入 `renderer` 运行：

```bash
python tools/setup_mrm.py
# 或使用提前下载的官方发布包：
python tools/setup_mrm.py --archive /path/to/ManiaReplayMaster.v2.4.0.zip
```

安装器固定校验官方 v2.4.0 ZIP 和 JAR 的 SHA256，然后编译 `mrm_bridge/Bridge.java`。
发布包与编译产物保存在忽略的 `vendor/mania-replay-master`，源码、安装器和许可证可上传仓库。
服务端 `engine=mrm` 必须携带回放；引擎缺失或报错会返回失败。
每个任务启动独立 JVM，独立临时目录，超时终止包括 FFmpeg 在内的进程树。

## 来源与验证

格式和判定参考 [Mania-Replay-Master](https://github.com/Mania-Visualization-Project/Mania-Replay-Master)，
尤其是 `MalodyReplayReader.kt`、`MalodyMapReader.kt` 和 `MalodyJudger.kt`，
该项目以 Apache-2.0 发布。V 的 OSR/MR 使用官方回放读取器及判定器，然后调用官方
绘制和编码类；MRV 使用已核验的 Python 解析器，将原始判定和按键传入官方绘制类。
OM 的 Malody 支持仍使用 Python 解析与 WebGL 输出。
参考项目的 Malody 范围是 4.x，不能据此推断 V 回放格式。

回归工具：`tools/test_malody_input.py`、`tools/test_malody_replay.mjs`、
`tools/test_v_command.py`。覆盖时间换算、素材、MD5 配对、倍速、判定、难度选择及错误格式。
2026-10-10 已完成独立端口及实际运行节点的自动播放、Malody 回放短视频渲染，
确认 H.264、AAC、60fps 和 1.2× 音画倍率一致。服务器插件的六项指令测试通过，
部署后确认插件正常加载、AstrBot 面板及渲染连接返回 HTTP 200。
2026-10-11 大小写修复已通过本机和服务器真实 AstrBot 注册过滤器测试，
已部署到三个 osu 插件，重启后面板 HTTP 200。新增 MRV 解析及配对的六项测试通过；
用户真实回放的按下、松开均为 2,275 次，最大连击为 1,042。
已使用用户提供的 OSZ 完整渲染 Alpha：2,265 次判定逐轨配对，29 根长条转换为
单键，使用原包 Ja.mp3；输出 1280×720、60fps、H.264/AAC，时长约 139.1 秒。
上述 1280×720 验证是此前 WebGL 输出。2026-10-11 已改为 MRM：Alpha 完整输出
540×960、60fps、H.264/AAC，约 141.1 秒（含末尾两秒）；判定数
BEST 2234 / COOL 22 / GOOD 3 / MISS 6 与 MRV 完全一致。
`tools/test_mrm_engine.py` 实际调用官方 JVM 渲染 OSR 和 1.2× MR；
`tools/test_v_command.py` 验证 MRM 与 OM 路由、曲包选择、实际 multipart 引擎字段。
MRM 已同步实际 Windows 渲染节点和服务器 AstrBot；服务器九项指令测试通过。
重启后插件正常加载、面板 HTTP 200，服务器隧道可读取 MRM 完成任务与对应判定数。
