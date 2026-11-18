# PromptGo v1.2.1 发布说明（图像提示词 + 交付热修）

> 2026-11-18 · 版本唯一来源 `engine.__version__`，组件 `VERSION` 与之同步（有测试守） · 上一版 v1.1.0
>
> v1.2.1 = v1.2.0（11-17 图像提示词）+ 11-18 的两个交付级热修（演示页样式 404、双击 exe 不开浏览器），
> 见 §4.1。功能面与 v1.2.0 完全一致，升级只需覆盖 `server/` 与 `web/`。

## 1. 一句话

新增**图像提示词**能力：同一句需求，识别为 `intent=image` 后输出 8 段式提示词，并按 MJ / SDXL / Flux / DALL·E 3 切换尾部写法；
带灰度开关（可一键回滚到纯文本）、本地反馈日志与双周复盘机制。**不联网、不加依赖、文本链路指标不变。**

## 2. 新增

| 能力 | 说明 |
| --- | --- |
| 图像意图与 8 段结构 | 主体/场景/构图/光线/风格/材质/技术/负面；6 类场景、324 条术语、缺省补位并标在 `defaults` |
| 平台方言 | `generic`（默认）/ `mj`（`--ar --v --style raw --no`）/ `sdxl`（`negative:` 行）/ `flux`（`; avoid`）/ `dalle3`（自然语言约束） |
| 比例与主体提取 | `16:9` / `16比9` / 竖版 均可识别；比例词不再被当主体，无主体时用场景名占位并给 `missing_subject` |
| 灰度开关 | `--enable-image on|off`；关闭后 `/v1/meta` 停止下发 `image_*`，图像需求回落文本行为 |
| 默认方言 | `--image-platform`，请求里的 `platform` 仍可覆盖 |
| 组件展示 | 场景/比例/风格/构图/光线 chips、平台下拉、有用/没用按钮 |
| 反馈通道 | `POST /v1/feedback` → 本地 JSONL（`logs/feedback.log`，4 MB 滚动），不记 IP、不联网 |
| 看板脚本 | `tools/feedback_report.py`：复制率/重试率/好评率/归因完成率 + 失败样本一键导出 |
| 验收工具 | `tools/image_eval.py`（120 条断言）、`perf_bench.py`（P95/体积门槛）、`style_matrix_check.py`（领域×风格 100 条） |

## 3. 变更（含修复）

- **模板去重**：AV/EC/PS 限定句与 S7 固定句撞词、主体已带材质时 S6 不再复述；正文长度 181–228 → 164–212。
- **主体提取**：产物词在前的句式（「做一张宣传图，秋日露营帐篷营地…」）不再把整句壳当主体。
- **术语匹配**：`match_terms()` 改为在 lower 后的文本上比对，修复 `3D 渲染` / `2.5D 插画` 永不命中。
- **提示文案**：风格冲突提示改用中文领域名（原为 `energy` 等 code）。
- **`/v1/health`** 新增 `image:{enabled,platform}` 与 `feedback` 字段。

## 4. 交付矩阵

| 形态 | 状态 | 产物 |
| --- | --- | --- |
| A 源码 + Python | ✅ 本版主交付 | `server/` `web/` `start.bat` `start.sh` |
| C zipapp | ✅ 已打并验启动 | `dist/promptgo.pyz`（78,255 B）+ `dist/web/` |
| B 单文件 exe | ✅ 已打并实测（11-18） | `dist/promptgo.exe`（8,112,921 B / 7.7 MB，含 `web/`）；未签名，目标机若启用 WDAC/AppLocker 仍可能被拦 |

**校验值（SHA-256）**

```
promptgo.pyz              82,420 B  adcb29c880bdf6690b62fe7a609f35f015317f248760517fd4aed142e16721bd
web/prompt-enhancer.js    40,936 B  d71f740069da2f84d55c4fa2b5cb5330ae670107f4dc80c24369aa9184d89259
dist/promptgo.exe      8,113,305 B  6d09aaa9672ae486392fdc2854f645157763e9d4939eb00c78f22de1b25dda12
```

发布包不含 `logs/`、`dist/`、`.git/`；`dist/` 已在 `.gitignore` 中。

### 4.1 v1.2.1 的内容：v1.2.0 发布后热修（2026-11-18）

实测双击 exe 时暴露两个问题，均已修、版本号升至 1.2.1 并重打产物（上表校验值即 1.2.1）：

| 现象 | 根因 | 修复 |
| --- | --- | --- |
| 打开 `/` 后页面无样式、SVG 被放大成整屏 | 演示页用相对路径 `./app.css`，在 `/` 下解析为 `/app.css`，而静态路由只有 `/demo/app.css` → 404 | 页面资源改绝对路径（`/demo/app.css`、`/prompt-enhancer.js`），路由补 `/app.css` 别名 |
| 双击 exe 不自动打开浏览器 | `--open` 默认关闭，双击不带参数 | 冻结态且无参数时默认开演示页；带参数仍以 `--open` 为准 |

## 5. 升级步骤（A → A）

1. 停服务（`Ctrl+C`）。
2. 覆盖 `server/` 与 `web/`（配置文件无需改动，无数据迁移）。
3. 启动：`python server/app.py --port 7317`；确认 `/v1/health` 里 `image.enabled=true`、`version=1.2.1`。
4. 冒烟：`python -m unittest discover -s tests`（应 **310 通过**）；`python tools/image_eval.py`（应 120/120）。

## 6. 回滚

| 场景 | 操作 | 结果 |
| --- | --- | --- |
| 只想关闭图像能力 | 重启加 `--enable-image off` | 回落纯文本；`/v1/meta` 无 `image_*`；反馈仍可用 |
| 要整体退回 v1.1.0 | 用上一版目录覆盖 | 无数据迁移；反馈日志可保留（v1.1.0 忽略该文件） |
| 回滚演练 | `python -m unittest tests.test_gray_release` | 12 例，覆盖开启/回滚两端行为 |

## 7. 已知限制

1. **领域 × 风格承接率 100%（99/99）**（门槛 85%，T1 灰区 11-17、T2 禁配 11-17、T3 维度归位 11-18 依次修复）；该指标只证明「点名的词落了地」，不等于画面好看，主观质量以盲评为准。词表外仅剩 `概念设定`，见 `docs/image-prompt/DOMAIN-STYLE-MAP-v0.1.md` §4.1。
2. **未成年人保护 / 在世艺术家署名**目前只有文档约定、无代码路径（计划 §9.6 已知缺口）。
3. **组件体积余量 4,120 B**（40,936 / 45,056，占 9.1%）：11-18 T5 瘦身后由 2,078 B 回升，仍不宽裕，再加 UI 前先核算字节或改懒加载。
4. **反馈数据为 0**：灰度观察期 2026-11-18 ~ 11-24，届时填 `docs/image-prompt/GRAY-REPORT-v0.1.md` §4。
