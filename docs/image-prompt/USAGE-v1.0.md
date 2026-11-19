# 图像提示词接入与使用指南 v1.0

> 适用于 PromptGo v1.2.3 · 2026-11-19 · 面向「要把图像提示词能力接进自己页面」的开发者
> 规范细节见 [`IMAGE-PROMPT-SPEC-v1.0.md`](IMAGE-PROMPT-SPEC-v1.0.md)，验收数据见 [`EVAL-REPORT-v0.1.md`](EVAL-REPORT-v0.1.md)

## 1. 30 秒接入

```bash
# 1) 启动服务（图像能力默认开启）
python server/app.py --port 7317
# 终端会打印：图像灰度 开启 | 默认方言 generic   /   反馈日志 .../logs/feedback.log
```

```html
<!-- 2) 嵌入组件（文本与图像共用同一个组件，识别是自动的） -->
<script src="http://127.0.0.1:7317/prompt-enhancer.js" defer></script>
<prompt-enhancer target="#my-input" mode="bubble"></prompt-enhancer>
```

```bash
# 3) 直接用接口
curl -s http://127.0.0.1:7317/v1/enhance -H "Content-Type: application/json" ^
  -d "{\"text\":\"做一张夏天海边咖啡店的宣传图，16:9\",\"platform\":\"mj\"}"
```

判断是否走图像链路看 `analysis.intent`：等于 `image` 才有 `analysis.image` 字段。

## 2. 输入什么、输出什么

**输入**：一句话需求即可。比例（`16:9` / `9:16` / `1:1` / `4:3` / `3:4`）、平台（`mj`/`sdxl`/`flux`/`dalle3`）、
风格/光线/构图/材质词都是可选的——缺的会用场景默认值补齐，并在 `analysis.image.defaults` 里标出哪些是补的。

**输出**：8 段式正文（主体 / 场景 / 构图 / 光线 / 风格 / 材质 / 技术 / 负面），通用方言下形如：

```
夏天海边咖啡店，户外自然场景，…，三分法构图，…，暖色温，…，日系胶片，…，16:9 画幅，高分辨率，
细节清晰，边缘干净，构图完整；避免 低质量、模糊、比例畸变、文字水印、…
```

`analysis.image` 里可直接拿来做 UI 的字段：

| 字段 | 含义 | 用途 |
| --- | --- | --- |
| `scene` / `scene_label` | 场景 id 与中文名（6 类：MK/IL/CD/EC/AV/PS） | 场景 chip |
| `ratio` | 生效比例（用户没写则按场景默认） | 比例 chip |
| `platform` | 生效方言（请求值 > `--image-platform` > `generic`） | 平台 chip |
| `picks` | 各维度命中词 `{style, lighting, composition, lens, texture}` | 风格/构图/光线 chip |
| `defaults` | 哪些段是补的默认值 | 提示「这些不是你说的」 |
| `warnings` | 替换/转译/占位留痕，含 `style_conflict` / `spoken` / `missing_subject` | 顶部提示条 |
| `trims` | 超长时被裁掉的段与原因 | 折叠详情 |
| `safety` | `blocked` / `reasons` / `rewrites` | 红线拦截与软红线改写 |

## 3. 平台方言

同一个需求，尾部写法按平台切换（正文 8 段共用同一份词表）：

| 平台 | 尾部写法 | 说明 |
| --- | --- | --- |
| `generic` | `；避免 低质量、模糊、比例畸变…` | 通用自然语言，任何模型都能读 |
| `mj` | `--ar 16:9 --v 6 --style raw --no 低质量, 模糊, …` | Midjourney v6 参数串 |
| `sdxl` | 正文 + 换行 `negative: 低质量, 模糊, …` | SD 系列独立负面提示词行 |
| `flux` | `; avoid 低质量, 模糊, …` | Flux 用英文连接词，正文保持中文 |
| `dalle3` | `。画面中不要出现文字、水印或 logo。` | DALL·E 3 不吃参数，只能自然语言约束 |

**注意**：平台只影响尾部参数与负面词写法，不改变 8 段内容。切错平台不会报错，
但 MJ 参数给 SD 用就是纯噪声——这就是为什么默认值是 `generic`（`--image-platform` 可改服务端默认）。

## 4. 灰度开关与回滚

```bash
python server/app.py --enable-image off     # 回滚：图像能力下线，输出纯文本提示词
python server/app.py --image-platform mj    # 默认方言改为 MJ（请求里仍可覆盖）
```

| 观察点 | `on`（默认） | `off`（回滚） |
| --- | --- | --- |
| `/v1/health` | `image:{enabled:true, platform:"..."}` | `image:{enabled:false}` |
| `/v1/meta` | 含 8 组 `image_*` 清单 | **不下发** `image_*`（不给「能选但没用」的选项） |
| 图像需求 | `intent=image`，输出 8 段 + 平台参数 | 不识别图像意图，回落文本增强行为 |
| 输出参数 | 含 `--ar` / `--no` / `negative:` | 一条都没有 |
| `/v1/feedback` | 正常落盘 | **照常落盘**（反馈与灰度解耦） |

回滚演练脚本：`python -m unittest tests.test_gray_release`（12 例，含开启态、回滚态两端行为）。
演练结论见 [`GRAY-REPORT-v0.1.md`](GRAY-REPORT-v0.1.md) §3。

## 5. 反馈闭环（本地，不联网）

服务端把反馈写成 JSONL（默认 `logs/feedback.log`，超过 4 MB 自动滚动 `.log.1`），
不记 IP、不联网、不上报任何外部服务。字段：`ts / kind / useful / intent / platform / chars / text`（原文截断 1200 字）。

| kind | 谁发 | 含义 |
| --- | --- | --- |
| `enhance` | 组件自动 | 出结果（复制率的分母） |
| `copy` | 组件自动（复制成功时） | 复制率 |
| `retry` | 组件自动（点「重试」） | 行为上的不满意 |
| `vote` | 用户点「有用 / 没用」 | 必带 `useful`，好评率 |

```bash
python tools/feedback_report.py                        # 看板：复制率 / 重试率 / 好评率 / 归因完成率
python tools/feedback_report.py --export failures.md   # 一键导出失败样本（含归因候选）
python tools/feedback_report.py --log logs/feedback.log.1 --json
```

关掉落盘：`--no-feedback-log`；换位置：`--feedback-log D:/data/pe.log`（相对路径落在程序所在目录）。
复盘机制与归因口径见 [`FEEDBACK-LOOP-v1.0.md`](FEEDBACK-LOOP-v1.0.md)。

## 6. 常见问题

**比例写了没生效？** 先看 `analysis.image.ratio`。输入里的 `16:9`/`16比9`/`竖版` 都会被识别；若仍不是你要的，
在看 `warnings` 有没有冲突提示——比例以请求里显式写的为准，其次是场景默认。

**风格被换掉了？** 说明命中了「领域禁配」（如医疗 × 恐怖），`warnings` 有 `style_conflict`，
换成了该领域首选风格。要保留原风格就不要用禁配词，或换一个领域描述。

**负面词为什么只有 4–8 项？** 只放「模型能稳定避开」的词。安全红线（血腥/色情等）**不进负面词**——
扩散模型对「no blood」这类否定常反向激活，安全项在生成前就拦截了（422 `SAFETY_BLOCKED`）。

**主体是「海报展板」？** 说明输入里只有壳词和比例（如「做一张 9:16 竖版海报」），没有具体主体，
引擎用场景名占位并给了 `missing_subject` 提示。补一句「画面是……」即可。

**能关掉图像功能吗？** 能，`--enable-image off`，见 §4；关掉后 `/v1/meta` 不再下发 `image_*`，宿主的图像入口应据此隐藏。

**反馈会外传吗？** 不会。只有本地文件，看板脚本也只是读文件。

## 7. 与文本链路的关系

- 同一个 `/v1/enhance`、同一个组件、同一份令牌与限流；图像只是 `intent=image` 时多出的一段分析。
- 文本链路的指标（P95 ≈1.9 ms、组件体积、192 条基线用例）不因图像能力变化；图像分支只增加约 0.4 ms。
- 输入长度上限仍是 `--max-chars`（默认 8000），图像正文另有 150–260 字的软预算，超了按 S6 → S3 → S7 顺序裁并记在 `trims`。
