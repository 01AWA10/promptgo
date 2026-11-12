# 任务二 · 核心实现走查与差距补齐

> **历史文档（归档）**：本文是 2026-11-10 的走查快照，当时的数字（12 项缺陷、37 → 46 个用例、组件 37.1 KB）不代表当前状态。
> 现状请看 [`PROGRESS-AUDIT.md`](./PROGRESS-AUDIT.md)（152 个用例、组件 39,287 B）。以下内容保留原文，不再更新。

> 范围：`server/`（引擎 + HTTP 层）、`web/prompt-enhancer.js`（组件）
> 方法：逐文件通读 → 按「契约一致性 / 健壮性 / 安全 / 质量」四类记录问题 → 修复 → 用测试与真实接口双重验证
> 结论：发现 12 项缺陷并全部修复，测试从 37 增至 46 个用例，真实接口复验 5/5 通过

---

## 1. 缺陷清单与修复

### P0 · 功能缺陷

| # | 位置 | 问题 | 修复 |
| --- | --- | --- | --- |
| 1 | `engine/pipeline.py` `stream()` | 终稿由 `"".join(parts).strip() + "\n"` 拼出，与 `enhance()` 的 `assemble()` 相差一个尾部换行；文档承诺的「逐字符一致」实际靠测试里的 `.strip()` 掩盖 | 末块不再追加分隔符，终稿直接取拼接结果；新增测试用 `assertEqual` 严格比对 |
| 2 | `web/prompt-enhancer.js` `enhance()` | 浏览器不支持 `ReadableStream` 时，对 **SSE 响应**调用 `res.json()`，必然解析失败——回退分支等于失效 | 新增 `_requestJSON()`，回退时改请求 `/v1/enhance` |
| 3 | `http_layer._read_json()` | `int(Content-Length)` 未捕获异常，畸形请求头会让处理线程抛 `ValueError`，客户端拿不到任何响应 | 捕获并返回 `400 BAD_LENGTH` |

### P1 · 健壮性与安全

| # | 位置 | 问题 | 修复 |
| --- | --- | --- | --- |
| 4 | `http_layer.do_GET` → `_serve_file` | 静态直出只校验「文件在项目根内」+ 后缀白名单，`/../server/http_layer.js` 这类请求可绕过（`.js` 在后缀白名单里） | `_serve_file(relative, base="web")`，resolve 后必须是 `web/` 的子路径 |
| 5 | `http_layer._cors` | 白名单模式下遇到未授权 `Origin`，回显白名单里的**第一个**来源 | 改为不回显任何 `Allow-Origin`，交由浏览器拒绝 |
| 6 | `RateLimiter._hits` | 字典只增不减，长期运行会随访问者数量缓慢泄漏内存 | 条目数超过 256 时清理已过期来源 |
| 7 | `_copy()` | 回退复制时把临时 `textarea` 插进 `shadowRoot`，部分浏览器 `execCommand("copy")` 读不到 Shadow DOM 选区 | 改挂 `document.body`，补 `readonly` 与 `setSelectionRange` |
| 8 | `_renderScore()` | 服务端返回值直接拼进 `data-w` 属性与文本节点，未做数值化 | `Number()` + `clamp(0,100)` 后再渲染 |

### P2 · 质量与体验

| # | 位置 | 问题 | 修复 |
| --- | --- | --- | --- |
| 9 | `renderer._objective()` | 把原始需求**全文**嵌进「目标」章节，8000 字输入会让输出膨胀近一倍 | `_quote_source()` 压缩空白并截断到 120 字加省略号 |
| 10 | `enhance()` | 超过 8000 字时静默截断，用户不知道内容被裁剪 | 截断时弹 toast |
| 11 | 输入框 `input` 监听 | 每次按键同步写 `localStorage` | 400 ms 防抖 |
| 12 | 评分区 | 服务端已返回 `grade_after`（如「可直接执行」），前端从未展示 | 评分区底部新增「评估：xxx」行 |

---

## 2. 新增测试（9 个，总数 37 → 46）

| 用例 | 守护的缺陷 |
| --- | --- |
| `test_stream_equals_json_for_all_formats` | #1（markdown/text × struct/concise 四组合严格相等） |
| `test_stream_equals_json` 断言改为 `assertEqual(chunks, result)` | #1（去掉 strip 放宽） |
| `test_long_input_does_not_bloat_output` | #9 |
| `test_traversal_with_allowed_suffix_blocked` | #4（`.js`/`.html` 后缀也必须在 web/ 内） |
| `test_bad_content_length` | #3 |
| `test_body_too_large` | 413 分支回归 |
| `CorsWhitelistTestCase` ×2 | #5（授权回显 / 未授权不回显） |
| `RateLimiterTestCase` ×2 | #6（限流生效 / 过期清理） |

---

## 3. 验证结果

**单元 + 协议测试**

```
运行 46 个用例 | 失败 0 | 错误 0
```

**真实服务复验（127.0.0.1:7317）**

| 项 | 结果 |
| --- | --- |
| SSE 拼接 == JSON 终稿 | 严格相等（972 字符） |
| 8500 字输入 | `truncated=true`，输出 910 字（修复前会接近 2 倍） |
| `GET /../server/http_layer.js` | `404` |
| 非法 `Content-Length` | `400 BAD_LENGTH` |
| 组件静态资源 | `200`，37.1 KB（仍 < 40 KB 上限） |

**前端运行时（无头浏览器）**

- 无 JS 异常（`errors: []`）
- 结果渲染 977 字，评分 `86/100（+61，原 25）`，五维条正常
- 新增「评估：可直接执行」行渲染正确
- 复制按钮可用，点击后 toast 正常出现

---

## 4. 记录但未处理

| 项 | 原因 |
| --- | --- |
| 结果区 `aria-live` 播报 | 流式每帧更新会触发连续播报，需专门设计节流策略，收益低于成本 |
| 无「取消」按钮 | 本地引擎耗时 < 1 ms，取消无实际意义；`AbortController` 已就绪，接远程模型时再暴露入口 |
| `META.dims` 为字符串数组，`score.dims` 为对象数组 | 前端未消费 `META.dims`，改动会破坏既有契约；如需统一，v1.1 加 `dims_detail` 字段 |
| 组件 UI 固定中文 | 与 `lang`（输出语言）是两件事，属于 i18n 范围外 |

---

## 5. 对文档的同步修改

`docs/ARCHITECTURE.md` 已同步三处：

1. 3.5 补充「白名单外不回显 `Allow-Origin`」与静态直出的目录约束；
2. 新增 3.6 错误码表（9 个 code，与实现一一对应）；
3. 第 6 节事件一致性改为「逐字符，含 text 格式」，并补「长输入不膨胀」指标。
