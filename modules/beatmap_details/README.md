# 谱面详情

此目录保存谱面分析器的上游源码快照和三页 Detail Pro 渲染模块。

- 来源：https://github.com/LeoBlackMT/osumania_map_analyser
- 固定提交：`a44acf463679d57d46e4249afeb9adc2b816c3e0`
- 复制日期：2026-10-09
- 许可：MIT；原许可与作者声明保存在 `upstream/LICENSE`。
- `upstream/` 为完整源码快照，不包含上游 `.git`。
- 分析核心位于 `upstream/ManiaMapAnalyser by Leo_Black/js/`。
- 参数清单见 `PARAMETERS.md`。

AstrBot 使用 `dtlp5812833`、`dtlp 5812833` 查询指定谱面，`dtlp` 使用本聊天最近成功发送的 p/r 谱面，不限发送者，无需绑定账号。返回三页图片，包含 Density/NPS 图。QQ 群聊和私聊使用一条合并转发的详情聊天记录，按顺序放入三页与标题，不发送生成提示；其他平台保留三图发送方式。

默认分析范围：osu!mania、无 Mod、1.0×、Stable/Classic。不能计算的算法会标注不可用；Companella 模型适用范围是 4K。

`dtl4312004` 或 `dtl 4312004` 返回单张预测卡片；`dtl` 使用本聊天最近 p/r 的谱面，无需绑定账号。包含镜像立绘、预测段位、SUNNY 星数、MSD、密度曲线与每 10 秒键型标注。常规与 LN 双结果一起显示，LN 图案位于右侧并缩小；Reform 1–10 使用专用透明数字，未确定段位的 Vibro 使用问号图案。

两条指令均可回复 `.osz`、Malody Key `.mcz/.zip/.mc` 文件。多难度回复列表编号选择；选择列表保存指令类型与倍率，也可用 `2 dt` 或 `2 1.2` 覆盖。仅预测谱面文件，Malody `.mr` 是回放文件，不作为谱面导入。

倍速参数直接写：`dt` 为 1.5×，`ht` 为 0.75×，`1.2` 指定自定义速度（0.1～3.0）。例如 `dtl 4312004 dt`、`dtlp 4312004 1.2`、`dtl 4312004 0.5`，或回复文件发送 `dtl ht` / `dtlp 1.2`。HT/DT/自定义速度只能指定一项；不指定时为 1.0×。旧 `-dt`、`-ht`、`-rate` 写法保留兼容。倍率参与段位、星数、MSD 的实际重算；全谱键型、密度时间轴与每 10 秒窗口按游玩速度调整。

单张接口为 `GET /api/detail-compact/<谱面ID>?rate=1.2`，直接返回 PNG；三页接口同样接受 `rate`。`compact_service.py` 复用 OM 节点与 Chrome，缓存位于 `cache/dtl-green-v2-rate/<谱面ID>/rate-<倍率>/`。单张模板位于 `runtime/compact.html`，主题与段位组件位于 `assets/detail_green.css`、`assets/detail_ranks.js`。服务器经 SSH 隧道转发到 Windows 渲染节点。

2026-10-12 已部署：Windows 节点安装卡片组件；AstrBot 服务器加载 `dtl` 指令。服务器请求 `4312004` 返回有效 PNG，重复请求哈希相同；指令回归测试 7 项通过。发布包与素材保存在服务器 `data/plugin_data/astrbot_plugin_osu_scorecard/dtl-release-20261012.zip` 和 `dtl-assets/`，旧插件文件已备份到同目录 `deploy-backups/`。

回复 OSZ 文件使用 `dtlp`：通过已启用的 OM 插件导入文件；单难度直接分析，多难度回复选择列表发送编号，可带 @机器人，30 分钟内有效。详情导入接口为 `POST /api/import_detail_osz`，音频可省略。包内每个难度有独立的本地来源 ID，分析直接读取上传内容，避免用包内官服 ID 查成别的谱。列表按聊天、用户和本次选择隔离；`dtlp 2` 仍表示查询官服谱面 ID 2。

`service.py` 在 OM 本机节点分析和截取三页；`runtime/` 保存通用模板、分析入口与依赖锁文件。安装依赖时进入 `runtime/` 执行 `npm ci`。渲染节点需要 Python、Node.js、现有 OM Chrome/CDP 环境。接口为 `GET /api/detail/<谱面ID>`，返回包含三张 PNG 的 ZIP；AstrBot 的 `detail_server` 默认使用现有节点地址 `http://127.0.0.1:8760`。

缓存位于 `cache/dtlp-v4/<谱面ID>/`，版本由 `service.py` 的 `VERSION` 控制；模板或算法变化时应更新缓存版本。原始分析 JSON 保存在同目录，参数清单见 `PARAMETERS.md`。无长条谱面可能没有 SunnyWindow 的分类数据，模板应显示缺少分类的说明并继续生成其余详情。

倍速版本三页缓存已升级为 `cache/dtlp-v5-rate/<谱面ID>/rate-<倍率>/`，避免不同倍率返回同一旧图片。2026-10-12 文件/倍率更新验证：26 项详情指令测试、8 项 Malody 转换测试通过；真实导入 OSZ 与 Malody MC 后均成功生成 DT 单卡和 HT 三页，自定义 1.2× 通过，非有限倍率返回 400。

上游原应用的实时数据来源、匿名统计和设置界面属于原应用行为；复制源码不会启动它们。
