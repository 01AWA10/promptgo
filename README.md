# PromptGo · 可嵌入网页的离线提示词增强工具

把「帮我写个文案」这类模糊需求，一键改写成**带角色、领域语境、成品骨架、约束与自检清单**的结构化提示词。
识别层会先判定**意图 / 领域 / 渠道 / 语气**，再把缺失槽位变成追问项，而不是靠猜。
前端是一个零依赖 Web Component，后端是零依赖 Python 标准库服务，两者通过 `127.0.0.1` 本地端口通信，
**全程不联网、不下载模型、不依赖任何第三方包**。

- 技术选型与架构说明：[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- 在线演示（本地）：启动服务后打开 `http://127.0.0.1:7317/demo/`

---

## 快速开始

需要 Python 3.11+（仅标准库，无需 `pip install`；已在 3.13 / 3.14 上实测）。

```bat
:: Windows
start.bat

:: macOS / Linux
./start.sh

:: 或直接运行
python server/app.py --port 7317 --open
```

启动后：

```
本地服务   http://127.0.0.1:7317
演示页     http://127.0.0.1:7317/demo/
组件地址   http://127.0.0.1:7317/prompt-enhancer.js
```

## 嵌入到任意网页

```html
<!-- 1. 引入组件（自动注册 <prompt-enhancer>，无构建步骤） -->
<script src="http://127.0.0.1:7317/prompt-enhancer.js" defer></script>

<!-- 2. 放到页面上，绑定已有输入框 -->
<prompt-enhancer target="#my-input" mode="struct" layout="bubble"></prompt-enhancer>

<!-- 3. 监听结果，接入业务逻辑 -->
<script>
  document.querySelector('prompt-enhancer').addEventListener('pe:result', function (e) {
    console.log(e.detail.enhanced, e.detail.score);
  });
</script>
```

### 属性

| 属性 | 取值 | 说明 |
| --- | --- | --- |
| `target` | CSS 选择器 | 绑定的 `textarea/input`，用于读取原文与回填结果 |
| `layout` | `bubble`（默认） / `inline` | 悬浮球 + 抽屉，或常驻页面流 |
| `mode` | `struct` `concise` `creative` `academic` `code` `agent` | 增强模式 |
| `intensity` | `light`（4 段） `standard`（8 段） `deep`（9 段，含风险） | 章节数量与深度 |
| `lang` | `auto` `zh` `en` | 输出语言（默认跟随输入语言） |
| `theme` | `auto` `dark` | 主题 |
| `position` | `right`（默认） `left` | 悬浮球位置 |
| `z` | 数字 | 自定义 `z-index` |
| `token` | 字符串 | 服务开启 `--token` 时的访问令牌 |
| `endpoint` | URL | 覆盖默认的 `http://127.0.0.1:7317` |

### 事件与 API

| 名称 | 载荷 | 说明 |
| --- | --- | --- |
| `pe:result` | `{original, enhanced, analysis, score, elapsed_ms}` | 增强完成 |
| `pe:error` | `{message}` | 失败 |
| `pe:open` / `pe:close` | `{}` | 面板开合 |
| `pe:copy` | `{text}` | 已复制 |

```js
// 不渲染 UI，直接调用引擎
const res = await PromptEnhancer.enhance("写个周报", { mode: "concise" });
console.log(res.enhanced);
```

---

## 识别能力（规则层）

| 维度 | 规模 | 覆盖 |
| --- | --- | --- |
| 意图 | 12 | coding / marketing / analysis / summarize / translate / plan / writing / qa / agent / review / product / general |
| 领域 | 22 + 通用兜底 | 新能源、技术、营销、电商、教育、金融、医疗、法务、游戏、HR、制造、汽车、文旅、餐饮、房产、科研、安全、物流、政务、客服、农业、内容制作 |
| 渠道 | 55 词条 / **36 标签** | 小红书、公众号、抖音、知乎、微博、朋友圈、官网、B站、视频号、播客、新闻稿、白皮书、企业微信、站内信、信息流、开屏、电梯广告…… |
| 语气 | 63 词条 / **41 标签** | 正式、专业、幽默、冷幽默、毒舌、真诚、干练、极简、网感、接地气、烟火气…… |
| 成品骨架 | 12 套 / 62 条 | 每个意图一份章节顺序，渲染进「任务拆解」；`concise` 模式跳过 |

匹配策略：**长词优先 + 命中不重叠 + 按原文顺序**，同一段文本最多各取 4 个渠道与语气，
超出的部分不静默丢弃——`analysis.truncated` 会给出 `{channel: n, tone: n}` 的数量，前端 chips 显示「另有 N 项未展示」；
营销类意图缺少渠道时会生成追问项，而不是默认某个平台。

词表除本名外还收**同义改写与英文写法**：领域如「社群/裂变」→营销、「快递/仓库」→物流、
「solar/battery」→新能源，渠道如 `rednote`→小红书、`press release`→新闻稿，语气如「风趣」→幽默、`serious`→正式。
别名只指向既有标签，`/v1/meta` 的标签清单不因此变化。

以上清单都可从 `GET /v1/meta` 直接枚举（`intents` / `domains` / `channels` / `tones`），
宿主不必在客户端硬编码：

```bash
curl http://127.0.0.1:7317/v1/meta
# {"intents":[{"id":"coding","label":"代码与工程","label_en":"coding & engineering"},...],
#  "domains":[...,{"id":"general","label":"通用","label_en":"general"}],
#  "channels":[{"id":"小红书","label":"小红书"},...],
#  "tones":[{"id":"正式","label":"正式"},...], ...}
```

---

## 目录结构

```
server/
  app.py            # 启动入口：参数、端口选择、资源根解析、横幅
  http_layer.py     # 路由 / CORS / 令牌 / 限流 / SSE / 静态资源
  engine/
    analyzer.py     # 语言、意图、领域、渠道、语气、约束、缺口、风险
    templates.py    # 6 模式 × 12 意图 × 22 领域 + 成品骨架（数据驱动）
    renderer.py     # 分块渲染结构化 Markdown
    scorer.py       # 5 维启发式评分（增强前后对比，结构性含成品骨架）
    pipeline.py     # 编排 + 流式事件
web/
  prompt-enhancer.js  # 可嵌入组件（单文件，Shadow DOM）
  demo/index.html     # 演示宿主页
tests/
  test_engine.py    # 引擎单测
  test_templates.py # 模板库覆盖度
  test_expansion.py # 扩充效果回归（含基准确认）
  test_port.py      # 端口占用判定与自动顺延（含 Windows 重复绑定回归）
  test_cli.py       # 启动入口：令牌、启动文案、--open、退出码
  test_http.py      # 端到端协议测试（socket 直连）
  test_http_errors.py # 错误分支：429 限流 / 411 空体 / SSE error / 500
  test_frontend.py  # 前端最小冒烟（调用 Node 跑 smoke.mjs，无 Node 时跳过）
  test_packaging.py # 打包形态下的资源根解析
  frontend/smoke.mjs # 组件纯逻辑：SSE 分帧 / target 回填 / JSON 回退
  run.py            # python tests/run.py
tools/
  expansion_bench.py # 扩充前后效果对比（python tools/expansion_bench.py）
build.py            # 打包：python build.py（exe）/ python build.py --zipapp（.pyz）
.github/workflows/ci.yml  # 持续集成：多平台 × 多 Python 跑全量测试
start.bat / start.sh  # 双击启动脚本
```

## 接口

```
GET  /v1/health              探活
GET  /v1/meta                模式/深度/格式/维度/上限 + intents/domains/channels/tones 清单
POST /v1/enhance             {"text":"...","mode":"struct"} → JSON
POST /v1/enhance/stream      SSE：stage → analysis → plan → chunk* → result → done
```

## 测试

```bash
python tests/run.py            # 本地：没有 Node 时前端组自动跳过
python tests/run.py --strict   # CI：跳过即失败，确保前端冒烟真的跑了
# 192 个用例：引擎与模板 71 + 扩充 14 + 元数据 12 + 端口与 CLI 34 + 协议 41 + 前端 7 + 打包与版本 13
# 覆盖意图/领域/渠道/语气/骨架/约束/评分/流式事件顺序/SSE 分帧/CORS/鉴权/越权路径/资源根解析/版本一致性
```

前端 7 个用例通过 Node 跑 `tests/frontend/smoke.mjs`（`node:vm` + 最小 DOM 桩，无需 jsdom）。
本机没有 Node 时自动跳过；可用 `NODE=<node 路径> python tests/run.py` 指定解释器。

持续集成见 `.github/workflows/ci.yml`：ubuntu 与 windows 双平台 × Python 3.11/3.13，
安装 Node 22 后执行 `python tests/run.py --strict`，并附带 `compileall` 语法检查；
缺少 Node 导致前端组被跳过时，流水线会直接失败而不是显示绿色。

扩充前后效果对比（固定语料 + 旧词表快照，可重复）：

```bash
python tools/expansion_bench.py
# 领域准确率 50% → 100%（34 条）；渠道召回 36% → 100%；语气召回 25% → 100%
# 词表 16→22 领域 / 26→55 渠道 / 24→63 语气；成品骨架 0 → 12 意图 62 条
# 同一样例输出 977 → 1078 字符；意图判定只改 1 条（短剧脚本 coding→writing）
```

## 命令行

```bash
python server/app.py \
  --port 7317            # 端口被占用时自动顺延（最多 6 个：7317–7322；--no-fallback 可关闭）
  --host 127.0.0.1       # 仅监听回环；改为 0.0.0.0 时建议同时开 --token
  --token                # 随机令牌，请求头 X-PE-Token
  --allow-origin URL     # 收敛 CORS 白名单，可重复
  --pace 6               # 流式吐字间隔（毫秒），0 为关闭
  --rate-limit 90        # 每分钟请求上限，默认 90
  --max-body 64          # 请求体上限（KB），默认 64
  --max-chars 8000       # 单次输入字符上限，默认 8000
  --quiet --open
```

另有 `--version`，打印版本后直接退出。三个上限会同时反映到 `/v1/health`（`max_chars`）
与 `/v1/meta`（`limits.max_chars`），浏览器端与宿主脚本可据此对齐，不必改代码。

## 交付形态

本项目以**形态 A（源码 + Python）**交付。目标机只需 Python 3.11+，无需联网、无需 `pip install`。

拷贝以下内容即可运行：

```
server/            # 引擎与 HTTP 层
web/               # 组件 + 演示页
start.bat          # Windows 双击启动（优先用 py -3，自动 chcp 65001）
start.sh           # macOS / Linux
README.md          # 可选，随交付附上
```

验证清单（已在交付机实测）：`start.bat 7451` → `/v1/health` 返回 200 →
`/prompt-enhancer.js` 返回 200（39,778 B）→ 演示页可打开。

形态 B（单文件 exe）与形态 C（`.pyz`）均为可选，见下一节。若目标机启用了 WDAC / AppLocker，
未签名 exe 会被直接拦截（本机即如此），此时用形态 A 或形态 C，或由 IT 放行。

## 打包（可选）

**形态 C：zipapp（推荐给「目标机有 Python、但有应用控制策略」的机器）**

```bash
python build.py --zipapp          # 产物 dist/promptgo.pyz + dist/web/
python dist/promptgo.pyz --port 7317 --open
```

产物约 49 KB，只用标准库，无签名问题、不会被 WDAC 拦截；代价是目标机需 Python 3.11+，
且 `dist/web/` 必须与 `.pyz` 同级（`bundle_root()` 按归档所在目录解析静态资源）。

**形态 B：单文件 exe（目标机无 Python 时）**

```bash
pip install pyinstaller   # 仅打包机需要
python build.py           # 产物 dist/promptgo(.exe)，实测 7.7 MB
python build.py --clean   # 先清理 build/ 与 dist/
```

`build.py` 会按平台自动选择 `--add-data` 的分隔符（Windows 用 `;`，其他用 `:`），
并把 `web/` 打进包内。等价的手写命令（分隔符需自己改）：

```bash
pyinstaller --onefile --noconfirm -n promptgo --add-data "web;web" server/app.py
```

静态资源根由 `app.bundle_root()` 统一解析，兼容三种形态：源码运行取项目根、
PyInstaller 打包取 `sys._MEIPASS` 解包目录、zipapp 取归档所在目录。

> 说明：部分企业机器启用了应用控制策略（WDAC / AppLocker），exe 会被直接拦截无法启动。
> 此时改用形态 A（`python server/app.py`）分发，或由 IT 为产物放行。

## 常见问题

**组件提示「未连接到本地服务」**：先确认 `http://127.0.0.1:7317/v1/health` 可访问；
若端口被占用，服务会自动顺延，请在组件上加 `endpoint="http://127.0.0.1:7318"`。

**端口顺延是怎么判定的**：按「是否真的有人在监听」判断（连接探测），而不是「能否 bind」——
Windows 允许同端口重复绑定，按 bind 判定会让第二个实例抢占同一端口。实测双实例：先起
`--port 7433` 的实例，再起一个同端口实例，第二个会落到 `7434`；若加 `--no-fallback`，
第二个直接以退出码 1 结束并提示端口已被占用。

**页面在 `file://` 下打开**：可用，跨域来源为 `null` 时服务默认允许；生产环境建议用
`--allow-origin` 收敛白名单。

**会不会把我的内容传到网上？** 不会。服务仅监听回环地址，引擎是本地规则运算，
无任何出网请求（可用抓包工具验证）。
