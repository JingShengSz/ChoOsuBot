# 段位图案覆盖检查

检查对象：`js/estimator/intervals/*.js` 中 485 个预测区间标签，去掉 high/low 等后缀后共有 97 种基本名称。当前素材中有 36 种可按名称明确对应；61 种没有明确对应的图案。Reform 1–10 已补齐。运行 `audit_icons.py` 可复查完整逐项清单。

| 系列 | 缺少图案的名称 |
| --- | --- |
| 4K 常规 | Intro 1–3、Lambda、Mu、Nu、Xi、Omicron、Pi、Rho |
| 10K Level | Level 0–10、Level V、Level XI |
| 6K/7K Regular | Regular 0–10、Regular Azimuth、Regular Gamma、Regular Stellium、Regular Zenith |
| 7K Wild | Wild 1–9 |
| LN | LN 0、LN 17–20、LN Azimuth、LN Celestial、LN Finish、LN Gamma、LN Mystery、LN Nihility、LN Stellium、LN Terra、LN Zenith |

素材库里另有 `5.webp`、`10.webp` 等纯数字图案，但未标明属于 Level、Regular 还是其他体系，因此没有把它们算作这些系列的专用图案。`Hypersovae LN 16` 可对应 `ln16.webp`；`Lnlism LN 17` 缺少 `ln17.webp`。V1–V14 图案齐全；未确定 V 段位的 Vibro 使用 `question.webp`，旧波形图已弃用。
