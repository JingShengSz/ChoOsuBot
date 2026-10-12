# 验证和交付记录

日期：2026-10-10。

## 范围

- 官方 API 索引：101 条路径、120 个 method/path 组合，55 个公开 JSON 查询可调用。
- AstrBot LLM 工具：9 个。
- 客户端使用 `public` 应用令牌；测试没有开启个人授权或执行账号写操作。

## 离线测试

30 项 pytest 测试通过。覆盖接口权限、路径隔离、数组／分页编码、Mod 参数、输出裁剪与游标保留、凭据报错脱敏、401 重取令牌、429 等待期、并发请求合并、缓存、工具 docstring 参数，以及常用工具的返回字段。

Ruff 静态检查与格式检查通过。

Windows 沙箱不能创建 asyncio 事件循环所需的内部 socketpair，因此离线异步测试在隔离的工作区 venv 中、沙箱外运行。测试只使用合成凭据和模拟 HTTP，不读取用户 OAuth 文件。

## 服务器真实查询

在 `/opt/astrbot/.venv/bin/python` 的独立验证进程执行，真实框架成功注册全部 9 个工具。验证进程不与用户聊天、不重启 AstrBot。

| 查询 | 结果 |
|---|---|
| F6A8AF 的 mania 玩家资料 | 成功；有头像、总 PP 和 team 字段 |
| 谱面 `5111622` | 成功；原始星数 `8.74592` |
| 谱面 `5111622` + DT | 成功；`star_rating = 11.070799827575684`，显示到两位为 `11.07` |
| 玩家 recent，包含失败，limit=1 | 应用令牌查询成功，返回 1 条 |
| 中国 mania PP 排行第 2 页 | 成功，返回 50 条 |
| 搜索 Executioner，mania，any | 成功，返回 50 个谱面集 |

以上证明常用查询与真实 AstrBot 注册链路可用；没有对全部 55 个接口逐一发送线上请求，也没有进行聊天平台端到端对话测试。测试时点的数据可能变化。

## 文件状态

OAuth 源文件按用户指定路径通过 SCP 直接复制，未打开或输出内容。服务端文件：

```text
/opt/astrbot/data/plugin_data/astrbot_plugin_osu_tools/osu_oauth.local.json
```

权限 `600`。真实验证时客户端在服务进程内读取该文件，输出仅包含验证标志和上表中的公开数值。

2026-10-10 已安装到 `/opt/astrbot/data/plugins/astrbot_plugin_osu_tools/`，通过重启 AstrBot 加载。启动日志确认插件加载成功，9 个工具全部注册，服务恢复运行。

服务器现有 osu-malody MCP 包含 `osu_get_user`，因此本插件玩家资料工具使用 `osu_get_player`，避免工具名称冲突。README 和安装包已同步更新。
