# 第三方回放渲染器来源

本项目的 `v` 回放功能调用 **Mania-Replay-Master v2.4.0**。

- 原仓库：[Mania-Visualization-Project/Mania-Replay-Master](https://github.com/Mania-Visualization-Project/Mania-Replay-Master)
- 使用版本：[v2.4.0 发布包](https://github.com/Mania-Visualization-Project/Mania-Replay-Master/releases/tag/v2.4.0)
- 原作者声明：Copyright (c) 2020-present, project contributors.
- 许可：Apache License 2.0，完整副本见 [Mania-Replay-Master.txt](Mania-Replay-Master.txt)。

本仓库新增 `mania_render/mrm_render.py`、`mrm_bridge/Bridge.java` 和 AstrBot 接口，用于传递文件、参数及渲染状态。JVM 回放渲染核心由原项目提供。运行依赖通过 `tools/setup_mrm.py` 下载，缓存、JAR、回放文件和谱面包不随本仓库提交。
