# PromptGo 开发进度审计

> 审计时间：2026-11-11 · 基线：工作区 `c:/Users/1/CodeBuddy/20261110153339`
> 方法：通读 `server/`、`web/`、`tests/`、`tools/`、文档；实跑测试与基准；对未覆盖路径做手工冒烟（CLI 启动、真实接口、socket 语义）。

## 0. 结论摘要

- **主体功能已全部落地**：引擎（分析 → 模板 → 渲染 → 评分）、HTTP 层、可嵌入组件、演示页、两种分发形态均可用。
- **交付形态已定：形态 A（源码 + `start.bat` + Python 3.11+）**。exe 被本机 WDAC 拦截，形态 B 降级为可选附件。
- **测试 192/192 通过**（含 41 个协议用例、7 个前端用例与真实 socket 端到端）；**GitHub Actions 四个组合全绿**（run 43195232447，ubuntu/windows × Python 3.11/3.13）。
- **没有 P0 阻断项**；P1 系列（端口顺延 / exe 过期 / 服务旧代码）与 P2-1~P2-14、P3-1~P3-8 均已处理。
- **前端已有最小冒烟**（SSE 分帧 / `target` 回填 / JSON 回退 / 章节归一化），组件体积 38.8 / **44 KB（88.3%）**，余量 5,278 B（预算于 11-12 上调，换取后续 UI 空间）。
- **v1.1.0 已发布（2026-11-13）**：`engine.__version__` 与组件 `VERSION` 双处同步，192 用例全绿；形态 A 实测 health `v1.1.0` + 组件 39,778 B + 演示页 200；形态 C `.pyz` 实测 `--version` 与 health 200；形态 B exe 8,069,873 B 仍被 WDAC 拦截，仅归档校验（`web/` 3 文件 + 5 个引擎模块）。推送 `main` 与 tag `v1.1.0`（commit `700f5da`），CI run 43387050837 四组合 success。
- 代码量（非空行）：后端 2,168 行、前端 770 行、Python 测试 1,621 行（含 `run.py`）、前端冒烟 238 行、工具 274 行、文档 676 行（含本报告与 README），合计 5,747 行。

## 1. 已完成的功能与模块

| # | 模块 | 已完成内容 | 验证证据 |
| --- | --- | --- | --- |
| 1 | 分析器 `analyzer.py` | 语言/意图(12)/领域(22)/渠道(55)/语气(63) 识别；篇幅/格式/受众约束抽取；缺失槽位（背景按「长度 + 信息量」判定）；模糊表述与风险；主题/实体/关键词；长词优先+不重叠匹配；同义改写与英文别名 | `tests/test_engine.py` 45 例；`tests/test_templates.py` 26 例 |
| 2 | 模板库 `templates.py` | 12 套意图模板（角色/步骤/输出契约/自检，中英双语）+ 12 套成品骨架（62 条）+ 22 条领域语境 + 6 模式提示 | 覆盖度测试逐个字段断言，漏配即失败 |
| 3 | 渲染器 `renderer.py` | 8 段标准渲染（light 4 / deep 9）、骨架注入、concise 跳过骨架、markdown/text 双格式 | `test_outline_*`、`test_text_format`、渲染一致性用例 |
| 4 | 评分器 `scorer.py` | 5 维启发式评分（结构性含成品骨架 +12，结构项上限 80 留余量）+ 前后对比 + 等级文案 + `skeleton` 标记 | `TestScore` 3 例 + `TestSkeletonScoring` 4 例 |
| 5 | 流水线 `pipeline.py` | JSON 与 SSE 双链路共用纯函数管线；阶段事件；输入归一化与截断 | `test_stream_equals_json_for_all_formats`（2 格式 × 2 模式逐字符比对） |
| 6 | HTTP 层 `http_layer.py` | 路由、CORS 白名单、`X-PE-Token`、限流（默认 90/min，可配）、请求体与字符上限（可配）、SSE 分帧、静态资源越界防护、9 个错误码 | `test_http.py` 26 例 + `test_http_errors.py` 15 例（真实 socket，含配置注入） |
| 7 | 组件 `prompt-enhancer.js` | Shadow DOM、bubble/inline、`target` 读取与回填、手工 SSE 分帧、无流回退 JSON、草稿、评分条、chips（意图/领域/约束/风险/待确认）、**章节导航（消费 `plan.sections`，点击滚动定位）**、`PromptEnhancer` API | 冒烟覆盖分帧/回填/回退/归一化；UI 绘制人工验证 |
| 8 | 演示页 `web/demo/` | 宿主监听示例、事件总线、样例填充、评分仪表、**渠道/语气/章节/待确认展示，识别维度由 `/v1/meta` 驱动** | 人工验证 + 静态断言 |
| 9 | 分发 | `start.bat`（优先 `py -3`）、`start.sh`、`build.py`（onefile + 自动分隔符）、`bundle_root()` 三形态 | `test_packaging.py` 5 例；手工 CLI 冒烟通过 |
| 10 | 质量工程 | 192 用例 / 11 文件；`tests/run.py --strict`（跳过即失败）；GitHub Actions 双平台 × 双 Python（已在真实仓库跑绿）；`tools/expansion_bench.py` 旧词表快照对比 | 本地 `--strict` → 192 通过 / 0 跳过；CI run 43195232447 四组合 success；基准输出 50%→100%（34 条） |
| 11 | 文档 | README、ARCHITECTURE（选型/协议/性能/边界）、TASK2-REVIEW（历史评审） | 与本轮实测数字已对齐 |

实测指标：组件 `38.8 KB / gzip 11.5 KB`；320 字增强 `1.27 ms`（analyze 0.92 ms）；7500 字输入输出 1068 字符；CLI 启动 + `/v1/enhance`（deep，9 段，1053 字符）冒烟通过。

## 2. 待完成任务清单（按优先级）

### P0 · 阻断交付

无。

### P1 · 交付前必须处理

| ID | 事项 | 当前状态 | 影响范围 |
| --- | --- | --- | --- |
| P1-1 | ~~**端口顺延在 Windows 上不生效**~~ **已修复** | 修复方式：占用判定从「能否 bind」改为「**是否真的有人在监听**」（连接探测，250 ms 超时，仅 `ConnectionRefusedError` 视为空闲）；`build_server` 在探测与绑定之间发生竞态时继续换端口；`--no-fallback` 先探测再绑定，占用时以退出码 1 明确失败。服务端仍保留 `allow_reuse_address` 以保证快速重启。验证：`tests/test_port.py` 9 例；双实例实测（7433 起、同端口再起 → 落到 7434，两个实例 health 均 200）；占用端口 + `--no-fallback` → 退出码 1 | 原影响：README/ARCHITECTURE 的顺延承诺失效、两服务争抢同一端口、`--no-fallback` 失去意义。现均解除 |
| P1-2 | ~~**`dist/promptgo.exe` 已过期**~~ **已重新打包，并改为形态 A 交付** | `python -m pip install pyinstaller`（6.22.3）→ `py build.py --clean` → `dist/promptgo.exe` **8,069,873 B ≈ 7.7 MB**（包内 `web/` 3 个文件与 5 个引擎模块均已校验）。因本机 WDAC 拦截未签名 exe，**交付形态最终定为 A**：`start.bat` + 源码 + Python 3.11+，已实测 `start.bat 7451` → health 200 → 组件 39,778 B；exe 仅作可选附件 | 交付路径已确定且可验证；形态 B 在无应用控制策略的机器上仍可按 `build.py` 复现 |
| P1-3 | ~~**本机 7317 端口跑的是旧代码**~~ **已重启** | 原 PID 83476（python 3.14.3，09:51 启动）已停止，新实例 PID 118404（同解释器、同参数）。重启前实测 `渗透测试` → `general/通用`（旧）；重启后 → `security/安全与合规`、8 段、含输出骨架、935 字符，`server.err.log` 为空。日志改为重定向到 `server.log` / `server.err.log`（隐藏窗口运行） | 验收环境已与新代码一致 |

### P2 · 功能与质量缺口

| ID | 事项 | 当前状态 | 影响范围 |
| --- | --- | --- | --- |
| P2-1 | ~~前端零自动化测试~~ **已修复（最小冒烟）** | 组件抽出 6 个纯函数（`parseFrame` / `drainFrames` / `writeTarget` / `supportsStream` / `readJSONResponse` / `sectionList`）并从 `PromptEnhancer._internals` 暴露；`tests/frontend/smoke.mjs` 用 `node:vm` + 最小 DOM 桩加载单文件（无 jsdom），19 项断言 + 1 项真实接口端到端全部通过；`tests/test_frontend.py` 6 例（含体积预算、导航容器、演示页维度）纳入 `tests/run.py`，无 Node 时跳过。**仍未覆盖**：Shadow DOM 渲染、chips/Markdown 绘制、复制回退、导航点击后的滚动行为 | 前端高风险三块（分帧 / 回填 / JSON 回退）与章节归一化已有回归保护；纯 UI 绘制与滚动仍是人工验证 |
| P2-2 | ~~组件体积余量不足~~ **已处理（压缩 + 预算上调）** | 先做样式压缩：内联 CSS 改单行规则、合并重复 `:host`、`rgba()` 转十六进制透明度、`border` 收敛为 `--pg-bd`、去非关键过渡、`_els` 用 `q` 别名、chips 复用容器，回收约 1.5 KB（导航占用约 1.6 KB，净增 79 B）。11-12 将预算口径由 40 KB 上调至 **44 KB**：当前 38.8 KB（39,778 B，含「含骨架」chip 与「另有 N 项未展示」提示）= **88.3%**，gzip 11.5 KB，余量 **5,278 B** | 后续 UI 有 5.2 KB 空间；`SIZE_BUDGET` 与演示页标签由用例 `test_demo_budget_tag_matches_budget` 锁定一致 |
| P2-3 | ~~HTTP 错误分支未覆盖~~ **已修复** | 新增 `tests/test_http_errors.py`（11 例）：429（REST 与 stream 两条入口、按来源隔离、窗口恢复）、411（JSON 与 stream 两种请求体为空）、SSE 内 `event: error`（`EnhanceError` 与任意异常两路）、500 `ENGINE_ERROR`（不泄露堆栈）、以及「收口 500 后 EnhanceError 仍按自带状态返回」。实现零改动，缺陷是覆盖缺口而非行为错误 | 已解除；顺带确认 error 帧是完整 SSE 帧（前端手工分帧不会卡住） |
| P2-4 | ~~`app.py` CLI 分支覆盖不全~~ **已修复** | 新增 `tests/test_cli.py`（18 例）：`--token` 未给值随机生成（16 字符 url-safe、两次不同）/给值沿用、`banner()` 与 `startup_lines()` 文案、令牌提示、非回环警告、`--open` 延迟调度（注入 timer，验证 0.6 s 与 demo URL）、`main()` 在 Ctrl+C 与正常返回下均返回 0 且关闭 server。为此把启动打印抽成纯函数 `banner()` / `startup_lines()`，并新增 `_resolve_token()` / `_schedule_open()` | 已解除。顺带修掉一个真实崩溃：启动文案里的 U+26A0「⚠」在 cp936 控制台（`--host 0.0.0.0`）会抛 `UnicodeEncodeError`，现改为「【警告】」并加 GBK 可编码断言 |
| P2-5 | ~~`/v1/meta` 不暴露识别清单~~ **已修复** | `engine.META` 新增 `intents`(12，`id/label/label_en`)、`domains`(23，含 `general`)、`channels`(36 标签)、`tones`(41 标签)，全部由词典在模块加载时生成（同义拼写自动去重），`general` 固定收尾；新增 `tests/test_meta.py` 12 例（零漂移、去重、模板/骨架一致性、体积预算）与 1 条 HTTP 断言 | 已解除；META 体积 6.7 KB，宿主可据此渲染下拉/筛选而无需硬编码 |
| P2-6 | ~~`plan` 事件的 `sections` 未被组件使用~~ **已修复** | 结果区新增 `.pg-nav`：`plan` 事件到来即渲染章节按钮，点击按「sections 下标 == 正文标题下标」定位滚动（实测 struct/light/deep/concise 四个组合，章节数与 `## ` 标题数分别为 8/4/9/5 且顺序完全一致）；JSON 回退路径用 `blocks` 补齐导航；`pe:result` 事件详情新增 `sections` 字段供宿主使用 | 章节结构从文本内部变为可点击导航；归一化逻辑有 3 项冒烟断言守护 |
| P2-7 | ~~演示页未展示新增维度~~ **已修复** | 侧栏 kv 增加 渠道/语气/章节/待确认四行（渠道与语气按 `constraints.kind` 取值，可能命中多个；待确认取 `analysis.missing` 数量），并新增一行由 `/v1/meta` 驱动的维度概览（意图 12 / 领域 23 / 渠道 36 / 语气 41）。实测营销样例渠道=小红书、语气=口语化 | 演示与验收时新识别能力可见；用例 `test_demo_shows_channels_and_tones` 守护四个锚点与 `/v1/meta` 调用 |
| P2-8 | ~~zipapp 形态只有代码支持~~ **已修复** | `build.py` 新增 `--zipapp`：用标准库 `zipfile` 把 `server/` 打成 `dist/promptgo.pyz`（实测 49 KB，归档含 `__main__.py` + 8 个模块，不含 `__pycache__`），并把 `web/` 复制到同级；`--clean` 一并清理。实测 `python dist/promptgo.pyz --version` 正常，起服务后 health 200、`/prompt-enhancer.js` 39,778 B、演示页 200 | 被 WDAC 拦截的机器有了可用形态；3 条用例守护归档布局、静态资源同级与运行期 import 完整性 |
| P2-9 | ~~骨架与评分脱钩~~ **已修复** | 根因不是「没加权重」，而是结构性维度**过早饱和**：原公式 4 个标题即拿满 40 分，加上列表/编号封顶后结构项恒为 97，骨架再多条也不涨。改为：标题 `min(26, 6×n)`、列表 `min(18, 2×n)`、编号 `min(10, 2×n)`、空行 4，**骨架命中再 +12**，结构项上限降到 80 留出余量；新增 `_has_skeleton()` 要求标记后至少 2 条骨架条目才算数，`score.skeleton` 随结果返回、`compare()` 一并暴露，前端评分区显示「含骨架」chip。实测同一素材（营销样例）：带骨架 83 / 去骨架 81（结构项 80 / 68），总分严格更高；营销样例整体由 86 变为 83（结构项不再虚高）。**仍未解决**：`standard` 与 `deep` 仍同为 83——深度增加的是章节数与风险段，质量维度已封顶，不构成「更好」，故不强行拉开 | 4 条用例守护（余量、严格更高、空标不算分、标记透出）；架构文档「已知边界」中「评分器不计骨架分」的说法已同步修正 |
| P2-10 | ~~渠道/语气最多取 2 个~~ **已修复** | 保留上限由 2 提到 **4**（`MAX_MULTI`），并把 `_match_labels` 改为扫描全部命中后在调用方切片，从而能统计「被丢弃几条」；`Analysis.truncated` 记录 `{kind: 丢弃数}` 并随 `analysis` 返回。前端 chips 增加「另有 N 项未展示」，演示页渠道/语气行追加「（另有 N 项）」。实测「小红书/抖音/知乎/微博/B站/微信公众号 + 5 种语气」：保留 4+4，`truncated={tone:1, channel:2}` | 多渠道投放不再漏配且可追溯；4 条引擎用例 + 1 条接口用例 + 1 条冒烟断言守护 |
| P2-11 | ~~词典匹配的固有局限~~ **已修复（词表扩容）** | 新增 `DOMAIN_SYNONYMS`（22 领域 +153 条同义改写与英文表述，如 社群/裂变→营销、快递/仓库→物流、solar/battery→新能源、kubernetes/database→技术）；渠道补平台别称与英文写法（rednote/douyin/wechat/press release/podcast 等，38→55 词条），语气补同义与英文（风趣/简练/严肃、serious/friendly/warm 等，47→63 词条）。别名只指向既有标签，`/v1/meta` 标签数保持 36/41 不变。加词约束：只收本行业独有词、英文 ≥4 字符且不构成其他单词子串（避免 `api`→`rapid` 这类误命中）、不改 `DOMAIN_PRIORITY` | 基准语料从 22 条扩到 34 条（新增 12 条全是旧词表漏判样本），领域准确率 50%→100%；17 条中文 + 11 条英文 + 渠道/语气别名共 4 条用例守护，任何「新词抢走旧领域」都会失败；词表外改写（如「老客池」）仍会漏判，已写入架构文档「已知边界」 |
| P2-12 | ~~配置不可调~~ **已修复** | 三个上限改为参数注入：`normalize/enhance/stream` 接受 `max_chars`，`AppConfig` 增加 `max_body` / `rate_limit` / `max_chars`，由 `build_parser()` 的 `--max-body`(KB) / `--rate-limit` / `--max-chars` 传入，非正数直接拒绝；新增 `--version`；`/v1/health` 与 `/v1/meta` 如实返回当前上限。实测 `--max-chars 1200 --max-body 8 --rate-limit 5`：health=1200、meta=1200、10 KB 请求体返回 413 | 内网多机可各自调参而无需改代码；9 条用例守护默认值、透传、非正数拒绝与接口一致性 |
| P2-13 | ~~`_find_missing` 的 `context` 判定粗糙~~ **已修复** | 判定从「字符数 > 120」改为「长度 + 信息量」，单点收敛到 `_has_context()`：去空白后 ≥80 字符；中文要求去重字符 ≥40 且去重率 ≥0.30；英文要求 ≥25 词且去重词占比 ≥0.45（英语字母表有限，只能按词算）。实测：97 字符的真实产品背景判为「已给」；144 字符的复读句、157 字符的「复读 + 一句需求」均判为「未给」并继续追问背景 | 长而空洞的输入不再跳过最有价值的背景追问；阈值可解释、可回归，7 条用例守护（单元判定 + 端到端） |
| P2-14 | ~~413 偶发「客户端收不到响应」~~ **已修复** | 大请求体时 `_read_json` 判定超限后直接抛 413，未读的请求体留在缓冲区就关闭连接；Windows 下内核发 RST，把刚写出的响应一起丢掉（全量测试偶发 1 次「未收到任何响应字节」）。新增 `_discard_body()`：回 413 前按 Content-Length 排空（上限 1 MB、1 s 超时），既不拖住工作线程也不会再触发 RST。连续复跑该用例 10 次稳定通过 | 413 响应在 Windows + 大请求体下可稳定送达；测试不再出现与环境相关的红色 |

### P3 · 文档与工程化

| ID | 事项 | 当前状态 | 影响范围 |
| --- | --- | --- | --- |
| P3-1 | ~~Python 版本口径不一致~~ **已修复** | README 此前已改为 3.11+，本轮把 `ARCHITECTURE.md` §1 的「Python 3.9+」同步为 3.11+；全仓搜索无 `3.9+` 残留，口径统一为「3.11+，实测 3.12/3.13/3.14」 | 用户不会再按低版本进入未验证路径；3.9/3.10 未实测已如实标注 |
| P3-2 | ~~`tools/` 未在 ARCHITECTURE 目录结构中体现~~ **已修复** | ARCHITECTURE §5.2 组件结构图新增「辅助工具（tools/，不在服务进程内）」方框与 ⑪ 条目，模块表补一行说明（旧词表快照 vs 当前词表逐条召回对比、离线运行、扩词后跑一次防退化）；与 §0 质量保障行、§8 已知边界中对 `tools/expansion_bench.py` 的引用形成闭环 | 架构文档与仓库结构一致；读者不会再以为 `tools/` 是运行时依赖 |
| P3-3 | ~~`docs/TASK2-REVIEW.md` 是历史快照~~ **已修复** | 文首加「历史文档（归档）」提示，说明当时的 12 项缺陷 / 46 用例 / 37.1 KB 不代表现状，并指向 `PROGRESS-AUDIT.md` | 不会再被当作当前状态引用 |
| P3-4 | ~~无 CI~~ **已实跑并转绿** | 首次真实运行（run 43192024927，commit `9ddad8f`）：ubuntu 3.11/3.13 绿，windows 3.11/3.13 红，失败步骤均为「全量测试」。根因是 en-US Windows 控制台默认 **cp1252**，`tests/run.py` 打印中文摘要抛 `UnicodeEncodeError`——用例全过但进程非零退出；本地用 `PYTHONIOENCODING=cp1252` 可稳定复现。修复：`run.py` 与 `server/app.py` 启动即把 stdout/stderr 强制 UTF-8，workflow 增加 `PYTHONIOENCODING`/`PYTHONUTF8` 兜底，并补 2 条子进程用例复现该环境。修复后 run 43195232447（commit `8e544bc`）四组合全绿 | 回归已由人工转为「提交即触发」；`--strict` 同时堵住了「跳过即假绿」 |
| P3-5 | ~~版本号三处重复~~ **已修复** | 唯一来源收敛为 `engine.__version__`：`http_layer` 改为 `from engine import __version__ as VERSION`（不再自持字面量），组件保持字面量（静态单文件无法 import），由 `tests/test_packaging.py` 三条用例守护一致性；演示页页脚改为 `/v1/health` 回填，消灭第四处硬编码 | 发版只需改一处；任一环节漏改即测试失败 |
| P3-6 | ~~`.gitignore` 过宽~~ **已修复** | 删除 `*.png`、`*.txt` 两条，保留 `*.log`、`*.tmp` 与打包产物规则 | 测试夹具与文档配图不再被静默忽略 |
| P3-7 | ~~静态资源 MIME 缺口~~ **已修复** | `CONTENT_TYPES` 补 `.png`（image/png）、`.ico`（image/x-icon）、`.woff2`（font/woff2）、`.woff`（font/woff）；新增 `StaticAssetMimeTestCase` 真实请求校验返回头 | 图片/字体不再以 `octet-stream` 下发 |
| P3-8 | ~~工作区残留产物~~ **已修复** | 删除 `build/`、`dist/`（含 7.7 MB `promptgo.exe` 与 spec）、`server.log`、`server.err.log`；exe 可随时用 `py build.py` 重新生成 | 交付包不再携带构建噪声；仓库根目录只剩源码、文档与脚本 |

## 3. 测试状态

- **通过**：192/192（`test_engine` 45、`test_templates` 26、`test_expansion` 14、`test_meta` 12、`test_port` 9、`test_cli` 25、`test_http` 26、`test_http_errors` 15、`test_frontend` 7、`test_packaging` 13）。
- **失败**：无。
- **未覆盖（据代码走查，非失败）**：前端 Shadow DOM 渲染与绘制（chips/Markdown/复制回退）；真实 zipapp；Python 3.9/3.10 兼容性；macOS/Linux 下的端口顺延。
- **前端冒烟说明**：`tests/frontend/smoke.mjs` 需 Node（本机用 IDE 托管的 22.22.2），未安装时 Python 侧自动跳过，不会误报失败。
- **strict 模式**：CI 走 `python tests/run.py --strict`，任何 `skip` 都按失败处理；本机模拟无 Node 时输出 3 条跳过并退出码 1，证明「假绿」已被堵住。

## 4. 建议的下一步顺序

1. ~~修 P1-1~~ **已完成**：占用判定改为连接探测 + 绑定时竞态重试，`tests/test_port.py` 9 例守护，双实例实测通过。
2. ~~补 P2-4~~ **已完成**：`tests/test_cli.py` 18 例覆盖令牌、启动文案、`--open`、退出码；并修掉「⚠ 在 cp936 控制台崩溃」的真实缺陷。
3. ~~补 P2-3~~ **已完成**：`tests/test_http_errors.py` 11 例覆盖 429/411/SSE error/500，实现零改动。
4. ~~重启本机 7317 服务~~ **已完成**：旧 PID 83476 停止，新 PID 118404；实测 `渗透测试` 由 `通用` 变为 `安全与合规`。
5. ~~重打包~~ **已完成**：PyInstaller 6.22.3 → 7.7 MB，包内容校验通过；运行仍被 WDAC 拦截（属环境限制）。
6. ~~交付形态二选一~~ **已决策**：按形态 A 交付（`start.bat` + 源码 + Python 3.11+）；已实测 `start.bat 7451` → health 200 → 组件资源正常返回（当前 39,778 B）。
7. ~~补前端最小冒烟~~ **已完成**：`tests/frontend/smoke.mjs`（16 断言 + 真实接口）与 `tests/test_frontend.py`（4 例，含体积预算）。
8. ~~`/v1/meta` 暴露清单~~ **已完成**：`intents/domains/channels/tones` 由词典生成，`tests/test_meta.py` 12 例守护零漂移。
9. ~~补体验（P2-6/7）~~ **已完成**：组件新增章节导航并消费 `plan.sections`；演示页展示渠道/语气/章节/待确认，维度概览由 `/v1/meta` 驱动。
10. ~~组件瘦身（P2-2）~~ **已完成**：CSS 内联单行化 + 变量收敛 + JS 微优化，回收约 1.5 KB；11-12 预算上调至 44 KB，当前 39,778 B，余量 5,278 B。
11. ~~口径与交付一致性（第一批）~~ **已完成**：Python 版本口径统一（P3-1）、版本号单一来源（P3-5）、MIME 补齐（P3-7）、忽略规则收紧（P3-6）、历史文档标注（P3-3）、工作区清理（P3-8）；新增 6 条守护用例。
12. ~~补 CI（P3-4）~~ **已完成**：`.github/workflows/ci.yml` 双平台 × 双 Python，Node 22 强制安装，`--strict` 禁止跳过；本地已复现「无 Node 即失败」。
13. ~~评分与骨架挂钩（P2-9）~~ **已完成**：结构性维度改为「不饱和 + 骨架显式加分」，带骨架严格高于去骨架（83 / 81），`score.skeleton` 透出到接口与 UI。
14. ~~配置可调与 `--version`（P2-12）~~、~~zipapp 打包（P2-8）~~ **均已完成**：三个上限经 CLI 注入并透出到 health/meta；`python build.py --zipapp` 产出 49 KB 可运行 `.pyz`。
15. ~~**P3-2**~~ **已完成**：ARCHITECTURE §5.2 结构图补「辅助工具（tools/）」方框与 ⑪ 条目，模块表同步。
16. ~~**P2-13**~~ **已完成**：`context` 判定改为「长度 + 信息量」（`_has_context()`），复读式长文本不再被误判为已给背景；7 条用例守护。
17. ~~**P2-11**~~ **已完成**：领域补 153 条同义/英文词，渠道 38→55、语气 47→63 词条；基准语料扩到 34 条，领域准确率 50%→100%，4 条用例 + 基准门槛防领域漂移。
18. ~~**P2-14**~~ **已完成**：413 先排空请求体再响应，消除 Windows 下 RST 导致的空响应；连续 10 次复跑稳定。
19. ~~**发版 v1.1.0**~~ **已完成**：版本号 1.0.0 → 1.1.0（`engine.__version__` + 组件 `VERSION`）→ 192 用例全绿 → `py build.py --clean`（exe 8,069,873 B）与 `--zipapp`（.pyz 49,686 B）→ 形态 A `start.bat 7451` 与形态 C `py dist/promptgo.pyz --version` 均实测通过。exe 仍被 WDAC 拦截，属环境限制。已推送 `main` + tag `v1.1.0`，CI 四组合 success（run 43387050837）。
