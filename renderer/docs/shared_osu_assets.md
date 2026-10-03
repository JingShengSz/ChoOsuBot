# osu! 玩家资料与成绩素材公共入口

## 入口位置

- `mania_render/osu_api.py`：官方 API 认证、成绩、玩家资料及 `PlayerProfile`。
- `mania_render/fetch.py`：OM 与成绩图共用的谱面原始背景获取、镜像回退和缓存。
- `mania_render/score_assets.py`：组合以上入口，返回成绩、玩家资料、头像文件和背景文件。
- `tools/fetch_score_assets.py`：本地命令行调用入口，不包含重复实现。

以上函数都是同步阻塞调用。异步机器人中用 `await asyncio.to_thread(...)`，避免阻塞消息处理。

## 玩家字段约定

| 公共字段 | 官方字段 | 说明 |
|---|---|---|
| `user_id` | `user.id` | 稳定玩家 ID，用于后续查询 |
| `username` | `user.username` | 当前显示名，不应写死到模板 |
| `avatar_url` | `user.avatar_url` | 保留官方完整 URL，包括版本查询参数；可能为空 |
| `total_pp` | `user.statistics.pp` | **当前指定模式**的总 PP，不是本次成绩 PP，也不是游玩当时总 PP |
| `ruleset` | 调用时明确指定 | `osu` / `taiko` / `fruits` / `mania` |
| `team` | `user.team` | 官方战队对象，通常含 `id/name/short_name/flag_url`；无返回值时为 `None`，不是国家信息 |
| `global_rank` | `user.statistics.global_rank` | 当前该模式世界排名，可为空 |
| `country_rank` | `user.statistics.country_rank` | 当前该模式国家排名，可为空 |

缺失总 PP 返回 `None`，真实零 PP 返回 `0.0`，不得互相替代。
成绩内嵌的 `user` 可能不完整，因此 `api.player()` 会单独请求 `/users/{id}/{ruleset}`。
战队旗帜 URL 已保留在 `team.flag_url`，本次工具不额外下载旗帜。

```python
from pathlib import Path
from mania_render.osu_api import OsuApi
from mania_render.score_assets import fetch_score_assets
from mania_render.fetch import get_beatmap_background, get_background

# 在 renderer 目录运行；其他目录请给配置和 cache 使用绝对路径。
api = OsuApi.from_file(Path('data/osu_oauth.local.json'))
player = api.player(32749965, 'mania')
print(player.username, player.total_pp, player.team)

bundle = fetch_score_assets('https://osu.ppy.sh/scores/6645548845', api, Path('cache'))
score_pp = bundle['score']['pp']
total_pp = bundle['player']['total_pp']
avatar_file = bundle['avatar_path']
background_file = bundle['background_path']

# 只获取背景，不下载回放或音频，也不需要成绩链接。
background = get_beatmap_background('5493536', Path('cache'))
# 已有 OM 解析出来的谱面集 ID / 背景文件名时：
# background = get_background(set_id, background_filename, Path('cache'))
```

## 背景策略与复用关系

`.osu` 的 Events 背景文件名 → 单文件镜像 → 整包镜像/已有用户令牌可用时的官方包 → 指定文件。
不会改用官方裁切 cover，也不会取压缩包里任意一张图片冒充背景。
文件路径大小写不敏感匹配；只有 basename 唯一时才允许忽略目录匹配。
未声明背景返回 `None`；声明了但获取失败会抛出异常，由调用方决定展示错误或占位图。

`load_beatmap_by_id()`（OM CLI/服务端渲染）与 `/api/bg/`（OM 浏览器渲染）均已调用
`get_background()`，成绩素材也走同一函数。缓存键包含谱面集 ID 和完整文件名摘要，
避免同一谱面集的不同难度串背景。旧 `cache/audio/*_bg.*` 不作为新入口缓存复用。
网络内容先写临时文件，检查图片签名后再原子发布；这能拦住 HTML/JSON 错误页，
但不是完整图像解码校验。项目静态 API 服务仍只依赖 Python 标准库。

## 本地运行与凭据

```text
python tools/fetch_score_assets.py https://osu.ppy.sh/scores/6645548845
python tools/test_shared_osu_assets.py
```

配置默认在 `renderer/data/osu_oauth.local.json`，填写 `osu_client_id` 和 `osu_client_secret`。
`OsuApi` 在内存缓存客户端 token，不打印密钥、请求头或 token，也不将 token 保存到结果。
`bundle.json` 仅保存公开资料及本地素材路径，位置为 `cache/scores/<score_id>/bundle.json`。
获取玩家资料使用 public 客户端凭据；官方谱面整包下载仍沿用 OM 的用户级 token 机制，
二者不能互相替代。

## 本次实际验证（2026-10-03）

成绩 `6645548845`：玩家 `F6A8AF`（32749965），mania，成绩 PP `147.902`；
当前模式总 PP `9485.6`；战队 `MSS / Millennium Science School`（472）。
谱面 `5493536`，谱面集 `2498268`。这些是本次查询快照，后续应重新获取。

现有 AstrBot 插件的异步 OAuth/回放链路仍保留；它的部署包与渲染服务独立。
后续整理若改接公共客户端，应同时确认打包路径与异步调用方式，不能直接删去旧链路。
