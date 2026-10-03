# astrbot_plugin_osu_scorecard

把一个 osu! 成绩渲染成 1920×1080 的成绩卡图片，发到聊天里。

官服（osu.ppy.sh）和 **SB 私服（osu.ppy.sb）** 都支持 —— 指令后面加 `-sb` 就是私服。

卡片本体是本机的 PSD 模板，插件用 COM 驱动 Photoshop 填写字段、换背景、按评级换立绘与配色，
再导出 PNG。星级条和 OD/HP 条按每局的数值用 Pillow 实时画。

> v1.1 起默认**不走 Photoshop**，改用纯 Pillow 渲染同一套版式（0.46 s vs 27~34 s）。
> 见下面「渲染引擎」。

---

## 指令

| 指令 | 作用 |
|---|---|
| `p` | 最近**通过**的一个成绩 |
| `r` | 最近**游玩**的一个成绩（没通过也算） |
| `s <成绩ID 或 链接>` | 指定一个成绩，例：`s 6645548845` |
| `bind <osu!用户名>` | 把 osu! 账号和你的 QQ 绑定，例：`bind Cookiezi` |
| `authorize` | 重新要一个官服授权链接（绑定后没授权、或链接过期时用） |
| `mode <模式>` | 切换绑定账号的模式（`osu` / `taiko` / `fruits` / `mania`） |
| `help` | 简洁的帮助信息 |

**不需要指令**：消息里出现 `https://osu.ppy.sh/scores/<数字>` 或
`https://osu.ppy.sh/community/scores/<数字>` 就会自动渲染（可以用 `auto_link` 关掉）。

群聊里回复会 @ 你；私聊直接发图。

> **官服的 `p` / `r` 要先授权一次。** `bind` 之后机器人会回一条带授权链接的消息，
> 点开点「Authorize」就完事，之后 `p` / `r` 一直能用（凭据会自动续期）。
> `s <成绩ID>`、贴成绩链接、以及全部的 `-sb` 指令**都不需要授权**。
> 详见下面的「官服授权」。

---

## 私服（SB / ppy.sb）

**任何一条指令后面加 `-sb`，就是查私服的成绩。**

| 官服 | 私服 |
|---|---|
| `bind Cookiezi` | `bind Cookiezi -sb` |
| `mode mania` | `mode mania -sb` |
| `p` | `p -sb` |
| `r` | `r -sb` |
| `s 6645548845` | `s 5030104 -sb` |

`-sb` 必须写在**最后**，前面要有空格。也接受 `--sb` 和 `-私服`。
写成 `bind Foo-sb` 不会误判 —— 用户名里的 `-sb` 不算。

### 官服和私服是两本账，绑定也是

私服是另一套账号体系：同一个人在官服叫 `Cookiezi`，在私服可能压根没号，或者同名却是
另一个人。所以**绑定按服分开存**，一个 QQ 可以同时绑两边：

```
bind Yama7u7          -> 官服 记录
bind SomeName -sb     -> 私服 记录     两条互不影响
mode mania -sb        -> 只改私服那条
```

玩家资料缓存（总 PP / 排名 / 头像）也是按服分开的，否则官服查出来的总 PP 会被私服的
查询命中。

### 卡片上怎么区分

谱面 ID 旁边多了一格：

| 服务器 | 显示 | 颜色 |
|---|---|---|
| 官服 | `官方` | 灰 `#8C96A9` |
| SB 私服 | `SB 私服` | 青 `#4FC3F7` |

两边都显式写出来（而不是「私服才标、官服留空」）是刻意的：留空这种约定，看图的人
不知道是「官服」还是「这格没做」。青色是挑过的，和九套评级色都不撞。

### 私服不需要任何凭据

官服的 `/scores/recent` 必须要用户授权（见「官服授权」），**私服不需要** ——
给用户名或 id 就能查最近成绩。所以 `-sb` 一加上就能用，`sb_api_url` 那项也不用填密钥。

接口来源：`https://api.ppy.sb/` 是个 FastAPI 服务，自带 `/openapi.json`。

### 私服的三个坑（都实测过）

1. **两个成绩接口的形状不一样**，这是最坑的一个：

   | 接口 | 内嵌 `beatmap` | `userid` |
   |---|---|---|
   | `/v1/get_player_scores`（`r -sb` 走这条） | 有 | **没有** |
   | `/v1/get_score_info`（`s -sb` 走这条） | **没有** | 有（外加 `map_md5`） |

   只按其中一种写，另一个指令就会静默出问题：`s <id> -sb` 会得到一张没有曲名/难度/
   满连的空卡，`r -sb` 的 TOTAL PP 永远是空的。两种形状都得兼容。

2. **`score.beatmap.max_combo` 是脏数据。** 它永远等于 `score.max_combo`（玩家的连击），
   不是谱面满连。真值只能另外调 `/v1/get_map_info?md5=`。实测同一条成绩：玩家 945、
   谱面 3228。

3. **`mods` 是 stable 位掩码整数**，不是官服的缩写列表，得自己解码。键数 mod（4K/5K…）
   对 mania 卡片是噪音，解码后丢掉。

另外 `/v1/calculate_pp` 返回 401（要授权），所以私服成绩的理论 PP 还是本地自己算。

---

## 依赖

这不是一个纯 Python 插件，它需要**同机装好的 Adobe Photoshop**。

| 需要 | 说明 |
|---|---|
| Adobe Photoshop | 装了就行，插件通过 COM 自己把它拉起来 |
| `D:\Cho Osu Bot\template\` | 模板 PSD + 素材（`assets/mods/ready`、`assets/rank_svg`、`assets/signboards`） |
| osu! OAuth 凭据 | 见下面「配置」和「官服授权」 |

osu! API 客户端（`osu_api.py`）已经 **vendored 进插件目录**，纯标准库实现，
所以插件是自包含的：**不需要**外部的 `renderer/` 目录，服务器上也不用额外装渲染器。

Python 侧不需要额外装东西 —— AstrBot 自带的虚拟环境已经有 Pillow / aiohttp / pywin32：

```bash
# AstrBot venv 里实测：
#   PIL 12.3.0 · aiohttp 3.14.2 · pywin32 · numpy
```

---

## 配置

在 AstrBot 网页 → 插件管理 → **osu!mania 成绩卡** 里配置。

| 配置项 | 默认值 | 说明 |
|---|---|---|
| `osu_credential_file` | `D:\Cho Osu Bot\renderer\data\osu_oauth.local.json` | **通常不用动**。渲染器已经维护着这个文件，里面有 `osu_client_id` / `osu_client_secret` 两个键 |
| `osu_client_id` | 空 | 只在上面那个文件不存在时才会用到 |
| `osu_client_secret` | 空 | 同上。**敏感信息**，不要发到聊天里 |
| `osu_data_path` | `D:\Cho Osu Bot\template\osu_score_template_v1.psd` | 模板路径 |
| `assets_path` | 空 | 留空 = 模板同级的 `assets/` |
| `renderer_path` | 空 | **已弃用**，留着只为兼容旧配置。API 客户端已内置，填了也不读 |
| `photoshop_path` | `D:\Photoshop\Adobe Photoshop 2026\Photoshop.exe` | COM 没拉起来时的兜底启动路径 |
| `default_ruleset` | `mania` | 模板是 mania 的，改别的模式版式不会跟着变 |
| `auto_link` | `true` | 消息里的成绩链接自动出图 |
| `cache_minutes` | `10` | 玩家资料（总 PP / 头像 / 全球排名）本地缓存时长，`0` = 每次重拉 |
| `output_keep` | `20` | 保留多少张渲染产物 |
| `render_timeout_seconds` | `180` | 单次渲染超时 |
| `renderer` | `auto` | `auto` / `pil` / `photoshop` |
| `pp_max_mode` | `computed` | `computed` = 按公式算理论最大 PP；`dash` = 显示 `--` |
| `spec_path` | 空 | `layer_mapping.json` 路径，留空 = 模板旁边那个 |
| `sb_api_url` | `https://api.ppy.sb` | SB 私服的 API 根地址，**不需要密钥** |
| `oauth_enabled` | `true` | 关掉 = 不启动回调服务、不主动要授权（`p` / `r` 会提示改用 `s`） |
| `oauth_callback_host` | `127.0.0.1` | 回调服务的监听地址。本机测试用 `127.0.0.1`；上了服务器要改成 `0.0.0.0` |
| `oauth_callback_port` | `6199` | 回调服务端口。被占用时插件会报一句可读的原因，不会崩 |
| `oauth_redirect_base` | 空 | 公网地址前缀，例 `https://bot.example.com`。留空 = 用上面 host:port 拼本机地址 |

**凭据不会出现在任何地方**：不进日志、不进错误消息、不进聊天回复、不进回调返回的 HTML 页面。
`_explain()` 会把异常文本里任何 token 形状的字符串先洗成 `<redacted>` 再显示。
私服那条路根本不涉及凭据，所以没有可泄漏的东西。

唯一的例外是 `refresh_token`：它**必须落盘**，否则机器人一重启所有人都要重新授权。
它存在 `data/osu_store.json` 里每条 `"osu:<QQ>"` 记录下的 `oauth` 字段里 —— 本地文件、
不进日志、不进聊天。这个文件不要外传。

---

## 渲染是怎么做的

```
osu! API  ──►  card.py      成绩 JSON → 每个文字层该显示什么字符串
                │
                ├─►  raster.py   Pillow 画：星级条 / OD-HP 条 / 头像 / mod 徽章 / 背景
                │
                └─►  psd.py      COM 驱动 Photoshop：填文字层 → 贴位图 → 切立绘 → 导出 PNG
```

### 关键设计：所有位图都预先合成到 1920×1080

交给 Photoshop 的每一张位图，都是在 Python 里就合成到一张 1920×1080 透明画布上的**最终位置**。
于是 ExtendScript 那边只需要 `duplicate(doc, PLACEATBEGINNING)` —— 复制进来就在正确坐标，
**一次 `translate` 都不需要**。

这不是洁癖，是踩出来的：这台机器上的 Photoshop 2026，
`ArtLayer.translate()` 会把位移**取反并缩放**（要 +1px 给 -63px），
而写成「读 bounds → 算差值 → 再 translate」的自校正循环会一路发散到 **y = -114000**。

### 两条 ExtendScript 铁律

| 规则 | 为什么 |
|---|---|
| 改文字颜色必须用 `new SolidColor()` | 用 `RGBColor` 报错 1200；用 ActionManager 的 `setd`/`TxLr` 会**不报错但什么都不改**（像素级验证：0 个变色像素） |
| ExtendScript 没有 `JSON` 对象 | 它是 ES3。返回值是手写序列化的 —— 一开始用 `JSON.stringify(out)` 直接报「JSON 未定义」 |

### 永远操作副本

渲染时先把模板 `copy2` 到工作目录再打开，导出后 `close(DONOTSAVECHANGES)` 并删掉副本。
渲染中途崩了也弄不坏模板。

### 并发

一个 `asyncio.Lock` 串行化渲染 —— Photoshop 一次只能跑一个文档操作。

---

## 自检

不需要 osu! 网络、不需要凭据，跑的是**冻结的真实成绩** `6645548845`（官服）
和 `5030104`（私服）：

```bash
cd D:\LLBot\bin\astrbot\data\plugins\astrbot_plugin_osu_scorecard
D:\LLBot\bin\astrbot\.venv\Scripts\python.exe self_test.py                # 全部离线阶段
D:\LLBot\bin\astrbot\.venv\Scripts\python.exe self_test.py --only sb      # 只跑私服那一节
D:\LLBot\bin\astrbot\.venv\Scripts\python.exe self_test.py --only oauth   # 只跑 OAuth 那一节
D:\LLBot\bin\astrbot\.venv\Scripts\python.exe self_test.py --full         # 再加一次全量渲染（要联网）
```

阶段：

1. **字段映射** —— 把冻在 `tests/fixture_score.json` 里的真实 API 响应喂进和插件同一条代码路径，
   逐字对齐 26 个字段（玩家名、分数、PP、两种准确率、连击、六个判定、日期、谱面信息……）。
2. **位图生成** —— 星级条 / OD-HP 条不能是空白，且要对数值有反应。
3. **插件逻辑** —— 链接识别、参数解析、命令守卫、报错脱敏、存储读写与缓存过期。
4. **私服**（`--only sb`）—— 用 `tests/fixture_sb_score.json`（从 api.ppy.sb 抓下来的
   **原始响应**）喂进 `sb_api` + `card` 这条生产路径，验 mod 位掩码解码、脏数据
   `max_combo`、以及**两个成绩接口的形状差异**。
5. **官服 OAuth**（`--only oauth`）—— 真起 HTTP 服务、真发请求、真走回调、真落盘；
   只有 `exchange_code` 和 `/me` 两个必须联网的调用用替身。见「官服授权 → 这一块的自检」。
6. **全量渲染**（`--full`）—— 含背景、头像、mod 徽章、辉光，导出后检查不是单色。

> **这一节存在的理由**：这个项目被同一个模式坑过两次 —— 测试喂的 JSON 形状和生产
> 真收到的形状不一样，于是测试全绿、线上永远显示 `--`。
> 所以第 4 节刻意用**抓下来的原始响应**，并且调**生产用的同一个函数**。
> 它第一次跑就抓到了一个真 bug（见下面「私服的三个坑」第 1 条）。

还有两个不在 `self_test.py` 里的：

| 脚本 | 用途 |
|---|---|
| `compare_engines.py` | PIL 与 Photoshop 两条路的出图差异对照 |
| `tests/make_fixture.py` | 重新抓一次真实成绩冻成 fixture |

---

## 官服授权（OAuth 授权码流程）

### 为什么非要授权不可

`/users/{id}/{ruleset}/scores/recent` 对**应用凭据（client_credentials）一律返回 404**。
实测过的所有变体全部 404：带不带 `include_fails`、`?limit=`、`/best`、`/firsts`、
用用户名代替 id、老式路径 `/users/{uid}/scores/recent/mania`。

osu! 把这个端点放在**用户授权**后面。`/users/{id}/recent_activity` 虽然 200，但事件里
`beatmap` 是 `null`、也没有成绩 id，填不了卡片的任何一格，**所以没有拿它当退路**。

只读成绩用 `scope=public` 就够，**没有申请 `identify`**，拿到的 token 读不到邮箱之类的
私密信息。

### 用户看到的是什么

```
用户:  bind F6A8AF
机器人: 已绑定 F6A8AF。
        官服 p / r 需要你先授权一次，点这个链接：
        https://osu.ppy.sh/oauth/authorize?client_id=...&state=...
        点开点「Authorize」就行。

        ← 用户在浏览器里点一下
        ← 浏览器跳到回调页，显示「授权完成，可以关掉了」
机器人: （私聊/群里）F6A8AF 授权完成，现在 p / r 可以用了。
```

确认消息是**从回调里发出去的**，不是从指令里 —— 因为点「Authorize」的那一刻
机器人并不知道用户什么时候点完。这和 yumu-bot 的做法一致。

之后 `p` / `r` 直接用。token 24 小时过期，插件会在过期前自动用 `refresh_token` 续，
用户无感。

### 需要在 osu! 那边注册应用

`https://osu.ppy.sh/home/account/edit` → OAuth → New OAuth Application。

| 字段 | 值 |
|---|---|
| Application Name | 随便，会显示在授权页上 |
| Redirect URI | 见下面 —— **必须和插件配置拼出来的完全一致** |

**Redirect URI 怎么填，取决于机器人跑在哪：**

| 场景 | Redirect URI | 能不能用 |
|---|---|---|
| 本机自测（浏览器和机器人在同一台电脑） | `http://127.0.0.1:6199/oauth/callback` | ✅ |
| 部署到有公网域名的服务器 | `https://bot.example.com/oauth/callback` | ✅ |
| 部署在服务器、但没域名没反代 | —— | ❌ 用户的浏览器回调不回来 |

填完以后把同样的值写进插件配置：用 `oauth_redirect_base`（例
`https://bot.example.com`）或者用 `oauth_callback_host` / `oauth_callback_port`
拼出来。**osu! 是逐字符比对的**，`http` 和 `https`、结尾斜杠、端口号差一个都换不到
token。

回调服务**只会在这个地址上开一个 aiohttp 端口**，不做别的。要暴露到公网就自己在前面
放 Nginx / Caddy 反代（`proxy_pass` 到 `127.0.0.1:6199` 即可，路径要原样透传）。

### 内部是怎么走的

```
① bind <名字>  →  存下绑定  →  生成一个随机 state  →  回授权链接
                              （state 不是 QQ 号本身，
                               见下面「为什么不用 QQ 号当 state」）

② 用户点「Authorize」
   osu! 把浏览器 302 到  <redirect_uri>?code=<code>&state=<state>

③ 插件自己的回调服务收到 GET，认 state：
       GET <redirect_uri>?code=…&state=…
   POST https://osu.ppy.sh/oauth/token
        {"client_id":…, "client_secret":…, "code":…,
         "grant_type":"authorization_code", "redirect_uri":<同一个>}
        -> {"access_token", "refresh_token", "expires_in": 86400}

③' 拿 token 调 /me 确认真实 user_id 和用户名 → 写进 store
   → 从回调里给这个 QQ 发一条确认消息
   → 回一个纯静态 HTML 页（页面上不含 token、不含 code）

④ p / r →  /users/{id}/{mode}/scores/recent
            Authorization: Bearer <access_token>
```

### 为什么 `state` 不是 QQ 号本身

回调是**用户的浏览器**发起的，服务器这时候只拿到 `state` 和 `code`，不知道是谁在授权。
把身份塞进 `state` 确实能解决这个问题（yumu-bot 就是这么做的），但 `state` 会出现在
用户浏览器的地址栏、可能出现在 osu! 的日志里，直接明文写 QQ 号没有必要。

这里的做法：`state` 是 `secrets.token_urlsafe()` 生成的随机串，和 QQ 号的对应关系存在
服务器本地（`data/oauth_pending.json`），900 秒过期，**取一次就作废**（防止重放）。
所以过期时间从「30 天」缩到了「15 分钟」，能拿到的东西也少得多。

### token 的续期

`access_token` 24 小时过期，用 `refresh_token` 续：

```
POST https://osu.ppy.sh/oauth/token
{"client_id":…, "client_secret":…, "grant_type":"refresh_token",
 "refresh_token":…, "scope":"public"}
```

`refresh_token` 有效期 30 天，**每次刷新会发一个新的，旧的立刻作废** —— 所以刷新后
必须把新的写回 store，否则下一次刷新就永久失败了。这一条有自检覆盖
（`self_test.py --only oauth` 里的「写回了新的 refresh_token」）。

### 为什么没用 AstrBot 的 `register_web_api()`

查过源码，**用不了**：

- `dashboard/api/plugins.py` 把插件注册的端点是挂在
  `/api/v1/plugins/extensions/<plugin_path:path>`（和旧的 `/api/plug/<plugin_path:path>`）上的，
  两个都带 `Depends(require_plugin_scope)` / `require_dashboard_user`；
- `dashboard/api/auth.py` 里没有任何「公开路径白名单」。

也就是说插件注册的端点**一律需要登录态**，而 osu! 的回调是浏览器直接跳过来的裸 GET，
带不上 AstrBot 的会话。所以这里自己起了一个 aiohttp 服务 —— 和 yumu-bot 自己起
Spring Boot 的 `callbackUrl` 是一个道理。

### 这一块的自检

```bash
python self_test.py --only oauth
```

33 项，**真起 HTTP 服务、真发 HTTP 请求、真走回调、真落盘**，只有两个必须联网的调用
（`exchange_code` 和 `/me`）用替身 —— 它们需要真实的 code，而 code 只能从 osu! 的授权页
点出来。

覆盖到：state 一次性与不可重放、`redirect_uri` 拼接、链接形状、回调页面不含 token/code、
错误 state 被拒、缺参数被拒、用户点取消、token 落盘、刷新时的 `refresh_token` 轮换、
端口被占用时给可读原因、提示文案里不含令牌。

> ⚠️ 这个 stage 能证明的是**接线是对的**，不能证明 osu! 那边的真实往返 ——
> 那一步只能在配好 `Redirect URI`、用户真点一次之后才算数（见「已知限制」）。

---

## 已知限制

### 官服授权在「没域名」的服务器上不成立

回调地址必须是**用户浏览器能访问到**的地址。所以：

- 本机自测（浏览器和机器人在同一台电脑）：`http://127.0.0.1:6199/oauth/callback` 就行。
- 部署在服务器上：必须有公网域名 + 反代，且**注册到 osu! 的 Redirect URI 与插件拼出来的
  逐字符一致**。

在这台开发机上跑不了「用户真点一次 Authorize」这一步，所以整个 OAuth 流程的
**osu! 端往返没有被真实验证过** —— 验证过的是插件这一侧的接线（见「官服授权 → 这一块的自检」）。
真部署时第一次用要盯着看一遍。

兜底：授权不可用时，`p` / `r` 会回一句可读的提示，告诉用户改用 `s <成绩ID>`、贴成绩链接，
或者加 `-sb` 查私服 —— 这三条路都不需要授权。

### `map_max_combo` 用哪个数

osu! API 的 `beatmap.max_combo` 对 mania **不可信**。同一条成绩（bid 5493536）：

| 来源 | 值 |
|---|---|
| API 的 `beatmap.max_combo` | 3243 ← **不用这个** |
| 数 `.osu` 的 HitObjects：2478 个对象（2034 普通键 + 444 长条，长条算 2 combo） | **2922** |
| 玩家这局的 `max_combo`（`is_perfect_combo` = true） | 2922 |
| 六个判定之和 | 2922 |

**卡片用的是 2922。** 决定这么定：API 那个 3243 大概是 Lazer 口径（Lazer 的
LN 尾巴单独算一个 combo），而这个模板、这群玩家看的都是 stable。

实现上不额外下载 `.osu`：`card.py` 在 `is_perfect_combo` 且玩家有 `max_combo` 时
直接取玩家的值 —— 满连时玩家的连击**就是**谱面满连，和数文件的结果一致。
`card.count_map_max_combo(osu_text)` 是那个计数器，留着给「非满连也想显示精确
满连」的场景用，目前没接进渲染路径。

### 准确率 99.53 vs 99.54

API 的 `accuracy` = `0.99536`。标准四舍五入是 99.54%，osu! 官网显示 **99.53%**（截断）。
**卡片取截断**，和官网一致 —— 玩家是拿官网对的。`card._fmt_acc` 一行就是这件事。

### 其他

- `pp_max`（理论最大 PP）：osu! API 没有这个字段，插件按 mania 的 pp 公式自己算
  「全 320 判定 + 满连」的值；算不出来或者算出来比实际 pp 还小时显示 `--`（见下）。
- `rank_change`：图层名看着像 PP 变化，但 API 只给 `rank_global`（榜位），卡片显示 `#165`。
- 背景/头像下载失败时静默跳过，卡片其余部分照常出。

---

## 与原始规格的偏离

写报告时明确列出来，方便回滚：

1. **`s` 不需要绑定**。规格说「所有 p/r/s 请求先查绑定表」。`p`/`r` 必须有绑定（没有用户名没法查），
   但 `s <id>` 的成绩本身自带玩家信息，强制绑定只会平白拦住人。`s` 因此不检查绑定。
2. **`secret: true` 没有加进 `_conf_schema.json`**。AstrBot 的 `DEFAULT_VALUE_MAP` 只认
   `int/float/bool/string/text/list/file/object/template_list/dict` 十种 type，
   `secret` 不是它支持的字段，加了会被静默忽略。改用**实际生效**的 `obvious_hint: true`
   加一段加粗警告。dashboard 会给带 `obvious_hint` 且带 `hint` 的项渲染一个 ‼️ 标记。
3. **多了几个配置项**：`osu_credential_file`、`assets_path`、`renderer_path`、
   `auto_link`、`render_timeout_seconds`、`renderer`、`pp_max_mode`、`spec_path`、
   `sb_api_url`。
4. **`photoshop_path` 是兜底用途**：正常情况 COM 会自己拉起 Photoshop，
   这个路径只在 COM 没拉起来时用来手动启动一次再重试。
5. **`-sb` 写在每条指令最后**（规格是这么定的）。识别用了正则
   `(?:^|\s)--?sb\s*$`，要求前面是行首或空白，所以用户名里带 `-sb` 不会被吃掉。
   另外接受 `-私服`。

---

## 文件

| 文件 | 作用 |
|---|---|
| `main.py` | 插件入口：指令、绑定、缓存、发送 |
| `card.py` | 成绩 JSON → 卡片字段（纯函数，可离线测） |
| `sb_api.py` | SB 私服 API 客户端 + 数据归一化（两个成绩接口的形状差异在这里处理） |
| `oauth.py` | 官服 OAuth：回调 HTTP 服务、`state` 表、回调页面 |
| `raster.py` | 星级条 / OD-HP 条 / 头像 / mod 徽章 / 背景（Pillow） |
| `psd.py` | Photoshop COM 驱动 |
| `store.py` | 绑定表、玩家缓存、**官服授权令牌**（JSON，写在 `data/plugin_data/` 下，**分服**） |
| `self_test.py` | 离线自检（含用真响应验 SB 两种形状、真起 HTTP 服务验 OAuth 回调） |
| `tests/make_fixture.py` | 拉一次真实成绩冻成 fixture（只需跑一次） |
| `tests/fixture_score.json` | 冻结的真实 API 响应，公开数据 |
| `tests/fixture_sb_score.json` | 冻结的私服响应：成绩 / 谱面 / 玩家三层都在里面 |

数据写在 `data/plugin_data/astrbot_plugin_osu_scorecard/`，**不写插件安装目录**
（升级时会被替换）。渲染产物在 `output/`，超过 `output_keep` 张就删最旧的。

---

## 渲染引擎（v1.1 起默认不走 Photoshop）

老路子（`psd.py`）每次渲染要：复制 16 MB 的 PSD → 打开 → 写 26 个文字层 →
替换 13 张位图 → 导出 PNG → 关闭。**实测 27~34 秒**，其中绝大部分就是
「打开 + 导出 PSD」本身，属于架构性的慢，调不动。

现在默认走 `render.py`（纯 Pillow），版式全部读 `layer_mapping.json`：

| | Pillow | Photoshop |
|---|---|---|
| 单张耗时 | **0.46 s** | 27~34 s |
| 加速 | **约 65 倍** | — |
| 依赖 | Pillow | Photoshop + pywin32/PowerShell |

配置项 `renderer` 控制：`auto`（默认，先 PIL 失败才退回 PS）/ `pil` / `photoshop`。

**PIL 渲染器的 z 序**（自下而上）：
`beatmap_bg` → 压暗 74.9% → `_deco_bg_gradient`(screen) → 毛玻璃底板 →
`rank_glow`(screen) → 立绘 → **static_overlay** → 头像/星级条/属性条/mod → 全部文字

### PIL 需要的额外素材

模板里有两类东西是 Photoshop 白送的、插件从不设置的：

1. **静态文字与图标** —— `_deco_*` 那一批标签（TOTAL PP / SCORE / JUDGEMENT…）、
   判定图标、BPM/OD/HP 图标、分隔线
2. **立绘** —— `signboard_s` / `signboard_b`

PIL 只画插件提供的东西，所以这两类必须先导出来：

```bash
# 改完模板要重跑这两个
node … # 不适用，是 PS 脚本
# 在 Photoshop 里执行：
#   template/build/dump_ink.jsx      -> scratch/ink_bounds.txt，再并进 layer_mapping.json
#   template/build/export_static.jsx -> assets/static_overlay.png
#                                       assets/signboards/signboard_{s,b}.png
```

**导出 `static_overlay.png` 时只能「隐藏动态层」，不能顺手把别的层设成 visible。**
第一版就是写了 `l.visible = true`，把模板故意藏起来的设计提示和隐藏层全放了出来，
PIL 出的图上多了一块白色残影和一行 `watermark slot 180x60`。

### 两套引擎的实测差异

同一张卡、同一批素材、同一份数据，`python compare_engines.py` 出的对比：

- **平均像素差 6.98/255**（对比度放大 4 倍看差异图，见 `tests/out/cmp_diff.png`）
- **版式是对的**：对 9 个文字区域做 ±8px 的平移搜索，绝大多数最佳偏移就是 0，
  少数是 ±1px 的亚像素取整 —— 不是错位
- 剩下的差异来自三处：
  1. **文字抗锯齿**（FreeType vs Photoshop 的文字引擎），大字号上最明显
  2. **毛玻璃底板的模糊是近似的**（缩到 1/4 用 1/4 半径模糊再放大，为速度），
     差异是一大片平滑的灰，不是硬边
  3. **`accuracy` 那一格的颜色**：模板里存的是 `#6BC24A`（早期做评级配色时
     改上去的），而 `layer_mapping.json` 里记的是 `#EAEEF6`。
     PS 路径只写 contents、不写 color，所以漏出了模板的旧颜色；
     PIL 按 spec 画。**实际运行时插件会用 `_recolor_accent()` 按评级设色，两条路都会覆盖**，
     所以只在「不传 accent」的对照场景下才看得出来。

## 理论最大 PP

`pp_max` 不再是 `--`，按 osu!mania 的 pp 公式算「全 320 判定 + 满连」。

**公式来源**（取用于 2026-10）：
`osu.Game.Rulesets.Mania/Difficulty/ManiaPerformanceCalculator.cs`

```
totalHits      = perfect + great + good + ok + meh + miss
customAccuracy = (perfect*320 + great*300 + good*200 + ok*100 + meh*50) / (totalHits*320)
difficultyValue= 8.0 * max(SR - 0.15, 0.05)^2.2
                 * max(0, 5*customAccuracy - 4)
                 * (1 + 0.1 * min(1, totalHits/1500))
total          = difficultyValue * multiplier     # NF ×0.75, EZ ×0.5
```

**标定**（成绩 6645548845）：公式 **147.9015** vs API **147.902**，差 **-0.0005**。
这个对照在 `self_test.py` 第 6 节里是常驻断言。

全 320 时 `customAccuracy` 恒等于 1，公式退化成只跟 星级 / totalHits / NF·EZ 有关
（已用 SR 2~9、notes 500~4000 的网格验证退化与完整公式逐位一致）。

> ⚠️ **这个公式会随 osu! 版本变化**，改版后数字会失准，需要人工维护。
> 配置项 `pp_max_mode` 一键退回 `--`（`dash`）。

**一个必须知道的边界**：这个公式用的是成绩自带的星级（`difficulty_rating`），
而**开了 DT/HT 之后 osu! 会重算星级**，公式却不重算。于是会出现
`算出来的 pp_max < 实际的 pp` 这种不可能的结果（实测某条 DT 成绩：算出 283pp，
实际 931pp）。这种时候卡片显示 `--` 而不是那个荒谬的小数字。

## 指令

| 指令 | 作用 |
|---|---|
| `p` / `p -sb` | 最近**通过**的成绩 |
| `r` / `r -sb` | 最近**游玩**的成绩（含失败） |
| `s <成绩ID 或 链接>` | 指定成绩 |
| `bind <osu!用户名>` / `bind <名字> -sb` | 绑定 QQ（分服） |
| `authorize` | 重新要一个官服授权链接（见「官服授权」） |
| `mode <模式>` | 切换模式，`osu` / `taiko` / `fruits` / `mania`（`-sb` 只改私服那条） |
| `help` | 指令列表 |

外加：消息里出现成绩链接会自动出图（配置项 `auto_link`）。
**`-sb` 只对上面这几条指令有效，自动识别链接永远是官服**（私服成绩没有公开链接）。

`bind` / `authorize` / `mode` / `help` 同时注册了 `!` 前缀的别名（`!bind` 等）——
AstrBot 的唤醒前缀默认是 `/`，`!` 不是前缀，所以 `!bind` 会作为一个普通指令名匹配。

### 绑定记录格式

绑定记录升过两次代，读取时都会自动升级，**已有的绑定不会丢**：

| 代 | 形状 | 为什么改 |
|---|---|---|
| 1 | `"<QQ>" -> "用户名"` | 最初 |
| 2 | `"<QQ>" -> {username, ruleset}` | `mode` 要按 QQ 存模式 |
| 3 | `"<server>:<QQ>" -> {username, ruleset, server}` | SB 私服：一个人在两个服是两个人 |
| 3+ | 第 3 代再加一个可选的 `oauth` 字段 | 官服授权令牌（见下） |

第 3 代的键里带服名，所以 `bind A` 和 `bind A -sb` 是两条互不影响的记录。
玩家资料缓存的键同样带服名（`<server>:<ruleset>:<用户名>`），否则官服查出来的
总 PP 会被私服的查询命中。

**`oauth` 字段**只挂在官服的记录上：

```jsonc
"osu:12345": {
  "username": "F6A8AF", "ruleset": "mania", "server": "osu",
  "oauth": {
    "access_token":    "…",   // 24 小时过期，过期自动用 refresh 换新的
    "refresh_token":   "…",   // 30 天有效，每次刷新都会换一个，必须写回
    "expires_at":      1778000000.0,
    "user_id":         32749965,
    "scope":           "public",
    "obtained_at":     1777913600.0
  }
}
```

私服的记录里永远不会有这个字段。`bind` 名字本身**不等于**授权 —— 绑定只需要用户名
（查 `/users/{id}` 用应用令牌就够），只有 `p` / `r` 需要用户令牌。

## 渲染前的图层清理

模板里 `mod_2_mult`（DT 的 `x1.5`）出厂就是可见的。插件只「设置需要的」、
从不「隐藏多余的」，所以没开 mod 的成绩卡上也残留一个 `x1.5`。

现在两条路都处理了：
- **PIL**：只画 `to_layers()` 给的层，天然不会画多余的
- **Photoshop**：JSX 里加了 `hideStale()`，按名字兜底隐藏
  `mod_N_mult` 和 `rank_{xh,ss,sh,s,a,b,c,d}` —— 但**不碰 `_deco_` 开头的设计标签**

`to_layers()` 只在出现**变速 mod**（DT/HT/NC/DC）时才产生 `mod_N_mult`。
其他 mod 不显示倍率，因为它们的值在各规则集/osu! 版本间不一致，
**印个错数字比不印更糟**。
