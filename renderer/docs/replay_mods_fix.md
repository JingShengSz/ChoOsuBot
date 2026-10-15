# 回放倍速和 Hold Off 修正（2026-10-15）

## 问题与原因

Jaafan 的 Aim Burst 回放开启 DT + HO。此前解析只读取传统 OSR 头部 Mod 位图，丢失 lazer 在文件末尾保存的完整 Mod JSON，播放速度也未同步到控件。

原谱有 6,286 个物件，其中 502 个长条。HO 把这些长条转换为单键，实际只有 6,286 次判定。此前页面仍绘制长条并计算尾判，得到 6,788 次，导致统计总数与回放不同，无法校准最终 ACC。

## 实现

- 解析 lazer 的 LZMA 扩展成绩 JSON，保留完整 Mod/settings、完整判定统计、maximum_statistics。完整统计覆盖传统 UInt16 计数字段。
- DT/NC 默认 1.5×，HT/DC 默认 0.75×；`speed_change` 优先。老回放保留传统位图回退。
- Mod 倍速设置为初始播放速度，支持额外生成自定义倍速选项；谱面与按键时间保持原始谱面时间，避免两次变速。
- HO 通过已有的长条转单键变换应用于全套渲染与判定。匹配窗口按回放倍速补偿，CPS 按播放速度计算，UR 换算为实际毫秒。
- ACC 明确标注 Lazer / Stable，最终值由回放完整判定统计校准。时间分布仍由回放输入匹配推导，不能保证每一刻完全复刻游戏内部判定。
- 网页保留成绩图转场；WebCodecs 与 MediaRecorder 导出只包含开场、谱面和最后音符后 2 秒音乐。导出不再等待或依赖成绩图生成。
- 服务器封装从页面时间轴获取倍速和音乐结束时间，使 osu 与 Malody 共用速度来源。

## 已核对的实际回放

谱面 3261941，Jaafan，DT + HO：MAX 6,163、300 判定 123，其余 0；总数 6,286。Lazer ACC 99.9679224714823%，Stable 换算 100%。谱面时间 634 ms 对应第一按键 631 ms，时间戳没有缩放；浏览器实际播放约 1.5×。

完整导出：1280×720、60 FPS、10,098 帧，168.32 秒，包含音轨。故意让成绩卡接口返回 500 后依然完成。FFmpeg 解码末帧显示游玩画面和正确的 ACC，没有成绩卡。结果保存在 `scratch/osu-dt-check/jaafan-dt-ho.mp4`。

## 验证入口

- `renderer/tools/test_osr_lazer_mods.py`：lazer 扩展 Mod、默认和自定义速度、完整统计、传统格式回退。
- `renderer/tools/test_osu_dt_browser.cjs <回放.osr> --export`：实际 DT + HO 回放的计数、ACC、音频速度、播放时钟和完整导出；故意让成绩图接口失败，仍能导出。
- `renderer/tools/test_scene_flow_browser.cjs`：网页成绩图转场、导出不含成绩图、音频对齐与 2 秒音乐尾段。用 FFmpeg 解码实际末帧检查。
- `renderer/tools/test_scene_mux.py`：服务器封装保留开场和音乐尾段。

## 官方实现参考

- [LegacyScoreDecoder](https://github.com/ppy/osu/blob/master/osu.Game/Scoring/Legacy/LegacyScoreDecoder.cs)：lazer 完整统计与 Mod 数据来自扩展 JSON。
- [ManiaModHoldOff](https://github.com/ppy/osu/blob/master/osu.Game.Rulesets.Mania/Mods/ManiaModHoldOff.cs)：长条转换为开始时间处的单键。
- [ManiaHitWindows](https://github.com/ppy/osu/blob/master/osu.Game.Rulesets.Mania/Scoring/ManiaHitWindows.cs)：判定窗口随谱面时钟速度补偿。
