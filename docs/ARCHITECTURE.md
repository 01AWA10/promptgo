# PromptGo · 可嵌入网页的离线提示词增强工具 —— 技术选型与架构说明

> **任务一交付物**：在编码前锁定技术选型与架构边界。
> 版本 v1.0 · 本文所述能力均已在 `server/`（后端）与 `web/`（前端）落地，未落地项集中列于第 8 节「已知边界」，不做超前承诺。

---

## 0. 结论速览

| 决策维度 | 选型结论 | 一句话理由 |
| --- | --- | --- |
| 前端嵌入方式 | **Custom Element（Web Component）+ Shadow DOM**，单文件 IIFE，`<script>` 一行引入 | 与宿主框架无关、天然样式隔离、零构建零依赖 |
| 前端承载形式 | **悬浮球 + 侧边抽屉**；另有 `layout="inline"` 常驻内联形态 | 不抢占宿主布局，任意页面可直接使用 |
| 前后端通信 | **HTTP/1.1 REST + SSE（`text/event-stream`）**，走 `127.0.0.1` 本地端口 | 只需后端→前端单向流，无需 WebSocket 握手与重连状态机 |
| 增强引擎 | **规则/模板驱动的确定性流水线**（纯 Python 标准库） | 真正零联网、零模型下载、毫秒级、结果可复现 |
| 后端运行时 | **Python 3.11+ 标准库 `http.server`**，**零第三方依赖** | 离线机器无需 pip、无需 venv、无需 node_modules |
| 分发形态 | 源码目录 + `start.bat` / `start.sh`；`build.py` 一键打出单文件可执行程序（实测 7.7 MB） | 内外网隔离环境可离线拷贝运行 |
| 进程模型 | 常驻单进程 + 多线程 HTTP 服务，仅监听回环地址 | 单用户本地工具，无需集群与队列 |
| 质量保障 | 176 个用例（引擎与模板 56 + 扩充 14 + 元数据 12 + 端口与 CLI 34 + 协议 40 + 前端 7 + 打包与版本 13），含 SSE 分帧、鉴权、越界、错误分支、上限配置、控制台编码、组件纯逻辑、骨架加分与 zipapp 归档 | 规则引擎可解释、可回归；`tools/expansion_bench.py` 用旧词表快照做前后对比 |

---

## 1. 需求约束 → 技术约束的映射

| 原始需求 | 派生技术约束 | 架构落点 |
| --- | --- | --- |
| 可嵌入网页 | 不污染宿主 DOM/样式；不要求宿主是 React/Vue；包体小 | Shadow DOM + 单文件 ES2020，无 polyfill |
| 完全离线 | 禁止云端 API；禁止运行时下载模型/依赖 | 引擎纯规则化；后端零依赖；无 CDN 字体与图标 |
| 前后端走本地端口 | 可配置端口、回环绑定、CORS、启动自检 | `127.0.0.1:7317`（可改）+ 预检 + 健康探测 |
| 提示词增强 | 输入质量方差大，需稳定产出结构化提示词 | 分析 → 补槽位 → 模板渲染 → 自检评分 |
| 结果展示与复制 | 过程可见、结果可用 | SSE 分段流式 + 一键复制 + 回填宿主 |
| 前端体验 | 避免"白屏等待" | 阶段事件：分析(<1ms) → 骨架 → 正文吐字 |

---

## 2. 前端：嵌入方式与承载形式

### 2.1 备选方案对比

| 方案 | 隔离性 | 接入成本 | 包体 | 通信复杂度 | 结论 |
| --- | --- | --- | --- | --- | --- |
| **Custom Element + Shadow DOM** | 高（样式/事件封闭） | 一行 `<script>` + 一行标签 | **38.4 KB / gzip 11.4 KB** | 低 | ✅ **采用** |
| iframe 沙箱 | 最高 | 需托管独立页面 + `postMessage` | 页面独立 | 中 | 备选：仅当宿主 CSP 极严时 |
| 纯 JS SDK（注入 `div`） | 低（样式易冲突） | 低 | 小 | 低 | 否决：与宿主样式互相污染 |
| 浏览器扩展 | 最高 | 需用户安装 | — | 低 | 否决：不符合"嵌入网页" |

选 Web Component 的决定性理由：宿主只需两个标签，**不需要构建链、不需要框架适配层**，且 `attachShadow` 让组件内的内联样式与 SVG 与宿主完全互不干扰。代价是不支持 IE（已确认不在范围内）。

### 2.2 承载形式

- **默认 `layout="bubble"`**：右下角（`position="left"` 可换左侧）悬浮球，展开为 `min(392px, 100vw-32px)` 宽、最高 688px 的抽屉；面板内 `Esc` 收起。
- **`layout="inline"`**：组件作为块级元素常驻页面流，适合已自建对话区的产品页；此时结果区不限高。
- **数据来源双通道**：`target="#input-id"` 绑定宿主已有 `textarea`（打开时读取、点「替换原文」回写并派发 `input`/`change` 事件），或直接用组件内置输入区。
- **事件契约**：`pe:result`（`original` / `enhanced` / `analysis` / `score` / `elapsed_ms`）、`pe:error`、`pe:open` / `pe:close`、`pe:copy`。
- **程序化 API**：`window.PromptEnhancer.enhance(text, opts)`（不渲染 UI）、`.create(attrs)`、`.render(md)`、`.version`。
- **降级策略**：探活失败时面板顶部显示明确引导（附启动命令），不静默失败；`ReadableStream` 不可用时自动回退为一次性 JSON 请求；草稿存 `localStorage:pg:draft`，刷新不丢。

### 2.3 属性表（实现即契约）

| 属性 | 取值 | 说明 |
| --- | --- | --- |
| `target` | CSS 选择器 | 绑定 `textarea/input`，读原文 + 回填 |
| `layout` | `bubble`（默认）/ `inline` | 抽屉 / 内联 |
| `mode` | `struct` `concise` `creative` `academic` `code` `agent` | 增强模式 |
| `intensity` | `light` `standard` `deep` | 章节数（4 / 8 / 9，deep 含风险提示）与深度 |
| `lang` | `auto`（默认）/ `zh` / `en` | 输出语言，默认跟随输入 |
| `theme` | `auto` / `dark` | 主题 |
| `position` | `right`（默认）/ `left` | 悬浮球位置 |
| `z` | 数字 | 自定义 `z-index` |
| `token` | 字符串 | 服务开启 `--token` 时的 `X-PE-Token` |
| `endpoint` | URL | 覆盖默认 `http://127.0.0.1:7317` |
| `label` / `placeholder` | 文本 | 悬浮球文案 / 输入占位符 |
| `open` | 布尔属性 | 初始展开 |

### 2.4 兼容性基线

Chrome/Edge ≥ 90、Firefox ≥ 90、Safari ≥ 15（Custom Elements v1 + `attachShadow` + `fetch` 流式读取）。
不使用可选链以外的实验语法，不引入 polyfill（离线环境下 polyfill 会反噬包体）。
Safari 14 及以下无 `ReadableStream` 响应体，自动走 JSON 回退分支（无流式，功能不降级）。

---

## 3. 前后端通信协议

### 3.1 为什么是 REST + SSE 而非 WebSocket

1. 增强结果**只需后端 → 前端单向流**，WS 的双向能力冗余。
2. WS 需要握手、心跳、断线重连状态机；SSE 复用普通 HTTP 的 CORS、鉴权、日志与代理配置。
3. `EventSource` 只支持 GET，因此实现采用 **`fetch` + `POST` + `ReadableStream` 手工分帧 SSE**，既有请求体又能流式读取。

### 3.2 端点清单

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `GET` | `/v1/health` | 探活：版本、引擎类型、鉴权开关、输入上限 |
| `GET` | `/v1/meta` | 模式/深度/格式/评分维度/上限 + `intents`(12) / `domains`(23，含 general) / `channels`(36 标签) / `tones`(41 标签)（前端渲染选项用） |
| `POST` | `/v1/enhance` | 一次性返回完整 JSON |
| `POST` | `/v1/enhance/stream` | SSE 流式返回 |
| `GET` | `/prompt-enhancer.js` | 组件本体（宿主持久化引用） |
| `GET` | `/` `/demo/` `/demo/app.css` | 演示宿主页 |
| `GET` | `*.html` `*.css` `*.js` `*.svg` `*.png` | `web/` 目录静态直出（带越界校验） |

### 3.3 请求体与响应

```json
{
  "text": "帮我写个关于新能源汽车的营销文案，要发小红书",
  "mode": "struct",
  "lang": "auto",
  "intensity": "standard",
  "format": "markdown"
}
```

响应（`/v1/enhance`）：

```json
{
  "ok": true,
  "enhanced": "## 角色\n...",
  "blocks": [{"key": "role", "title": "角色", "body": "..."}],
  "analysis": {"lang": "zh", "intent": "marketing", "domain": "energy", "topic": "新能源汽车",
               "constraints": [{"kind": "channel", "label": "发布渠道", "value": "小红书"}],
               "missing": [], "risks": []},
  "score": {"before": 24, "after": 83, "delta": 59, "skeleton": true, "dims": [...]},
  "profile": {"mode": "struct", "intensity": "standard", "format": "markdown"}
}
```

### 3.4 SSE 事件序列（实现顺序）

```
event: stage      data: {"stage":"analyze","progress":10,"label":"解析意图、约束与信息缺口"}
event: analysis   data: {"intent":"marketing","intent_label":"营销与文案","domain":"energy","constraints":[...],"missing":[...],"risks":[...]}
event: stage      data: {"stage":"plan","progress":32,"label":"匹配场景模板与增强模式"}
event: plan       data: {"mode":"struct","mode_label":"结构化","intensity":"standard","sections":[{"key":"role","title":"角色"},...],"hint":"..."}
event: stage      data: {"stage":"render","progress":55,"label":"组装结构化提示词"}
event: chunk      data: {"section":"role","delta":"## 角色\n..."}      ← 160 字符切片吐字
event: stage      data: {"stage":"score","progress":92,"label":"计算前后质量评分"}
event: result     data: {"enhanced":"...","score":{"before":24,"after":83,"skeleton":true,...},"analysis":{...}}
event: done       data: {"elapsed_ms":18,"chars":1078,"sections":8}
event: error      data: {"code":"EMPTY_INPUT","message":"..."}          ← 任意阶段可终止
```

约定：`result.enhanced` 与所有 `chunk.delta` 拼接结果**逐字符一致**（有单测守护），保证"流式预览 = 最终文本"。

### 3.5 安全与跨域

- 默认仅监听 `127.0.0.1`；显式 `--host 0.0.0.0` 时启动横幅给出风险告警并**建议同时开启令牌**（未强制，见第 8 节）。
- `Access-Control-Allow-Origin` 默认 `*`（本地开发便利）；`--allow-origin` 收敛为白名单后，**白名单外的来源不再回显任何 `Allow-Origin`**，由浏览器侧拒绝。
- 可选软令牌：请求头 `X-PE-Token`，`--token` 随机生成或自定义；缺失/错误返回 `401`。
- 限流：每 IP 每分钟 90 次，超限 `429`；请求体上限 **64 KB**，超出 `413`；输入正文上限 8000 字符（服务端截断并置 `truncated`）。
- 服务**不写磁盘**（日志仅输出 stdout/stderr），无文件上传、无数据库。
- 静态直出仅限 `web/` 目录内部（resolve 后必须落在 `web/` 之下），后缀白名单只是第二道防线。

### 3.6 错误码

| HTTP | `code` | 触发条件 |
| --- | --- | --- |
| 400 | `BAD_JSON` | 非 UTF-8 的 JSON，或顶层不是对象 |
| 400 | `BAD_LENGTH` | `Content-Length` 不是合法整数 |
| 401 | `UNAUTHORIZED` | 令牌缺失或错误 |
| 404 | `NOT_FOUND` | 未知路径 / 静态资源越界 |
| 411 | `EMPTY_BODY` | 无请求体 |
| 413 | `BODY_TOO_LARGE` | 请求体超过 64 KB |
| 422 | `EMPTY_INPUT` | `text` 为空或仅空白 |
| 429 | `RATE_LIMITED` | 单 IP 超过 90 次/分钟 |
| 500 | `ENGINE_ERROR` | 引擎内部异常（正常不应出现） |

SSE 链路不返回 HTTP 错误码，而是在流内推送 `event: error`，`data` 中携带同样的 `code`。

---

## 4. 离线运行与本地部署

### 4.1 为什么后端"零依赖"

离线/内网环境最大的失败点不是算法，而是 **`pip install` / `npm install` 拉不到包**。因此：

- 后端只用标准库：`http.server`、`json`、`re`、`threading`、`socketserver`、`argparse`。
- 前端不用打包器（无 webpack/vite），源文件即产物，无 `node_modules`、无构建步骤。
- 无 CDN、无远程字体、无远程图标（图标全部内联 SVG 或文字）。
- 引擎为规则实现，**不下载任何模型权重**，无出网请求（可抓包验证）。

### 4.2 启动方式

```bat
:: Windows 一键启动
start.bat                        :: 等价 python server\app.py --port 7317

:: macOS / Linux
./start.sh

:: 指定端口 / 收敛 CORS / 开启令牌
python server/app.py --port 7400 --allow-origin https://intranet.example.com --token
```

服务启动即打印：本地地址、演示页、组件地址、嵌入代码片段（可直接粘贴）。

### 4.3 端口与配置

- 默认 `7317`；被占用时**自动顺延最多 6 个端口**（7317–7322），`--no-fallback` 可关闭该行为。
- 占用判定按「**是否真的有人在监听**」：先对目标端口发起一次连接探测（超时 250 ms），只有连接被拒绝才算空闲；随后真正 bind 时若因竞态失败，继续换下一个端口。
  不能用「能否 bind」判断——Windows 允许同端口重复 bind（`SO_REUSEADDR`），旧实现会让第二个实例直接抢占同一端口而不顺延（已修复，`tests/test_port.py` 守护）。
- `--no-fallback` 下若端口被占用，进程以退出码 1 结束并打印明确原因，而不是静默抢占。
- 顺延后需让组件知道实际端口：通过 `<prompt-enhancer endpoint="http://127.0.0.1:7318">` 显式指定（组件也会读取 `localStorage:pg:endpoint` 供宿主写入，服务端不自动回写）。
- 常驻参数：`--host` `--port` `--token [值]` `--allow-origin`（可重复）`--pace`（吐字间隔毫秒）`--quiet` `--open`。

### 4.4 部署形态

| 形态 | 适用 | 说明 |
| --- | --- | --- |
| **A. 源码目录 + `start.bat`（本项目交付形态）** | 装有 Python 3.11+ 的机器 | 最小成本，改代码即生效；目标机无需联网与 `pip` |
| B. 单文件可执行程序 | 目标机无 Python 且无应用控制策略 | `python build.py` → `dist/promptgo(.exe)`，实测 7.7 MB（PyInstaller 6.22.3）；`web/` 经 `--add-data` 打入包内 |
| **C. zipapp（`.pyz` + 同级 `web/`）** | 目标机有 Python 3.11+，但应用控制策略拦截 exe | `python build.py --zipapp` → `dist/promptgo.pyz`（实测 45 KB）+ `dist/web/`；纯标准库，无签名问题；启动实测 health 200、静态资源正常 |
| D. 快捷方式 + 开机自启 | 终端用户零操作 | 静默启动，组件按默认端口探测 |

> 形态 B 的实测说明：资源根目录由 `app.bundle_root()` 统一解析（源码 / PyInstaller `_MEIPASS` / zipapp 三态）。
> `--add-data` 的源路径必须用绝对路径，否则会被 `--specpath` 解析到 `build/` 下并报 `Unable to find ... web`。
> 产物已验证包含 `web/demo/index.html`、`web/demo/app.css`、`web/prompt-enhancer.js`。
> 若目标机启用应用控制策略（WDAC / AppLocker），未签名 exe 会被拒绝执行（本机实测即如此），需 IT 放行或改用形态 A。
> **交付结论（2026-11-11）**：本项目按形态 A 交付；形态 B 的产物仅作可选附件，不再作为默认路径。
> **补充（2026-11-12）**：新增形态 C，`python build.py --zipapp` 已验证可启动服务并正确提供静态资源，
> 在被 WDAC 拦截的机器上比 exe 更现实；静态资源不进归档，`.pyz` 必须与 `web/` 同级。

---

## 5. 模块划分

### 5.1 三块用户可见模块 ↔ 实现映射（验收口径）

| 模块 | 实现位置 | 关键接口 / 行为 |
| --- | --- | --- |
| **① 输入采集** | `web/prompt-enhancer.js` → `_targetEl` / `_pullFromTarget` / `_persistDraft` | `target` 绑定宿主输入框；打开面板即取文；空值拦截、8000 字符截断、`Ctrl/Cmd+Enter` 提交、草稿自动入 `localStorage` |
| **② 提示词增强处理** | `server/engine/`：`analyzer` → `templates` → `renderer` → `scorer`，由 `pipeline` 编排 | `POST /v1/enhance`（JSON）与 `/v1/enhance/stream`（SSE）共用同一纯函数管线，输出确定且可复现 |
| **③ 结果展示与复制** | `web/prompt-enhancer.js` → `renderMd` / `_renderScore` / `_copy` / `_replace` | 流式增量渲染 + 评分对照条；「复制」走 `navigator.clipboard` 并回退 `execCommand`；「替换原文」写回 `target` 并派发 `input`/`change` |

### 5.2 组件内部结构

```
┌──────────────────────── 宿主网页（任意技术栈） ────────────────────────┐
│  <script src="http://127.0.0.1:7317/prompt-enhancer.js" defer></script> │
│  <prompt-enhancer target="#my-input" mode="struct"></prompt-enhancer>   │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │ Shadow DOM（样式/事件隔离）
        ┌───────────────────────▼────────────────────────┐
        │ 前端模块（web/prompt-enhancer.js，单文件）       │
        │ ① 输入采集  Collector                          │
        │ ② 传输      Transport（探活 / POST / SSE 分帧） │
        │ ③ 展示复制  Renderer（Markdown / 评分 / 复制回填）│
        │ ④ 状态      Store（草稿 / 偏好 / 自定义端点）    │
        └───────────────────────┬────────────────────────┘
                                │ HTTP 127.0.0.1:7317
        ┌───────────────────────▼────────────────────────┐
        │ 后端模块（server/）                             │
        │ ⑤ http_layer 路由 / CORS / 令牌 / 限流 / SSE 编码│
        │ ⑥ pipeline   编排 analyze→plan→render→score     │
        │ ⑦ analyzer   语言/意图/领域/渠道/语气/缺口/风险   │
        │ ⑧ templates  6 模式 × 12 意图 × 22 领域 的骨架库   │
        │ ⑨ renderer   结构化 Markdown 组装（可分段）      │
        │ ⑩ scorer     5 维评分（前/后对比）              │
        └────────────────────────────────────────────────┘
```

| 模块 | 职责 | 关键设计 |
| --- | --- | --- |
| ① 采集 | 绑定、取文、校验、回填、快捷键 | 与渲染解耦，宿主可只借道采集 |
| ② 传输 | 打开时探活、POST、手工 SSE 分帧、AbortController 取消 | 无第三方请求库，`fetch` + `TextDecoder` |
| ③ 展示 | 骨架 → 增量文本 → 评分对照 → 复制/替换/重试 | `requestAnimationFrame` 合批；结束时取消挂起帧，避免覆盖终稿 |
| ④ 状态 | 草稿保存、模式偏好、端点覆盖 | 仅 `localStorage`，无遥测 |
| ⑤ HTTP 层 | 路由表、CORS 预检、令牌、限流、SSE 头、静态资源 | `ThreadingHTTPServer` 每请求一线程；断开类异常静默 |
| ⑥ 流水线 | 幂等编排，阶段事件回调 | 阶段化输出天然支持流式 |
| ⑦ 分析器 | 语言、意图、领域、渠道、语气、显式约束、缺失槽位、模糊表述、主题抽取 | 全正则/词典，长词优先且不重叠，可单测、可解释 |
| ⑧ 模板库 | 意图 → 骨架（角色/目标/背景/步骤/约束/输出契约/自检/待确认）+ 成品章节骨架 `OUTLINES` | 数据驱动，新增场景只加数据 |
| ⑨ 渲染器 | 组装 Markdown，160 字符切片吐字 | 纯函数，`Analysis → str` |
| ⑩ 评分器 | 清晰度/具体性/结构性/约束完备/可验证性 | 启发式打分，驱动前后对比；成品骨架计入「结构性」（+12），`score.skeleton` 标注是否命中 |

**明确不做**（v1 范围外）：账号体系、云端同步、多用户并发、向量检索、模型推理、富文本编辑器。

---

## 6. 性能与兼容性约束

| 指标 | 目标 | 实测 / 保障手段 |
| --- | --- | --- |
| 增强耗时 | ≤ 50 ms（500 字） | **1.20 ms/次（320 字）**；纯正则与字符串拼接，无 IO |
| 首字节（SSE） | ≤ 120 ms | 分析阶段结束即推送 `stage`/`analysis` |
| 组件体积 | ≤ 44 KB 未压缩 | **38.4 KB（39,363 B）/ gzip 11.4 KB**（含内联 CSS 与 SVG；占预算 87.4%，余量 5,693 B） |
| 单文件产物体积 | ≤ 15 MB | **7.7 MB**（8,061,581 B，含 Python 运行时与 `web/` 资源） |
| 单帧阻塞 | ≤ 16 ms | 增量渲染 + rAF 合批，无长任务 |
| 后端常驻内存 | ≤ 60 MB | 无大对象缓存，线程按请求创建 |
| 并发 | ≥ 20 并发不串行 | 每请求独立线程；引擎纯函数、无共享可变状态 |
| 输入上限 | 8000 字符 | 前端截断 + 服务端 `normalize` 二次校验 |
| 事件一致性 | 拼接 = 终稿（逐字符，含 text 格式） | 单测 `test_stream_equals_json_for_all_formats` 覆盖 2 格式 × 2 模式 |
| 长输入膨胀 | 输出不随输入线性增长 | 原文引用截断至 120 字；7500 字输入在 struct/deep 下输出 1068 字符（约 1 KB 量级） |

兼容红线：不要求宿主有构建链；不污染宿主全局（仅注册 `<prompt-enhancer>` 与 `window.PromptEnhancer`）；不注入全局 CSS；层级可用 `z` 属性避让；组件样式全部通过 `<style>` 注入，不使用行内 `style` 属性。

---

## 7. 端到端数据流（以营销文案为例）

```
用户输入「帮我写个关于新能源汽车的营销文案，要发小红书」
  → ① 采集：取文 24 字，长度与空值校验通过
  → ② 传输：POST /v1/enhance/stream，携带 mode/intensity/lang
  → ⑤ HTTP 层：令牌/限流/JSON 校验 → normalize（截断、去空白）
  → ⑦ analyzer：lang=zh，intent=marketing，domain=energy，topic=新能源汽车，
                constraints=[发布渠道=小红书]，缺失=[受众, 调性, 篇幅, 输出格式]，风险=2
  → ⑧ templates：命中 marketing 骨架（过程步骤 + 成品章节骨架），按缺失槽位插入「（待确认）」与追问清单
  → ⑨ renderer：逐段产出 role/objective/context/steps/constraints/output/selfcheck/questions
  → 每 160 字符一个 chunk 回推，③ 逐帧渲染
  → ⑩ scorer：before=24 → after=83（+59，含骨架 +12 的结构性加分），5 维明细随 result 返回
  → ③ 展示：结果区回到顶部、评分条动画、「复制 / 替换原文 / 重试」可用
```

---

## 8. 已知边界（不做超前承诺）

| 项 | 现状 | 影响 / 后续 |
| --- | --- | --- |
| `--host 0.0.0.0` 未强制令牌 | 仅告警提示 | 内网多人共用时需人工加 `--token`；可在 v1.1 改为无令牌拒绝启动 |
| 端口顺延不自动告知前端 | 需显式 `endpoint` 或宿主写 `localStorage:pg:endpoint` | 顺延属低频场景，v1.1 可让服务端回写端口文件 |
| 无本地大模型适配层 | 引擎为固定规则流水线，**未抽象 `EngineAdapter`** | 接 Ollama/llama.cpp 需新增适配层，HTTP 契约可保持不变 |
| 规则模板覆盖面 | 6 模式 × 12 意图 × 22 领域，冷门场景增强幅度有限 | 模板数据化；新增领域/意图有覆盖度测试兜底（漏配即失败） |
| 领域/渠道/语气靠词典命中 | 22 领域 / 38 渠道 / 47 语气；同义改写（把「私域」写成「社群」）仍可能漏判 | 词表与 `tools/expansion_bench.py` 语料同源维护；扩词后跑基准确认不退化 |
| 成品骨架只约束章节顺序 | 骨架计入「结构性」维度（+12）并在 `score.skeleton` 标记，但不评价内容质量 | 骨架用于防跑题与稳定成文结构；分数上涨只代表结构落地，内容质量仍取决于素材与执行模型 |
| 深度不体现为更高分 | `standard`(8 段) 与 `deep`(9 段) 同素材质量分可能相同（结构项已封顶） | 深度增加的是风险与待确认章节，不是文本质量；刻意不用分数暗示「越深越好」 |
| 宿主持久化 | 组件地址建议固定端口，避免宿主页面写死失效 | 可改为同源反代（仍需本地部署） |
| 浏览器支持 | 无 IE / 旧 Safari | 目标产品线不含这些环境 |
| exe 在启用应用控制的机器上被拦截 | 本机实测被 WDAC 阻止（`An Application Control policy has blocked this file`），2026-11-11 重建的 7.7 MB 产物同样被拦；只能用归档校验（`web/` 3 个文件 + `engine` 5 个模块均在包内），无法做运行验证 | 交付前由 IT 放行，或改用形态 A（源码 + Python） |

---

## 9. 最终推荐架构

**一句话**：以**零依赖 Python 标准库服务**作为本地增强后端，以**单文件 Web Component** 作为可嵌入载体，两者通过**回环端口上的 REST + SSE** 通信，增强逻辑用**可解释的规则流水线**实现——在"完全离线 + 免安装依赖 + 任意网页可嵌入"三个硬约束下同时成立。

选型互锁关系（缺一不可）：

```
完全离线 ──► 引擎必须自带知识 ──► 规则/模板（而非模型）──► 毫秒级 + 可复现
免依赖   ──► 后端仅标准库、前端无构建 ──► 拷贝即跑 ──► 内网可交付
可嵌入   ──► Web Component + Shadow DOM ──► 一行 script ──► 与宿主框架无关
本地端口 ──► REST + SSE ──► 单向流足够 ──► 无需 WS 状态机
```

**成本与代价（诚实结论）**：规则引擎的上限低于大模型，增强质量依赖模板覆盖面；这是"完全离线且不下载模型"的必然代价。架构已把引擎隔离为纯函数层，未来接入本地模型时，前端与协议无需改动。
