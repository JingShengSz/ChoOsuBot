# osu! API 调用与研究记录

## 1. 来源和覆盖范围

本次同时检查官方 Wiki、API 文档和官方 GitHub：

| 来源 | 用途 |
|---|---|
| [osu!api Wiki](https://osu.ppy.sh/wiki/en/osu!api) | 区分 v1 和 v2 的官方入口 |
| [osu-web API 文档](https://osu.ppy.sh/docs/index.html) | OAuth、权限、参数、响应对象 |
| [OpenAPI YAML](https://osu.ppy.sh/docs/openapi.yaml) | 101 条路径，120 个 method/path 组合 |
| [Postman collection](https://osu.ppy.sh/docs/collection.json) | 官方交互请求集合入口 |
| [osu-web routes/web.php](https://github.com/ppy/osu-web/blob/master/routes/web.php) | 核对路由、可选路径参数、客户端路由和内部路由 |
| [UsersController](https://github.com/ppy/osu-web/blob/master/app/Http/Controllers/UsersController.php) | 用户、成绩、公开 scope；用户名规则 |
| [ScoresController](https://github.com/ppy/osu-web/blob/master/app/Http/Controllers/ScoresController.php) | 统一成绩 ID、旧 ID 和回放 |
| [BeatmapsController](https://github.com/ppy/osu-web/blob/master/app/Http/Controllers/BeatmapsController.php) | Mod 难度属性和谱面查询 |
| [BeatmapsetsController](https://github.com/ppy/osu-web/blob/master/app/Http/Controllers/BeatmapsetsController.php) | 谱面集查询及 lookup |
| [BeatmapsetSearchRequestParams](https://github.com/ppy/osu-web/blob/master/app/Libraries/Search/BeatmapsetSearchRequestParams.php) | 官方文档尚未写完的搜索参数 |
| [Users/LookupController](https://github.com/ppy/osu-web/blob/master/app/Http/Controllers/Users/LookupController.php) | 批量 ID／用户名查询，最多 50 项 |
| [RankingController](https://github.com/ppy/osu-web/blob/master/app/Http/Controllers/RankingController.php) | 排行榜 cursor、page、sort 和 type 别名 |
| [TeamsController](https://github.com/ppy/osu-web/blob/master/app/Http/Controllers/TeamsController.php) | 战队 ID／@简称查询 |
| [ppy/osu-api Wiki](https://github.com/ppy/osu-api/wiki) | 旧版 v1 的 7 个数据接口和素材 URL |
| [AstrBot AI 工具指南](https://docs.astrbot.app/dev/star/guides/ai.html) | `@filter.llm_tool`、docstring 参数、返回字符串 |

快照日期和源码 commit 保存在 `api_catalog.json`。本插件不会运行时下载 GitHub 代码，也不根据网站返回文字执行指令。

## 2. v2 的基本调用

### 应用令牌：本插件使用

先在 [账号设置](https://osu.ppy.sh/home/account/edit) 注册 OAuth Application。只使用 client credentials 时不需要回调服务器。

```http
POST https://osu.ppy.sh/oauth/token
Accept: application/json
Content-Type: application/json

{"client_id":123,"client_secret":"<由服务端读取>","grant_type":"client_credentials","scope":"public"}
```

响应中的 `access_token` 放入请求头；`expires_in` 是秒数。应用令牌没有用户身份，也没有可供本插件使用的用户 refresh token。

```http
GET https://osu.ppy.sh/api/v2/users/2/mania
Authorization: Bearer <只存在于服务进程>
Accept: application/json
x-api-version: 20220705
```

`x-api-version` 控制响应格式，不是 OAuth 版本。插件固定使用 `20220705` 的 Score 格式；省略请求头会被当作版本 0。需要 daily_challenge 房间等不同版本行为时，先评估响应兼容性再修改客户端。

### 用户授权：仅供未来扩展参考，本插件没有开放

1. 用户浏览器访问 `GET /oauth/authorize`，参数包含 `client_id`、`redirect_uri`、`response_type=code`、`scope`、随机且有有效期的 `state`。
2. 服务端回调核对 `state` 与原发起用户，检查回调 URL 与注册值完全一致。
3. `POST /oauth/token` 传 `grant_type=authorization_code`、`client_id`、`client_secret`、`code`、`redirect_uri`。
4. 服务端保存该用户的 `access_token`、`refresh_token`、过期时间和 scopes，按用户隔离。不能把管理员的 token 作为全体聊天用户的身份。
5. 过期后用 `grant_type=refresh_token` 换取新令牌；同时保存新 refresh token。撤销使用 `DELETE /api/v2/oauth/tokens/current`。

授权码、应用令牌、用户令牌和 v1 API key 不能混用。这里记录调用流程，不启用授权回调或写操作工具。

### scope 清单

| scope | 用途 |
|---|---|
| `public` | 公开数据查询 |
| `identify` | 获取授权用户自身资料，例如 `/me` |
| `friends.read` | 授权用户好友 |
| `chat.read` | 读取聊天 |
| `chat.write` | 发聊天消息 |
| `chat.write_manage` | 管理聊天频道加入／离开 |
| `forum.write` | 发表／编辑论坛内容 |
| `forum.write_manage` | 管理论坛主题 |
| `multiplayer.write_manage` | 另一套 SignalR 多人房间管理 API |
| `delegate` | 仅特定 Bot 的应用令牌可代理应用所有者 |
| `group_permissions` | 特定 delegation 场景继承用户组权限 |

不要以为有 `public` 就能调用全部 GET。标记 `requires user` 的接口需要用户身份；标记 `lazer` 的接口不对普通 authorization-code/client-credentials 应用开放。聊天 scopes 和 delegation 还有限制，见[官方权限说明](https://osu.ppy.sh/docs/index.html#scopes)。

## 3. 参数、分页和字段

- `mode` / `ruleset`：`osu`、`taiko`、`fruits`、`mania`；数字形式分别是 `0`、`1`、`2`、`3`。
- 路径用户名使用 `@name`，然后 URL 编码。老的 `key=username` 已弃用，不用于新代码。
- 不同列表分别用 `limit+offset`、`cursor_string` 或 `cursor[page]`。不要把一种分页方式复制到所有接口。
- URL 数组使用重复键：`ids[]=2&ids[]=3`、`mods[]=HD&mods[]=DT`。JSON body 中的 `mods` 则是真数组或 bitset。
- 返回 `null` 表示缺失或不适用，不强制转 0。成绩对象新旧格式不同，不混用 `statistics` 和旧式 `count_300` 等字段。
- API 的成绩 PP 由服务端返回；`POST /beatmaps/{beatmap}/attributes` 用于星数等难度属性，不是通用 PP 计算器。

### 常见资料的位置

| 信息 | API 返回字段／接口 |
|---|---|
| 玩家名 | User `username` |
| 头像 | User `avatar_url` |
| 总 PP | 指定模式 User `statistics.pp` |
| 全服／国家排名 | `statistics.global_rank` / `statistics.country_rank` |
| 战队 | User `team`；详细数据 `GET /teams/{team}/{ruleset?}` |
| 单局 PP | Score `pp` |
| 歌曲名／曲师 | Beatmapset `title` / `artist`，Unicode 版本按需取 |
| 难度名 | Beatmap `version` |
| 谱面状态 | Beatmapset `status` |
| 封面图片 | Beatmapset `covers` |
| Mod 后星数 | difficulty attributes 的 `star_rating` |

更多对象字段见官方文档的 User、Score、Beatmap、Beatmapset、TeamExtended 章节；通用工具的 `fields` 使用点路径选择。

## 4. GitHub 核对发现的差异

1. **鉴权信息不全**：OpenAPI 的很多操作写成 `security: []`，HTML 却标有 OAuth/scope。插件按 HTML 标签和源码判断，不误开放私人信息。
2. **operationId 重名**：`GET /scores` 与房间 playlist 分数列表都叫 `getScores`。本地分别命名 `getGlobalScores`、`getPlaylistScores`，保留原 ID 便于追溯。
3. **可选参数生成错误**：用户、战队、自身资料的模式参数可省略。Scribe 生成的路径参数列表中还有额外 `mode`，本地已过滤。
4. **用户名类型**：规范把 user 写为整数，但源码和文档支持 `@用户名`。本地 `getUser` 路径类型修正为字符串。
5. **谱面搜索**：文档还是 TODO。补入 `q/m/s/sort/g/l/nsfw/c/e/page/played/r/query`；`played`、自己的评级和收藏等仍取决于用户身份，应用令牌不能提供个人筛选结果。
6. **批量玩家**：`/users/lookup` 支持 `ids` 字符串数组、`ruleset_id`、`exclude_bots`，本地补齐。
7. **排行榜**：源码接受 `performance`、`score` 作为全局排行的兼容别名；也有 `global/team` 配合 `sort`。插件常用工具使用兼容形式，通用目录补齐 page/sort。
8. **recent 权限**：当前 UsersController 把 scores 列入 `public`。不能沿用旧记录里“应用凭据总是 404”的绝对判断；具体结果以实际调用为准。
9. **弃用接口**：`/beatmaps/{beatmap}/solo-scores` 改用 `/beatmaps/{beatmap}/scores` 配合响应版本头。

源码中的 `_lio` 路由是内部系统互操作接口；网站账号 session、管理后台和游戏客户端专用调用都不视为第三方稳定 API。仅在源码发现的方法不自动开放为 LLM 工具。

## 5. 旧版 v1：7 个主要数据接口

基础地址是 `https://osu.ppy.sh/api/`，不是 `/api/v1/`。每个请求使用查询参数 `k=<旧版 API key>`；本次 OAuth 文件不能替代这个 key。本插件不实现 v1 请求，以下用于维护旧模块。[官方 v1 Wiki](https://github.com/ppy/osu-api/wiki)

| 方法／路径 | 作用 | 关键参数（除 k） |
|---|---|---|
| `GET /api/get_beatmaps` | 谱面元数据 | `b` 单难度、`s` 谱面集、`u/type`、`since`、`m`、`a`、`h` hash、`limit`、`mods` |
| `GET /api/get_user` | 玩家资料 | `u`、`type`、`m`、`event_days` |
| `GET /api/get_scores` | 单图排行榜 | `b`、`u/type`、`m`、`mods`、`limit` |
| `GET /api/get_user_best` | 玩家 BP | `u/type`、`m`、`limit` |
| `GET /api/get_user_recent` | 玩家最近成绩 | `u/type`、`m`、`limit` |
| `GET /api/get_match` | 旧多人比赛记录 | `mp` 比赛 ID |
| `GET /api/get_replay` | 回放压缩数据 | `s` 成绩 ID，或 `b+u`；另有 `m/type/mods` |

v1 很多数值以字符串返回，空结果往往是空数组。Mods 是整数位标志，不能直接放 `"DT"`。`get_replay.content` 是 base64 编码的压缩回放流，缺少完整 `.osr` 头，不能简单改文件扩展名当作完整回放。该接口有单独的低限速，Wiki 标注 10 次／分钟。

## 6. 图片、谱面文件和多人实时接口

### 图片

优先使用 API 返回的 `avatar_url`、`covers`，无需重新猜 URL。v1 Wiki 也记录以下公开图片形式：

```text
https://a.ppy.sh/{user_id}
https://assets.ppy.sh/beatmaps/{beatmapset_id}/covers/cover.jpg
https://b.ppy.sh/thumb/{beatmapset_id}l.jpg
```

封面用 **beatmapset_id**，不是单个难度 ID。封面是网站裁剪图，不保证是谱面原背景。

### 原始谱面与原背景

本仓库已有 `.osu` 获取及 `.osz` 解析模块。公开的 `GET https://osu.ppy.sh/osu/{beatmap_id}` 返回谱面文本；文本里 `[General]` 的 `AudioFilename`、`[Events]` 的背景条目指向谱面包内文件。

原背景需要读取获授权获取的谱面包，并按 Events 中的相对路径取文件；不能把 cover 当原图。API v2 的 `/beatmapsets/{id}/download` 在当前文档中标记 lazer，本插件不拿应用令牌绕过限制。[.osu 格式 Wiki](https://osu.ppy.sh/wiki/en/Client/File_formats/osu_(file_format))

### SignalR

osu! 的裁判／多人房间实时控制属于独立 API，不是给 `/api/v2` 添加一个路径就能调用。入口见[Referee hub API](https://ppy.sh/osu-server-spectator/referee-hub-api.html) 和 [ppy/osu-server-spectator](https://github.com/ppy/osu-server-spectator)。需要对应权限和连接生命周期管理，本查询插件不建立实时连接或管理房间。

## 7. 错误处理和使用约束

| 情况 | 处理 |
|---|---|
| 401 | 重新取一次应用令牌；仍失败检查应用配置 |
| 403 | 检查 scope、用户身份、客户端限制、资源可见性 |
| 404 | 检查 ID 是否正确，score 是否混用 stable/统一 ID，模式是否正确 |
| 422 | 检查参数及 Mod 组合，不用重复相同错误请求 |
| 429 | 遵守 Retry-After，稍后重试；不要并行绕过限流 |
| 5xx／网络失败 | 有限退避，不能无限重试 |
| 空列表 | 当前查询条件下没有记录，不代表账号永远没有数据 |

官方建议不超过每分钟 60 次请求，复用缓存，不把 API 当本地数据库、批量抓取全部用户和成绩。大规模研究数据应查看 [data.ppy.sh](https://data.ppy.sh)，不是频繁轮询 API。[官方使用条款](https://osu.ppy.sh/docs/index.html#terms-of-use)

## 8. 如何更新这份索引

1. 下载公开的 `openapi.yaml`、`index.html`，查询 GitHub osu-web `master` 的 commit 元信息，保存为 `commit.json`。
2. 在对应源码版本核对控制器、权限中间件、参数类和弃用说明。
3. 运行 `python tools/build_catalog.py <源文件目录>`。
4. 审查新增开放项，尤其是身份相关 GET、下载、deprecated/lazer 标记。
5. 更新日期、补充项和测试，再生成插件 ZIP。不要将 OAuth 文件放入源目录、ZIP 或 Git。
