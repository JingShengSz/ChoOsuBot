# 谱面详情：上游可输出参数清单

核对版本：`a44acf463679d57d46e4249afeb9adc2b816c3e0`。以下依据复制的源码，范围是公共分析返回、算法诊断和界面展示；没有把遥测后台的网站访问统计当作谱面参数。当前只保存源码和清单，尚未接入网站或 AstrBot。

## 阅读约定

以下 `js/` 路径均相对 `upstream/ManiaMapAnalyser by Leo_Black/`。字段随算法、键数和选项变化；关闭功能、无适用数据或失败时可能为 `null`、`NaN` 或缺省，不能把缺省当成 0。`NaN` 经普通 JSON 序列化会成为 `null`。段位估计与 rework PP 是上游算法结果，不是 osu! 官方评级或官方 PP。

## 1. 完整分析管线返回

来源：`js/pipeline/runAnalysisPipeline.js`，`runAnalysisPipeline()`。

| 字段 | 内容 |
| --- | --- |
| `rework` | 当前选中估算器的结果，见下一节 |
| `actualEstimatorAlgorithm` | 实际算法（包含自动路由或回退） |
| `sunnyStar` | 归一化时使用的 Sunny 星数，否则为 null |
| `sunnyWindow` | SunnyWindow / LN 分析结果，见第 3 节 |
| `sixKConst` | 6K 定数，仅开启 display6kLevel 且为 6K 时生成 |
| `vibro.star` | 归一化前的估算星数 |
| `vibro.eligible` | 是否满足进一步 Vibro 检测的星数条件；不是最终 Vibro 结论 |
| `ppMetrics` | 开启 withPpMetrics 时才有此字段，见第 5 节 |
| `parsedSummary.metadata` | 原文件 Metadata 字段字典 |
| `parsedSummary.lnRatio` | 长条比例 |
| `parsedSummary.columnCount` | 键数 |
| `patternReport` | 键型报告，见第 4 节 |
| `patternTopFiveClusters` | 报告中排名前五的键型簇 |
| `patternError` | 键型分析错误文字 |
| `ettResult` | Etterna MSD 分析，见第 6 节 |
| `ettError`、`ettErrorCode` | MSD 错误文字与机器可读错误码 |
| `interludeStar`、`interludeError` | Interlude 星数与错误文字 |
| `companellaEttResult`、`companellaEttError` | Companella 需要不同 MSD 版本时的第二份 MSD 结果与错误 |
| `errors` | 预留硬错误数组；当前成功返回中恒为 [] |

注意：局部变量 `sunnyWindowError` 会被记录，但当前 return 没有输出它。Companella ONNX 推理在前端追加，不是在此管线内直接返回最终 Companella 结果。

Worker 外层消息：`{ id, result }` 或 `{ id, error }`，`id` 是请求配对编号，不是谱面 ID。来源 `js/app/worker/compute.worker.js`。

## 2. 估算器结果及全部公开诊断字段

来源：`js/estimator/*Estimator.js`、`reworkEstimatorUtils.js`。

### 公共字段

- `star`：星数。管线对 Azusa、Roxy、Mixed 可能替换为 Sunny 星数，原算法数字应从 numericDifficulty / debug 查看。
- `lnRatio`、`columnCount`：长条比例、键数。
- `estDiff`：估计难度 / 段位标签。
- `numericDifficulty`、`numericDifficultyHint`：数值难度及提示；Sunny / SunnyWindow 数值难度为 null。
- `graph`：可选难度曲线，结构 `{ times: number[], values: number[] }`；times 为时间点，values 为难度值，与 NPS 密度图不是同一个指标。
- Sunny 额外可带 `ppMetrics`。
- Azusa / Roxy 额外带 `rawNumericDifficulty`、`debug`。

### Azusa `debug`

`primaryNumeric`、`blendNumeric`、`danielNumeric`、`danielNumericForBlend`、`danielHasNativeNumeric`、`sunnyNumeric`、`notes`、`calibratedNumeric`、`curveGapResidual`、`outputNumeric`、`postCurveGapResidual`、`finalNumeric`。

嵌套：

- `curveStats`：`anchorImbalance`、`chordRate`、`jackQ95`。
- `blend`：`lowGateSource`、`lowGate`、`highGate`、`lowBase`、`highBase`（当前为格式化字符串或 null）。
- 失败结果的 `debug`：`code`、`message`。

### Roxy `debug`

顶层：`notes`、`rows`、`rawAgg`、`logRaw`、`preNumeric`、`rawNumeric`、`structuralNumeric`、`metaNumeric`、`baseUnguardedNumeric`、`unguardedNumeric`、`finalNumeric`、`referenceGapCorrection`、`azusaHighGapLift`。

嵌套完整结构：

- `structuralBackstop`：`applied`、`floor`、`strength`。
- `highReferenceStructuralFloor`：null 或 `{ floor, activation, missingReferenceBoost, pressure, confidence, referenceFloor, structuralFloor, referenceTarget }`。
- `od`：`flag`、`base`、`neutral`、`effective`、`baseWindow`、`effectiveWindow`、`pressureRatio`、`correction`。
- `speedRateMode`：`mode`、`speedRate`、`analysisSpeedRate`、`canonicalFirstObjectMs`、`originalFirstObjectMs`、`canonicalized`。
- `meta`：`featureCount`、`references`；references 的键为 `Azusa`、`Sunny`、`Daniel`、`Roxy`（禁用参考可为 null）。
- `stats`：`inactiveMs`、`breakCount`、`activeDurationSec`、`breakDensity`、`avgNps`、`chordRate`、`threeRate`、`overlapRate`、`rotationRate`、`sameHandQ10`、`fastJackRate`、`anchorRate`、`anchorImbalance`、`leftLoad`、`rightLoad`、`handBias`、`peakToSustainGap`、`columnCounts`、`rows`、`taps`。
- `corrections`：`lowCj`、`highStream`、`highCjDamp`、`courseBreakDamp`、`courseSustainLift`、`denseJsLift`、`denseJsDamp`、`anchorLift`、`handBiasLift`、`rawSum`、`total`。
- `streams` 的键：`speed`、`handStream`、`jack`、`chordjack`、`tech`、`stamina`、`course`。每项都有 `q50`、`q75`、`q90`、`q97`、`tailMean`、`powerMean`、`aggregate`。
- 失败：`debug.code`、`debug.message`；超出算法适用范围时额外 `debug.structuralNumeric`、`debug.notes`、`debug.rows`，numericDifficulty 为 null。

以上是解释算法决策的诊断数据，不能直接当作标准化玩家能力数值。

### Mixed 与 Companella

Mixed 继承被选中算法全部字段，额外：`actualEstimatorAlgorithm`、`mixedCompanellaPlan`、后处理可能增加 `companellaCapsule`。

`mixedCompanellaPlan` 基础结构 `{ lnRatio, lnDifficulty }`；低难融合计划还带 `fuseRc`、`onDisagree`、`rcEstDiff`、`rcNumeric`、`rcNumericHint`。计划执行后可置 null。

Companella `classifyCompanellaDifficulty()` 返回全部字段：`estDiff`、`numericDifficulty`、`numericDifficultyHint`、`danLabel`、`variant`、`confidence`、`rawModelOutput`。需要 MSD 八项、Interlude 星数、Sunny 星数输入。`confidence` 是输出距段位中心计算出的值，不是经验证的正确概率。

## 3. SunnyWindow / LN 输出

来源：`js/estimator/sunnyWindowEstimator.js`、`js/rework/sunnyWindowAlgorithm.js`。

最终估算返回公共字段加：

- `lnStar`：满足展示条件后采用的 LN 星数，否则 0。
- `typePercentageData`：`[["All", count], ["RC", count], ["Mix", count], ["HB", count], ["LN", count]]`。源码返回的是计数，展示层才换算比例，字段名虽然含 Percentage 但不是直接的百分数。

底层 `calculateLN()` 还可返回 `lnPartsRatio`、`graph`、`typePercentageData`；没有 LN 时为 `{ NoLN: true, typePercentageData }`。适用失败可以返回 -1 / -2，不能视为有效星数。

## 4. 键型报告与全部子类

来源：`js/patterns/service.js`、`summary.js`、`clustering.js`、`patternsDef.js`。

报告全部字段：`Clusters`、`Category`、`LNPercent`、`HBRowRatio`、`ModeTag`、`SVAmount`、`Duration`；直接调用 report 还带 `ImportantClusters` getter。ModeTag 可以是 `RC`、`Mix`、`HB`、`LN`；`Duration` 为首尾 note 时间差（ms）。

每个 Cluster 全部数据：`Pattern`、`SpecificTypes`（`[子类名称, 占比]` 数组）、`RatingMultiplier`、`BPM`、`Mixed`、`Amount`。直接调用还有 `Importance` getter 和 `format(rate)` 生成的文字；跨 Worker 的管线会剔除 getter/方法，仅保留六个数据字段。

六大类：`Stream`、`Chordstream`、`Jacks`、`Coordination`、`Density`、`Wildcard`。

| 键数 | 大类 | 全部子类名称 |
| --- | --- | --- |
| 4K | Stream | Rolls、Trills、Minitrills |
| 4K | Chordstream | Handstream、Split Trill、Jumptrill、Jumpstream |
| 4K | Jacks | Longjacks、Quadstream、Gluts、Chordjacks、Minijacks |
| 4K | Density | JS Density、HS Density、Inverse |
| 7K | Stream | 无专属子类 |
| 7K | Chordstream | Brackets、Double Stream、Dense Chordstream、Light Chordstream |
| 7K | Jacks | Longjacks、Chordjacks、Minijacks |
| 7K | Density | DS Density、DCS Density、LCS Density、Inverse |
| 其他键数 | Stream | 无专属子类 |
| 其他键数 | Chordstream | Chord Rolls、Double Stream、Dense Chordstream、Light Chordstream |
| 其他键数 | Jacks | Longjacks、Chordjacks、Minijacks |
| 其他键数 | Density | DS Density、DCS Density、LCS Density、Inverse |
| 所有键数 | Coordination | Column Lock、Release、Shield |
| 所有键数 | Wildcard | Jacky WC、Speedy WC |

注意 Double / Triple Jumpstream 检测函数存在于源码，但没有注册在 SPECIFIC_4K 返回表中，因此当前公共报告不会把它们作为独立子类返回。

## 5. Rework PP

来源：`js/rework/sunnyAlgorithm.js`、`reworkPerformance.js`、`js/app/livePp.js`。

静态 `ppMetrics` 全部字段：`star`、`variety`、`accScalar`、`totalNotes`、`spikiness`、`switches`。

`calculateReworkPp()` 全部返回字段：`pp`、`v2Acc`、`proportion`、`accMultiplier`、`varietyMultiplier`、`lengthMultiplier`，无效输入返回 null。

界面五行：Max PP / Live PP、Proportion、Acc Multiplier、Variety Multiplier、Length Multiplier。每行显示对象字段：`key`、`label`、`value`、`min`、`max`、`centered`。满判定计算 Max PP；游玩时用实际 `perfect/great/good/ok/meh/miss` 判定数计算 Live PP，NF / EZ 影响乘数。

## 6. Etterna MSD

来源：`js/ett/calc.js`、`index.js`、`constants.js`。

全部返回字段：`keycount`、`lnRatio`、`metadata`、`requestedEtternaVersion`、`etternaVersion`、`etternaVersionFallbackReason`、`rowCount`、`junkFile`、`values`、`engine`（包装层添加，值 wasm）。只有零或一行时省略版本 / rowCount / junkFile 字段，values 全为 0。

`values` 全部八项：`Overall`、`Stream`、`Jumpstream`、`Handstream`、`Stamina`、`JackSpeed`、`Chordjack`、`Technical`。

支持键数 4–18；可选择版本 0.68.0-Unofficial、0.70.0、0.72.0、0.72.3、0.74.0、0.75.0。默认 scoreGoal 0.93，musicRate 可改变。这些是计算条件，不是新输出指标；不同条件的数值不能直接混用。

## 7. 底层解析器数据

来源：`js/parser/osuFileParser.js`，`getParsedData()`。

全部返回字段：`columnCount`、`columns`、`noteStarts`、`noteEnds`、`noteTypes`、`od`、`gameMode`、`status`、`lnRatio`、`metaData`、`breaks`、`objectIntervals`。

- columns / noteStarts / noteEnds / noteTypes 为相互对应的逐物件数组。时间为 ms；noteTypes 为 osu! 物件类型位标记。
- breaks：`[startMs, endMs]` 数组。
- objectIntervals：`[startTime, interval]` 数组。
- metaData 原样保留 Metadata 节全部键，常见 `Title`、`TitleUnicode`、`Artist`、`ArtistUnicode`、`Creator`、`Version`、`Source`、`Tags`、`BeatmapID`、`BeatmapSetID`；额外自定义 Metadata 键也会保留，所有值为文本。
- timingPoints / noteTimes 虽为解析器实例内部属性，但不在 getParsedData 公共返回中。

## 8. 实时界面附属数据

来源：`js/app/socketHandlers.js`、`hud.js`、`graph.js`、`graphMath.js`、`livePpCounts.js`；文档 `upstream/docs/features/pause-detection.md`。

- 原生数据源选择、客户端状态、当前谱面、Mod、speedRate、有效 OD、谱面链接和封面：来自 tosu / 桌面原生读取 / bridge，不是仅上传 osu 文件就能获得的额外算法结果。
- 实时判定六项：perfect、great、good、ok、meh、miss；用来驱动 Live PP。
- 播放进度：songTimeMs、songStartMs、songEndMs；图上当前光标值可以插值读取。
- 暂停：pauseMarkerTimes（ms 数组）、pauseCount、isPaused、pauseTimeMs、frozenInterpMs。来自游戏 game.paused，静态谱面无法推断玩家暂停次数。
- 归一化曲线数据包含 times、values、minYValue、maxYValue；展示层还加工 SVG 曲线、进度着色和暂停标记。
- 最终 Vibro 标记与 SV 标记、键型 Category / ModeTag、算法胶囊、Loading / Unsupported Chart / No data 等提示属于展示派生数据或状态。

## 9. 输出与配置的边界

算法选项包括 speedRate、odFlag、cvtFlag（IN / HO）、classicMod、withGraph、withPpMetrics、forceSunnyReferenceHo、forceSunnyWindow、enableAnalyzeLN、enableAlwaysShowLNDifficulty、display6kLevel、extendedEstimationRange、withPattern、withEtterna、withInterlude、etternaVersion、companellaEtternaVersion、marathonCorrection。这些决定如何计算，不是返回参数。

外观主题、显示行开关、预设、数据源路径、WebSocket 地址、缓存和匿名遥测设置也不是谱面分析指标。`backend/` 主要处理匿名遥测 / 管理统计，不能将其 analytics 接口误作可直接调用的谱面分析 HTTP API；核心分析代码在前端 JS 管线与 WASM / ONNX 中。
