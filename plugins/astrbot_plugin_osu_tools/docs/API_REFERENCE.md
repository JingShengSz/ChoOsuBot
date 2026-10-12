# osu! API v2 接口全表

核对日期：2026-10-10。范围：官方 OpenAPI 快照内的全部 120 个 method/path 组合。

权限取自官方 HTML 的标签；OpenAPI 中很多 `security: []` 丢失权限信息，不能据此当作匿名接口。

源码版本：[04643dee6cac](https://github.com/ppy/osu-web/tree/04643dee6cacfaadc6c80976256481322e21e945)。

插件仅调用标记为“开放”的查询；其余接口保留文档索引供开发参考。运行时 `osu_api_help(operation_id=...)` 返回参数。

## Account

| operation_id | 方法 / 路径 | 权限 | 插件 |
|---|---|---|---|
| [getApiV2MeBeatmapsetFavourites](https://osu.ppy.sh/docs/index.html#account-GETapi-v2-me-beatmapset-favourites) | `GET /me/beatmapset-favourites` | requires user, OAuth, identify | 需要用户授权或额外 scope |

## Beatmap Packs

| operation_id | 方法 / 路径 | 权限 | 插件 |
|---|---|---|---|
| [getBeatmapPacks](https://osu.ppy.sh/docs/index.html#beatmap-packs-GETapi-v2-beatmaps-packs) | `GET /beatmaps/packs` | OAuth, public | 开放 |
| [getBeatmapPack](https://osu.ppy.sh/docs/index.html#beatmap-packs-GETapi-v2-beatmaps-packs--pack-) | `GET /beatmaps/packs/{pack}` | OAuth, public | 开放 |

## Beatmaps

| operation_id | 方法 / 路径 | 权限 | 插件 |
|---|---|---|---|
| [lookupBeatmap](https://osu.ppy.sh/docs/index.html#beatmaps-GETapi-v2-beatmaps-lookup) | `GET /beatmaps/lookup` | OAuth, public | 开放 |
| [getAUserBeatmapScore](https://osu.ppy.sh/docs/index.html#beatmaps-GETapi-v2-beatmaps--beatmap--scores-users--user-) | `GET /beatmaps/{beatmap}/scores/users/{user}` | OAuth, public | 开放 |
| [getAUserBeatmapScores](https://osu.ppy.sh/docs/index.html#beatmaps-GETapi-v2-beatmaps--beatmap--scores-users--user--all) | `GET /beatmaps/{beatmap}/scores/users/{user}/all` | OAuth, public | 开放 |
| [getBeatmapScores](https://osu.ppy.sh/docs/index.html#beatmaps-GETapi-v2-beatmaps--beatmap--scores) | `GET /beatmaps/{beatmap}/scores` | OAuth, public | 开放 |
| [getBeatmapScoresnonLegacy](https://osu.ppy.sh/docs/index.html#beatmaps-GETapi-v2-beatmaps--beatmap--solo-scores) | `GET /beatmaps/{beatmap}/solo-scores` | OAuth, public | 已弃用，请使用替代接口 |
| [getBeatmaps](https://osu.ppy.sh/docs/index.html#beatmaps-GETapi-v2-beatmaps) | `GET /beatmaps` | OAuth, public | 开放 |
| [getBeatmap](https://osu.ppy.sh/docs/index.html#beatmaps-GETapi-v2-beatmaps--beatmap-) | `GET /beatmaps/{beatmap}` | OAuth, public | 开放 |
| [getBeatmapAttributes](https://osu.ppy.sh/docs/index.html#beatmaps-POSTapi-v2-beatmaps--beatmap--attributes) | `POST /beatmaps/{beatmap}/attributes` | OAuth, public | 开放 |

## Beatmapset Discussions

| operation_id | 方法 / 路径 | 权限 | 插件 |
|---|---|---|---|
| [getBeatmapsetDiscussionPosts](https://osu.ppy.sh/docs/index.html#beatmapset-discussions-GETapi-v2-beatmapsets-discussions-posts) | `GET /beatmapsets/discussions/posts` | OAuth, public | 开放 |
| [getBeatmapsetDiscussionVotes](https://osu.ppy.sh/docs/index.html#beatmapset-discussions-GETapi-v2-beatmapsets-discussions-votes) | `GET /beatmapsets/discussions/votes` | OAuth, public | 开放 |
| [getBeatmapsetDiscussions](https://osu.ppy.sh/docs/index.html#beatmapset-discussions-GETapi-v2-beatmapsets-discussions) | `GET /beatmapsets/discussions` | OAuth, public | 开放 |

## Beatmapsets

| operation_id | 方法 / 路径 | 权限 | 插件 |
|---|---|---|---|
| [searchBeatmapset](https://osu.ppy.sh/docs/index.html#beatmapsets-GETapi-v2-beatmapsets-search) | `GET /beatmapsets/search` | OAuth, public | 开放 |
| [getApiV2BeatmapsetsLookup](https://osu.ppy.sh/docs/index.html#beatmapsets-GETapi-v2-beatmapsets-lookup) | `GET /beatmapsets/lookup` | OAuth, public | 开放 |
| [getApiV2BeatmapsetsBeatmapset](https://osu.ppy.sh/docs/index.html#beatmapsets-GETapi-v2-beatmapsets--beatmapset-) | `GET /beatmapsets/{beatmapset}` | OAuth, public | 开放 |
| [getApiV2BeatmapsetsBeatmapsetDownload](https://osu.ppy.sh/docs/index.html#beatmapsets-GETapi-v2-beatmapsets--beatmapset--download) | `GET /beatmapsets/{beatmapset}/download` | OAuth, lazer | lazer 客户端专用 |

## Changelog

| operation_id | 方法 / 路径 | 权限 | 插件 |
|---|---|---|---|
| [getChangelogBuild](https://osu.ppy.sh/docs/index.html#changelog-GETapi-v2-changelog--stream---build-) | `GET /changelog/{stream}/{build}` | 公开，无 OAuth 标签 | 开放 |
| [getChangelogListing](https://osu.ppy.sh/docs/index.html#changelog-GETapi-v2-changelog) | `GET /changelog` | 公开，无 OAuth 标签 | 开放 |
| [lookupChangelogBuild](https://osu.ppy.sh/docs/index.html#changelog-GETapi-v2-changelog--changelog-) | `GET /changelog/{changelog}` | 公开，无 OAuth 标签 | 开放 |

## Chat

| operation_id | 方法 / 路径 | 权限 | 插件 |
|---|---|---|---|
| [chatKeepalive](https://osu.ppy.sh/docs/index.html#chat-POSTapi-v2-chat-ack) | `POST /chat/ack` | requires user, OAuth, chat.read | 需要用户授权或额外 scope |
| [createNewPM](https://osu.ppy.sh/docs/index.html#chat-POSTapi-v2-chat-new) | `POST /chat/new` | requires user, OAuth, chat.write | 需要用户授权或额外 scope |
| [getUpdates](https://osu.ppy.sh/docs/index.html#chat-GETapi-v2-chat-updates) | `GET /chat/updates` | requires user, OAuth, lazer | lazer 客户端专用 |
| [getChannelMessages](https://osu.ppy.sh/docs/index.html#chat-GETapi-v2-chat-channels--channel--messages) | `GET /chat/channels/{channel}/messages` | requires user, OAuth, chat.read | 需要用户授权或额外 scope |
| [sendMessageToChannel](https://osu.ppy.sh/docs/index.html#chat-POSTapi-v2-chat-channels--channel--messages) | `POST /chat/channels/{channel}/messages` | requires user, OAuth, chat.write | 需要用户授权或额外 scope |
| [joinChannel](https://osu.ppy.sh/docs/index.html#chat-PUTapi-v2-chat-channels--channel--users--user-) | `PUT /chat/channels/{channel}/users/{user}` | requires user, OAuth, chat.write_manage | 需要用户授权或额外 scope |
| [leaveChannel](https://osu.ppy.sh/docs/index.html#chat-DELETEapi-v2-chat-channels--channel--users--user-) | `DELETE /chat/channels/{channel}/users/{user}` | requires user, OAuth, chat.write_manage | 需要用户授权或额外 scope |
| [markChannelAsRead](https://osu.ppy.sh/docs/index.html#chat-PUTapi-v2-chat-channels--channel--mark-as-read--message-) | `PUT /chat/channels/{channel}/mark-as-read/{message}` | requires user, OAuth, chat.read | 需要用户授权或额外 scope |
| [getChannelList](https://osu.ppy.sh/docs/index.html#chat-GETapi-v2-chat-channels) | `GET /chat/channels` | requires user, OAuth, chat.read | 需要用户授权或额外 scope |
| [createChannel](https://osu.ppy.sh/docs/index.html#chat-POSTapi-v2-chat-channels) | `POST /chat/channels` | requires user, OAuth, chat.write_manage | 需要用户授权或额外 scope |
| [getChannel](https://osu.ppy.sh/docs/index.html#chat-GETapi-v2-chat-channels--channel-) | `GET /chat/channels/{channel}` | requires user, OAuth, chat.read | 需要用户授权或额外 scope |

## Comments

| operation_id | 方法 / 路径 | 权限 | 插件 |
|---|---|---|---|
| [getComments](https://osu.ppy.sh/docs/index.html#comments-GETapi-v2-comments) | `GET /comments` | 公开，无 OAuth 标签 | 开放 |
| [postANewComment](https://osu.ppy.sh/docs/index.html#comments-POSTapi-v2-comments) | `POST /comments` | requires user, OAuth, lazer | lazer 客户端专用 |
| [getAComment](https://osu.ppy.sh/docs/index.html#comments-GETapi-v2-comments--comment-) | `GET /comments/{comment}` | 公开，无 OAuth 标签 | 开放 |
| [editComment](https://osu.ppy.sh/docs/index.html#comments-PUTapi-v2-comments--comment-) | `PUT /comments/{comment}` | requires user, OAuth, lazer | lazer 客户端专用 |
| [deleteComment](https://osu.ppy.sh/docs/index.html#comments-DELETEapi-v2-comments--comment-) | `DELETE /comments/{comment}` | requires user, OAuth, lazer | lazer 客户端专用 |
| [addCommentVote](https://osu.ppy.sh/docs/index.html#comments-POSTapi-v2-comments--comment--vote) | `POST /comments/{comment}/vote` | requires user, OAuth, lazer | lazer 客户端专用 |
| [removeCommentVote](https://osu.ppy.sh/docs/index.html#comments-DELETEapi-v2-comments--comment--vote) | `DELETE /comments/{comment}/vote` | requires user, OAuth, lazer | lazer 客户端专用 |

## Events

| operation_id | 方法 / 路径 | 权限 | 插件 |
|---|---|---|---|
| [getEvents](https://osu.ppy.sh/docs/index.html#events-GETapi-v2-events) | `GET /events` | OAuth, public | 开放 |

## Forum

| operation_id | 方法 / 路径 | 权限 | 插件 |
|---|---|---|---|
| [lockTopic](https://osu.ppy.sh/docs/index.html#forum-POSTapi-v2-forums-topics--topic--lock) | `POST /forums/topics/{topic}/lock` | requires user, OAuth, forum.write_manage | 需要用户授权或额外 scope |
| [postApiV2ForumsTopicsTopicMove](https://osu.ppy.sh/docs/index.html#forum-POSTapi-v2-forums-topics--topic--move) | `POST /forums/topics/{topic}/move` | OAuth, lazer | lazer 客户端专用 |
| [pinTopic](https://osu.ppy.sh/docs/index.html#forum-POSTapi-v2-forums-topics--topic--pin) | `POST /forums/topics/{topic}/pin` | requires user, OAuth, forum.write_manage | 需要用户授权或额外 scope |
| [replyTopic](https://osu.ppy.sh/docs/index.html#forum-POSTapi-v2-forums-topics--topic--reply) | `POST /forums/topics/{topic}/reply` | requires user, OAuth, forum.write | 需要用户授权或额外 scope |
| [getTopicListing](https://osu.ppy.sh/docs/index.html#forum-GETapi-v2-forums-topics) | `GET /forums/topics` | OAuth, public | 开放 |
| [createTopic](https://osu.ppy.sh/docs/index.html#forum-POSTapi-v2-forums-topics) | `POST /forums/topics` | requires user, OAuth, forum.write | 需要用户授权或额外 scope |
| [getTopicAndPosts](https://osu.ppy.sh/docs/index.html#forum-GETapi-v2-forums-topics--topic-) | `GET /forums/topics/{topic}` | OAuth, public | 开放 |
| [editTopic](https://osu.ppy.sh/docs/index.html#forum-PUTapi-v2-forums-topics--topic-) | `PUT /forums/topics/{topic}` | OAuth, forum.write | 需要用户授权或额外 scope |
| [editPost](https://osu.ppy.sh/docs/index.html#forum-PUTapi-v2-forums-posts--post-) | `PUT /forums/posts/{post}` | OAuth, forum.write | 需要用户授权或额外 scope |
| [getForumListing](https://osu.ppy.sh/docs/index.html#forum-GETapi-v2-forums) | `GET /forums` | OAuth, public | 开放 |
| [getForumAndTopics](https://osu.ppy.sh/docs/index.html#forum-GETapi-v2-forums--forum-) | `GET /forums/{forum}` | OAuth, public | 开放 |

## Home

| operation_id | 方法 / 路径 | 权限 | 插件 |
|---|---|---|---|
| [search](https://osu.ppy.sh/docs/index.html#home-GETapi-v2-search) | `GET /search` | OAuth, public | 开放 |

## Matches

| operation_id | 方法 / 路径 | 权限 | 插件 |
|---|---|---|---|
| [getMatchesListing](https://osu.ppy.sh/docs/index.html#matches-GETapi-v2-matches) | `GET /matches` | OAuth, public | 开放 |
| [getMatch](https://osu.ppy.sh/docs/index.html#matches-GETapi-v2-matches--match-) | `GET /matches/{match}` | OAuth, public | 开放 |

## Multiplayer

| operation_id | 方法 / 路径 | 权限 | 插件 |
|---|---|---|---|
| [getUserHighScore](https://osu.ppy.sh/docs/index.html#multiplayer-GETapi-v2-rooms--room--playlist--playlist--scores-users--user-) | `GET /rooms/{room}/playlist/{playlist}/scores/users/{user}` | requires user, OAuth, lazer | lazer 客户端专用 |
| [getPlaylistScores](https://osu.ppy.sh/docs/index.html#multiplayer-GETapi-v2-rooms--room--playlist--playlist--scores) | `GET /rooms/{room}/playlist/{playlist}/scores` | OAuth, public | 开放 |
| [getAScore](https://osu.ppy.sh/docs/index.html#multiplayer-GETapi-v2-rooms--room--playlist--playlist--scores--score-) | `GET /rooms/{room}/playlist/{playlist}/scores/{score}` | requires user, OAuth, lazer | lazer 客户端专用 |
| [getMultiplayerRooms](https://osu.ppy.sh/docs/index.html#multiplayer-GETapi-v2-rooms) | `GET /rooms` | OAuth, public | 开放 |

## Undocumented

| operation_id | 方法 / 路径 | 权限 | 插件 |
|---|---|---|---|
| [postApiV2RoomsRoomPlaylistPlaylistScores](https://osu.ppy.sh/docs/index.html#undocumented-POSTapi-v2-rooms--room--playlist--playlist--scores) | `POST /rooms/{room}/playlist/{playlist}/scores` | requires user, OAuth, lazer | lazer 客户端专用 |
| [putApiV2RoomsRoomPlaylistPlaylistScoresScore](https://osu.ppy.sh/docs/index.html#undocumented-PUTapi-v2-rooms--room--playlist--playlist--scores--score-) | `PUT /rooms/{room}/playlist/{playlist}/scores/{score}` | requires user, OAuth, lazer | lazer 客户端专用 |
| [postApiV2Rooms](https://osu.ppy.sh/docs/index.html#undocumented-POSTapi-v2-rooms) | `POST /rooms` | requires user, OAuth, lazer | lazer 客户端专用 |
| [postApiV2SessionVerify](https://osu.ppy.sh/docs/index.html#undocumented-POSTapi-v2-session-verify) | `POST /session/verify` | requires user, OAuth | 需要用户授权或额外 scope |
| [postApiV2SessionVerifyMailFallback](https://osu.ppy.sh/docs/index.html#undocumented-POSTapi-v2-session-verify-mail-fallback) | `POST /session/verify/mail-fallback` | requires user, OAuth | 需要用户授权或额外 scope |
| [postApiV2SessionVerifyReissue](https://osu.ppy.sh/docs/index.html#undocumented-POSTapi-v2-session-verify-reissue) | `POST /session/verify/reissue` | requires user, OAuth | 需要用户授权或额外 scope |
| [postApiV2BeatmapsBeatmapSoloScores](https://osu.ppy.sh/docs/index.html#undocumented-POSTapi-v2-beatmaps--beatmap--solo-scores) | `POST /beatmaps/{beatmap}/solo/scores` | requires user, OAuth, lazer | lazer 客户端专用 |
| [putApiV2BeatmapsBeatmapSoloScoresToken](https://osu.ppy.sh/docs/index.html#undocumented-PUTapi-v2-beatmaps--beatmap--solo-scores--token-) | `PUT /beatmaps/{beatmap}/solo/scores/{token}` | requires user, OAuth, lazer | lazer 客户端专用 |
| [putApiV2BeatmapsBeatmapTagsTag](https://osu.ppy.sh/docs/index.html#undocumented-PUTapi-v2-beatmaps--beatmap--tags--tag-) | `PUT /beatmaps/{beatmap}/tags/{tag}` | requires user, OAuth, lazer | lazer 客户端专用 |
| [deleteApiV2BeatmapsBeatmapTagsTag](https://osu.ppy.sh/docs/index.html#undocumented-DELETEapi-v2-beatmaps--beatmap--tags--tag-) | `DELETE /beatmaps/{beatmap}/tags/{tag}` | requires user, OAuth, lazer | lazer 客户端专用 |
| [getApiV2BeatmapsetsEvents](https://osu.ppy.sh/docs/index.html#undocumented-GETapi-v2-beatmapsets-events) | `GET /beatmapsets/events` | OAuth, public | 开放 |
| [postApiV2BeatmapsetsBeatmapsetFavourites](https://osu.ppy.sh/docs/index.html#undocumented-POSTapi-v2-beatmapsets--beatmapset--favourites) | `POST /beatmapsets/{beatmapset}/favourites` | requires user, OAuth, lazer | lazer 客户端专用 |
| [getApiV2BeatmapsetsBeatmapsetRatings](https://osu.ppy.sh/docs/index.html#undocumented-GETapi-v2-beatmapsets--beatmapset--ratings) | `GET /beatmapsets/{beatmapset}/ratings` | requires user, OAuth, lazer | lazer 客户端专用 |
| [postApiV2BeatmapsetsBeatmapsetRatings](https://osu.ppy.sh/docs/index.html#undocumented-POSTapi-v2-beatmapsets--beatmapset--ratings) | `POST /beatmapsets/{beatmapset}/ratings` | requires user, OAuth, lazer | lazer 客户端专用 |
| [getApiV2Blocks](https://osu.ppy.sh/docs/index.html#undocumented-GETapi-v2-blocks) | `GET /blocks` | requires user, OAuth, lazer | lazer 客户端专用 |
| [postApiV2Blocks](https://osu.ppy.sh/docs/index.html#undocumented-POSTapi-v2-blocks) | `POST /blocks` | requires user, OAuth, lazer | lazer 客户端专用 |
| [deleteApiV2BlocksBlock](https://osu.ppy.sh/docs/index.html#undocumented-DELETEapi-v2-blocks--block-) | `DELETE /blocks/{block}` | requires user, OAuth, lazer | lazer 客户端专用 |
| [getApiV2ChatPresence](https://osu.ppy.sh/docs/index.html#undocumented-GETapi-v2-chat-presence) | `GET /chat/presence` | requires user, OAuth, lazer | lazer 客户端专用 |
| [postApiV2Reports](https://osu.ppy.sh/docs/index.html#undocumented-POSTapi-v2-reports) | `POST /reports` | requires user, OAuth, lazer | lazer 客户端专用 |
| [putApiV2RoomsRoomUsersUser](https://osu.ppy.sh/docs/index.html#undocumented-PUTapi-v2-rooms--room--users--user-) | `PUT /rooms/{room}/users/{user}` | requires user, OAuth, lazer | lazer 客户端专用 |
| [deleteApiV2RoomsRoomUsersUser](https://osu.ppy.sh/docs/index.html#undocumented-DELETEapi-v2-rooms--room--users--user-) | `DELETE /rooms/{room}/users/{user}` | requires user, OAuth, lazer | lazer 客户端专用 |
| [getApiV2RoomsRoomLeaderboard](https://osu.ppy.sh/docs/index.html#undocumented-GETapi-v2-rooms--room--leaderboard) | `GET /rooms/{room}/leaderboard` | OAuth, public | 开放 |
| [getApiV2RoomsRoomEvents](https://osu.ppy.sh/docs/index.html#undocumented-GETapi-v2-rooms--room--events) | `GET /rooms/{room}/events` | OAuth, public | 开放 |
| [getApiV2RoomsRoom](https://osu.ppy.sh/docs/index.html#undocumented-GETapi-v2-rooms--room-) | `GET /rooms/{room}` | OAuth, public | 开放 |
| [deleteApiV2RoomsRoom](https://osu.ppy.sh/docs/index.html#undocumented-DELETEapi-v2-rooms--room-) | `DELETE /rooms/{room}` | requires user, OAuth, lazer | lazer 客户端专用 |
| [getApiV2SeasonalBackgrounds](https://osu.ppy.sh/docs/index.html#undocumented-GETapi-v2-seasonal-backgrounds) | `GET /seasonal-backgrounds` | 公开，无 OAuth 标签 | 开放 |
| [getApiV2ScoresScoreDownload](https://osu.ppy.sh/docs/index.html#undocumented-GETapi-v2-scores--score--download) | `GET /scores/{score}/download` | OAuth, public | 二进制下载，当前 JSON 工具不开放 |
| [getApiV2ScoresRulesetScoreDownload](https://osu.ppy.sh/docs/index.html#undocumented-GETapi-v2-scores--ruleset---score--download) | `GET /scores/{ruleset}/{score}/download` | OAuth, public | 二进制下载，当前 JSON 工具不开放 |
| [getApiV2ScoresRulesetScore](https://osu.ppy.sh/docs/index.html#undocumented-GETapi-v2-scores--ruleset---score-) | `GET /scores/{ruleset}/{score}` | OAuth, public | 开放 |
| [getApiV2ScoresScore](https://osu.ppy.sh/docs/index.html#undocumented-GETapi-v2-scores--score-) | `GET /scores/{score}` | OAuth, public | 开放 |
| [getApiV2UsersLookup](https://osu.ppy.sh/docs/index.html#undocumented-GETapi-v2-users-lookup) | `GET /users/lookup` | OAuth, public | 开放 |
| [getApiV2Friends](https://osu.ppy.sh/docs/index.html#undocumented-GETapi-v2-friends) | `GET /friends` | requires user, OAuth, friends.read | 需要用户授权或额外 scope |
| [postApiV2Friends](https://osu.ppy.sh/docs/index.html#undocumented-POSTapi-v2-friends) | `POST /friends` | requires user, OAuth, lazer | lazer 客户端专用 |
| [deleteApiV2FriendsFriend](https://osu.ppy.sh/docs/index.html#undocumented-DELETEapi-v2-friends--friend-) | `DELETE /friends/{friend}` | requires user, OAuth, lazer | lazer 客户端专用 |
| [getApiV2MeDownloadQuotaCheck](https://osu.ppy.sh/docs/index.html#undocumented-GETapi-v2-me-download-quota-check) | `GET /me/download-quota-check` | requires user, OAuth, lazer | lazer 客户端专用 |
| [putApiV2MeOptions](https://osu.ppy.sh/docs/index.html#undocumented-PUTapi-v2-me-options) | `PUT /me/options` | requires user, OAuth, lazer | lazer 客户端专用 |
| [getApiV2SuggestionsWiki](https://osu.ppy.sh/docs/index.html#undocumented-GETapi-v2-suggestions-wiki) | `GET /suggestions/wiki` | 公开，无 OAuth 标签 | 开放 |
| [getApiV2Tags](https://osu.ppy.sh/docs/index.html#undocumented-GETapi-v2-tags) | `GET /tags` | OAuth, public | 开放 |
| [postApiV2Screenshots](https://osu.ppy.sh/docs/index.html#undocumented-POSTapi-v2-screenshots) | `POST /screenshots` | requires user, OAuth, lazer | lazer 客户端专用 |

## News

| operation_id | 方法 / 路径 | 权限 | 插件 |
|---|---|---|---|
| [getNewsListing](https://osu.ppy.sh/docs/index.html#news-GETapi-v2-news) | `GET /news` | 公开，无 OAuth 标签 | 开放 |
| [getNewsPost](https://osu.ppy.sh/docs/index.html#news-GETapi-v2-news--news-) | `GET /news/{news}` | 公开，无 OAuth 标签 | 开放 |

## Notification

| operation_id | 方法 / 路径 | 权限 | 插件 |
|---|---|---|---|
| [getNotifications](https://osu.ppy.sh/docs/index.html#notification-GETapi-v2-notifications) | `GET /notifications` | requires user, OAuth, lazer | lazer 客户端专用 |
| [markNotificationsAsRead](https://osu.ppy.sh/docs/index.html#notification-POSTapi-v2-notifications-mark-read) | `POST /notifications/mark-read` | requires user, OAuth, lazer | lazer 客户端专用 |

## OAuth Tokens

| operation_id | 方法 / 路径 | 权限 | 插件 |
|---|---|---|---|
| [revokeCurrentToken](https://osu.ppy.sh/docs/index.html#oauth-tokens-DELETEapi-v2-oauth-tokens-current) | `DELETE /oauth/tokens/current` | OAuth | 修改账号状态的操作 |

## Ranking

| operation_id | 方法 / 路径 | 权限 | 插件 |
|---|---|---|---|
| [getKudosuRanking](https://osu.ppy.sh/docs/index.html#ranking-GETapi-v2-rankings-kudosu) | `GET /rankings/kudosu` | OAuth, public | 开放 |
| [getRanking](https://osu.ppy.sh/docs/index.html#ranking-GETapi-v2-rankings--mode---type-) | `GET /rankings/{mode}/{type}` | OAuth, public | 开放 |
| [getSpotlights](https://osu.ppy.sh/docs/index.html#ranking-GETapi-v2-spotlights) | `GET /spotlights` | OAuth, public | 开放 |

## Scores

| operation_id | 方法 / 路径 | 权限 | 插件 |
|---|---|---|---|
| [getGlobalScores](https://osu.ppy.sh/docs/index.html#scores-GETapi-v2-scores) | `GET /scores` | OAuth, public | 开放 |
| [reorderPinnedScore](https://osu.ppy.sh/docs/index.html#scores-POSTapi-v2-score-pins--score--reorder) | `POST /score-pins/{score}/reorder` | requires user, OAuth, lazer | lazer 客户端专用 |
| [unpinScore](https://osu.ppy.sh/docs/index.html#scores-DELETEapi-v2-score-pins--score-) | `DELETE /score-pins/{score}` | requires user, OAuth, lazer | lazer 客户端专用 |
| [pinScore](https://osu.ppy.sh/docs/index.html#scores-PUTapi-v2-score-pins--score-) | `PUT /score-pins/{score}` | requires user, OAuth, lazer | lazer 客户端专用 |

## Teams

| operation_id | 方法 / 路径 | 权限 | 插件 |
|---|---|---|---|
| [getTeam](https://osu.ppy.sh/docs/index.html#teams-GETapi-v2-teams--team---ruleset--) | `GET /teams/{team}/{ruleset}` | OAuth, public | 开放 |

## Users

| operation_id | 方法 / 路径 | 权限 | 插件 |
|---|---|---|---|
| [getUserKudosu](https://osu.ppy.sh/docs/index.html#users-GETapi-v2-users--user--kudosu) | `GET /users/{user}/kudosu` | OAuth, public | 开放 |
| [getUserScores](https://osu.ppy.sh/docs/index.html#users-GETapi-v2-users--user--scores--type-) | `GET /users/{user}/scores/{type}` | OAuth, public | 开放 |
| [getUserBeatmaps](https://osu.ppy.sh/docs/index.html#users-GETapi-v2-users--user--beatmapsets--type-) | `GET /users/{user}/beatmapsets/{type}` | OAuth, public | 开放 |
| [getUserRecentActivity](https://osu.ppy.sh/docs/index.html#users-GETapi-v2-users--user--recent_activity) | `GET /users/{user}/recent_activity` | OAuth, public | 开放 |
| [searchBeatmapsPassed](https://osu.ppy.sh/docs/index.html#users-GETapi-v2-users--user--beatmaps-passed) | `GET /users/{user}/beatmaps-passed` | OAuth, public | 开放 |
| [getUser](https://osu.ppy.sh/docs/index.html#users-GETapi-v2-users--user---mode--) | `GET /users/{user}/{mode}` | OAuth, public | 开放 |
| [getUsers](https://osu.ppy.sh/docs/index.html#users-GETapi-v2-users) | `GET /users` | OAuth, public | 开放 |
| [getOwnData](https://osu.ppy.sh/docs/index.html#users-GETapi-v2-me--mode--) | `GET /me/{mode}` | requires user, OAuth, identify | 需要用户授权或额外 scope |
| [putApiV2MeAchievementsAchievementId](https://osu.ppy.sh/docs/index.html#users-PUTapi-v2-me-achievements--achievementId-) | `PUT /me/achievements/{achievementId}` | requires user, OAuth, lazer | lazer 客户端专用 |

## Wiki

| operation_id | 方法 / 路径 | 权限 | 插件 |
|---|---|---|---|
| [getWikiPage](https://osu.ppy.sh/docs/index.html#wiki-GETapi-v2-wiki--locale---path-) | `GET /wiki/{locale}/{path}` | 公开，无 OAuth 标签 | 开放 |

## 索引校正

- 官方两个 `getScores` 分别重命名为 `getGlobalScores` 和 `getPlaylistScores`，保留 `upstream_operation_id`。
- team/user/me 尾部 mode 或 ruleset 是可选路径参数；过滤掉规范里不存在于路径的冗余参数。
- `searchBeatmapset` 的参数取自官方搜索参数类，原 OpenAPI 大部分仍是 TODO。
- `POST /beatmaps/{beatmap}/attributes` 是难度查询，无账号修改，因此允许。
- 私有 `_lio` 路由、网站 session 页面和未收录的内部路由不作为稳定工具开放。
