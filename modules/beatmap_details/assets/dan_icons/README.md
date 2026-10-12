# 段位图案素材

- 原有 `*.webp`（76 张）从 `D:\LLBot\bin\astrbot\data\plugins\astrbot_plugin_osugreek\images.zip` 原样解压。
- `plus.webp`、`minus.webp` 为本项目新增的 high / low 后缀图案，以 `ln8.webp` 的金色、深棕描边和浅金高光为参考绘制。
- 未确定 V 段位的 Vibro 类型现在使用 `question.webp`。原波形图案移到 `deprecated/`，不再加载。
- `reform1.webp`–`reform10.webp` 从用户提供的 `Tech-1.png`–`Tech-10.png` 中提取，保留原渐变和描边。Photoshop 原生去背景，6/8 的内部空洞用 SVG 轮廓遮罩清理；透明画布统一为 1920×1080，WebP 无损编码。
- `reform_sources/` 保留 Photoshop 导出的原始抠图；`reform*.svg` 保留像素和轮廓遮罩，便于后续精修。`prepare_reform.py` 与 `render_reform.cjs` 可重建 PNG。
- `icon_manifest.js` 记录原始透明画布中图案的可见边界，供详情卡等比显示；运行 `audit_icons.py --write-manifest` 可重建。
- 新图与原图同为 1920×1080 透明 WebP；生成脚本为 `make_suffix_icons.py`。
- `suffix_preview.png`、`vibro_preview.png` 是深色背景的对照图，仅供设计审查。
- 缺图清单见 `ICON_COVERAGE.md`；`audit_icons.py` 按实际预测区间复核。

详情卡 `4550525` 的本地预览已接入 Eta、high 后缀及 Vibro 图案。尚未同步服务器。
