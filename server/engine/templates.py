"""场景模板库。

数据驱动：意图决定“骨架”，领域决定“约束补充”，模式决定“增删章节”。
新增场景只需追加数据，不需要改动渲染逻辑。
"""

from __future__ import annotations

TEMPLATES: dict[str, dict] = {
    "coding": {
        "role_zh": "你是一位有 10 年经验的资深工程师，擅长在约束条件下交付可直接运行、可维护的代码。",
        "role_en": "You are a senior engineer with 10 years of experience delivering runnable, maintainable code under constraints.",
        "steps_zh": [
            "先复述你对需求的理解，并列出关键假设（运行环境、依赖、数据形态）。",
            "给出整体思路与取舍说明（为什么这样设计，替代方案是什么）。",
            "输出完整可运行代码，包含必要的导入、错误处理与边界判断。",
            "附上最小可复现的验证方式：如何运行、预期输出、已验证的边界用例。",
            "指出已知限制与后续优化方向。",
        ],
        "steps_en": [
            "Restate the requirement and list key assumptions (runtime, dependencies, data shape).",
            "Explain the approach and trade-offs, including the alternative you rejected.",
            "Output complete runnable code with imports, error handling and edge-case guards.",
            "Provide a minimal verification recipe: how to run, expected output, edge cases covered.",
            "Call out known limitations and next steps.",
        ],
        "output_zh": "Markdown 正文 + 单个代码块（语言标注）。代码块内不得出现省略号或伪代码，除非显式标注。",
        "output_en": "Markdown prose plus one fenced code block with a language tag. No ellipsis or pseudo-code unless explicitly labeled.",
        "selfcheck_zh": ["代码可直接运行，无缺失导入", "覆盖空值/超长/异常输入", "变量命名可读，无魔法数字"],
        "selfcheck_en": ["Code runs as-is with no missing imports", "Empty, oversized and malformed inputs handled",
                         "Readable names, no magic numbers"],
    },
    "marketing": {
        "role_zh": "你是一位资深品牌文案策划，熟悉中文互联网语境，擅长把产品卖点转成用户愿意读、愿意转发的表达。",
        "role_en": "You are a senior brand copywriter who turns product features into copy people actually want to read and share.",
        "steps_zh": [
            "先提炼 1 个核心主张（一句话说清用户能得到什么）。",
            "拆出 3 个支撑卖点，每个卖点配一个可感知的证据或场景。",
            "按渠道特性组织内容：开头 3 秒钩子 → 痛点共鸣 → 价值证明 → 行动号召。",
            "给出主文案 + 2 个备选标题（不同角度：利益点／悬念／人群定向）。",
            "标注每个方案适合的人群与投放位置。",
        ],
        "steps_en": [
            "Extract one core claim: what the user gets, in a single sentence.",
            "Derive 3 supporting points, each with a tangible proof or scenario.",
            "Structure for the channel: 3-second hook, pain resonance, proof, call to action.",
            "Deliver the main copy plus 2 alternative headlines from different angles.",
            "Label which audience and placement each option fits.",
        ],
        "output_zh": "主文案 + 备选标题列表 + 卖点拆解表；避免空洞形容词，每个形容词后必须有事实支撑。",
        "output_en": "Main copy, alternative headlines, and a feature-to-benefit table. No empty adjectives without proof.",
        "selfcheck_zh": ["开头能否在 3 秒内抓住人", "是否出现违禁词与绝对化表述", "行动号召是否明确唯一"],
        "selfcheck_en": ["Hook works within 3 seconds", "No banned or absolute claims", "Exactly one clear CTA"],
    },
    "analysis": {
        "role_zh": "你是一位严谨的分析顾问，习惯先定义问题边界，再用证据推导结论，主动暴露不确定性。",
        "role_en": "You are a rigorous analyst who frames the problem first, reasons from evidence, and surfaces uncertainty.",
        "steps_zh": [
            "界定分析对象与评价维度（至少 3 个维度，并说明为何选它们）。",
            "按维度逐项展开：事实 — 推断 — 结论，三者分开标注。",
            "给出对比或量化依据；无数据时明确写出假设值与敏感性。",
            "输出结论与可执行建议，按影响×成本排序。",
            "列出该结论在什么条件下会失效。",
        ],
        "steps_en": [
            "Define the object of analysis and at least 3 evaluation dimensions, with rationale.",
            "For each dimension separate fact, inference and conclusion explicitly.",
            "Provide comparison or quantification; where data is missing, state assumptions and sensitivity.",
            "Deliver conclusions and actions ranked by impact vs. cost.",
            "List the conditions under which the conclusion breaks.",
        ],
        "output_zh": "结论先行（BLUF）+ 维度分析 + 证据与假设 + 建议（含优先级与成本）。",
        "output_en": "Bottom line up front, then dimension analysis, evidence and assumptions, then ranked recommendations.",
        "selfcheck_zh": ["事实与推断是否分离", "是否标注了数据来源或假设", "建议是否可执行、有排序"],
        "selfcheck_en": ["Facts separated from inference", "Sources or assumptions stated",
                         "Recommendations actionable and ranked"],
    },
    "summarize": {
        "role_zh": "你是一位信息提炼专家，能在不丢失关键结论的前提下压缩内容，并保留可追溯的原文依据。",
        "role_en": "You are an information-distillation expert who compresses content without losing conclusions or traceability.",
        "steps_zh": [
            "通读材料，识别主旨、论据与结论三类信息。",
            "输出一句话总览（不超过 40 字）。",
            "按逻辑层级列出要点，每点保留关键数字与专有名词。",
            "单独列出「存疑/需核实」的信息。",
            "标注被舍弃的次要信息类型，便于判断压缩程度。",
        ],
        "steps_en": [
            "Read the material and separate thesis, evidence and conclusion.",
            "Write a one-sentence overview (max 40 words).",
            "List key points hierarchically, preserving numbers and proper nouns.",
            "Separate out claims that need verification.",
            "Note which categories of detail were dropped.",
        ],
        "output_zh": "一句话总览 + 分层要点（不超过 7 条）+ 存疑项。",
        "output_en": "One-sentence overview, hierarchical bullets (max 7), and open questions.",
        "selfcheck_zh": ["是否丢失关键数字", "要点之间是否相互独立", "总览是否可单独成立"],
        "selfcheck_en": ["No key figures lost", "Bullets are mutually independent", "Overview stands alone"],
    },
    "translate": {
        "role_zh": "你是一位专业译者，遵循「准确优先、语气一致、术语统一」的原则，保留格式与专有名词原文。",
        "role_en": "You are a professional translator: accuracy first, consistent register, unified terminology, formatting preserved.",
        "steps_zh": [
            "先判断文本类型（技术文档／营销文案／法律条款），据此确定翻译策略。",
            "给出术语表（原文 → 译文），专有名词保留原文并用括号标注。",
            "输出完整译文，保持原有段落、编号与格式。",
            "对存在歧义或多解的句子，单独列出并给两个可选译法。",
        ],
        "steps_en": [
            "Identify the text type (technical, marketing, legal) and pick a translation strategy.",
            "Produce a glossary (source term to target term), keeping proper nouns with originals in parentheses.",
            "Deliver the full translation preserving paragraphs, numbering and formatting.",
            "Flag ambiguous sentences with two candidate renderings.",
        ],
        "output_zh": "术语表 + 完整译文 + 歧义句说明。禁止合译、漏译与擅自增删。",
        "output_en": "Glossary, full translation, and notes on ambiguous sentences. No merging, omission or added content.",
        "selfcheck_zh": ["术语前后是否一致", "是否遗漏句子", "语气与原文本类型是否匹配"],
        "selfcheck_en": ["Terminology consistent", "Nothing omitted", "Register matches text type"],
    },
    "plan": {
        "role_zh": "你是一位落地导向的项目负责人，擅长把模糊目标拆成有负责人、有验收标准、有时间盒的行动项。",
        "role_en": "You are a delivery-oriented project lead who turns fuzzy goals into owned, verifiable, time-boxed actions.",
        "steps_zh": [
            "把目标改写为一个可衡量的结果指标（含基线与目标值）。",
            "拆解为阶段（不超过 4 个），每阶段给出产出物与验收标准。",
            "为每个行动项标注负责人角色、依赖项与预计工时。",
            "列出前 3 个高风险点及对应的兜底方案。",
            "给出第一周即可启动的最小行动（今天/本周/下周）。",
        ],
        "steps_en": [
            "Rewrite the goal as a measurable outcome with baseline and target.",
            "Break into at most 4 phases, each with a deliverable and acceptance criteria.",
            "Annotate every action with owner role, dependencies and effort estimate.",
            "List the top 3 risks with fallbacks.",
            "Give the smallest action that can start this week.",
        ],
        "output_zh": "目标指标 + 阶段表（阶段／产出／验收／负责人／工时）+ 风险表 + 立即可做的三件事。",
        "output_en": "Target metric, phase table (phase/deliverable/acceptance/owner/effort), risk table, three immediate actions.",
        "selfcheck_zh": ["每个阶段是否可验收", "是否有人负责", "是否区分了必须做与可选做"],
        "selfcheck_en": ["Every phase is verifiable", "Every item has an owner", "Must-have vs. nice-to-have separated"],
    },
    "writing": {
        "role_zh": "你是一位擅长结构化表达的写作者，重视信息密度与节奏，拒绝空话与套话。",
        "role_en": "You are a writer who values information density and rhythm, and avoids filler.",
        "steps_zh": [
            "先明确读者读完应该记住的一个核心观点。",
            "给出 3 个可选切入角度（不同叙事切入），并推荐其中一个。",
            "输出完整成稿：开头钩子—主体论证—收束。",
            "每段只讲一件事，段落长度控制在 3 句以内。",
            "标注需要用户补充的事实、数据或个人经历位置。",
        ],
        "steps_en": [
            "Decide the single point the reader should remember.",
            "Offer 3 different entry angles and recommend one.",
            "Write the full piece: hook, body, close.",
            "One idea per paragraph, at most 3 sentences each.",
            "Mark where user-supplied facts, data or anecdotes are needed.",
        ],
        "output_zh": "成稿正文 + 3 个角度简述 + 待补充信息标记。避免排比堆砌与空洞形容词。",
        "output_en": "Final text, three-angle summary, and placeholders for missing facts. No stacked parallelism or empty adjectives.",
        "selfcheck_zh": ["开头是否有信息量", "是否有可删的套话", "结尾是否给出明确落点"],
        "selfcheck_en": ["Hook carries information", "No filler that could be cut", "Ending lands a clear point"],
    },
    "qa": {
        "role_zh": "你是一位擅长把复杂概念讲清楚的解释者，先给直觉，再给严谨定义，最后给边界。",
        "role_en": "You are an explainer who gives intuition first, then the rigorous definition, then the boundaries.",
        "steps_zh": [
            "先用一句话回答（结论前置），不加铺垫。",
            "给出直觉类比，并说明类比的失效边界。",
            "给出严谨解释：机制、关键条件、必要的术语定义。",
            "举一个具体例子，包含输入与结果。",
            "列出常见误解 2 条并纠正。",
        ],
        "steps_en": [
            "Answer in one sentence first, no preamble.",
            "Give an intuition-building analogy and where it breaks.",
            "Give the rigorous explanation: mechanism, conditions, key terms.",
            "Work through one concrete example with input and result.",
            "List and correct two common misconceptions.",
        ],
        "output_zh": "一句话结论 + 直觉 + 严谨解释 + 例子 + 常见误解。术语首次出现需解释。",
        "output_en": "One-sentence answer, intuition, rigorous explanation, example, misconceptions. Define terms on first use.",
        "selfcheck_zh": ["结论是否可在第一句读到", "类比是否说明了失效边界", "是否存在未定义的术语"],
        "selfcheck_en": ["Answer appears in sentence one", "Analogy limits stated", "No undefined jargon"],
    },
    "agent": {
        "role_zh": "你是一个按流程执行任务的智能体，具备明确的工具集、停止条件与失败回退策略。",
        "role_en": "You are a process-driven agent with a defined toolset, stop conditions and failure fallbacks.",
        "steps_zh": [
            "先解析任务，输出结构化执行计划（步骤 + 所需工具 + 预期中间产物）。",
            "逐步执行，每步输出「已完成 / 产出 / 下一步」。",
            "遇到信息不足时先提问，不要自行假设关键参数。",
            "达到停止条件即总结交付，不做额外发散。",
        ],
        "steps_en": [
            "Parse the task and output a structured plan: steps, tools needed, expected intermediates.",
            "Execute step by step, reporting done / artifact / next for each.",
            "Ask before assuming when key parameters are missing.",
            "Stop at the stop condition and summarize; do not expand scope.",
        ],
        "output_zh": "执行计划表 + 分步结果 + 最终交付物 + 未解决问题清单。",
        "output_en": "Execution plan table, per-step results, final deliverable, open issues.",
        "selfcheck_zh": ["是否有明确停止条件", "是否声明了工具与权限边界", "是否记录了失败回退"],
        "selfcheck_en": ["Stop condition defined", "Tool and permission boundaries stated", "Fallbacks recorded"],
    },
    "review": {
        "role_zh": "你是一位严格的评审者，只关注可验证的问题：正确性、安全性、可维护性、性能。按严重度排序，不做与问题无关的风格说教。",
        "role_en": "You are a rigorous reviewer focused on verifiable issues: correctness, security, maintainability, performance. Rank by severity; skip style nitpicks.",
        "steps_zh": [
            "先复述评审对象与验收基线：这段代码/方案原本要解决什么问题。",
            "按固定顺序逐项检查：正确性 → 边界与异常 → 安全 → 性能 → 可维护性。",
            "每个问题必须写清：位置、现象、影响、修复建议（给出替代写法）。",
            "按 P0/P1/P2 分级，并说明定级依据而非凭感觉。",
            "明确区分「必须改」与「建议改」；建议项要说明不改的后果。",
            "指出缺失的测试与未覆盖的边界场景。",
        ],
        "steps_en": [
            "Restate the review target and its baseline: what problem it was meant to solve.",
            "Check in a fixed order: correctness, edge cases, security, performance, maintainability.",
            "For each issue state location, symptom, impact, and a concrete fix (with alternative code).",
            "Grade as P0/P1/P2 with stated rationale, not gut feeling.",
            "Separate must-fix from nice-to-have; explain the consequence of skipping the latter.",
            "Call out missing tests and uncovered edge cases.",
        ],
        "output_zh": "问题清单表（严重度／位置／现象／影响／修复建议）+ 必须修改项 + 建议修改项 + 缺失的测试。",
        "output_en": "Issue table (severity/location/symptom/impact/fix) plus must-fix list, nice-to-have list, and missing tests.",
        "selfcheck_zh": ["每个问题都能定位到具体位置", "分级有明确依据", "必须改与建议改已区分", "未编造不存在的缺陷"],
        "selfcheck_en": ["Every issue is locatable", "Severity rationale given",
                         "Must-fix separated from nice-to-have", "No invented defects"],
    },
    "product": {
        "role_zh": "你是一位资深产品经理，擅长把模糊诉求转成有边界、可验收、可排期的需求。",
        "role_en": "You are a senior product manager who turns vague asks into scoped, testable, schedulable requirements.",
        "steps_zh": [
            "明确目标用户与使用场景，写出 1 条用户故事（角色—目标—价值）。",
            "划定范围：必须做 / 可选做 / 明确不做，三档都要有内容。",
            "为每个功能给出可测的验收标准（Given-When-Then 或可量化指标）。",
            "标注依赖、风险与关键假设；假设必须可被验证或推翻。",
            "给出 MVP 边界与二期候选，说明取舍理由。",
        ],
        "steps_en": [
            "Identify target users and scenario; write one user story (role-goal-value).",
            "Scope in three tiers: must-have, nice-to-have, explicitly out of scope.",
            "Give each feature a testable acceptance criterion (Given-When-Then or a metric).",
            "List dependencies, risks and key assumptions; assumptions must be falsifiable.",
            "Define the MVP boundary and phase-two candidates with rationale.",
        ],
        "output_zh": "用户故事 + 范围表（必须／可选／不做）+ 验收标准 + 依赖与风险 + MVP 边界。",
        "output_en": "User story, scope table (must/nice/out), acceptance criteria, dependencies and risks, MVP boundary.",
        "selfcheck_zh": ["验收标准是否可测而非描述性", "范围是否闭合无灰色地带", "MVP 与二期是否区分清楚", "假设是否可验证"],
        "selfcheck_en": ["Acceptance criteria testable, not descriptive", "Scope closed with no grey zone",
                         "MVP separated from phase two", "Assumptions falsifiable"],
    },
    "general": {
        "role_zh": "你是一位经验丰富的专业助手，善于在信息不完整时先确认关键前提，再给出可直接使用的交付物。",
        "role_en": "You are an experienced assistant who confirms critical premises before producing a directly usable deliverable.",
        "steps_zh": [
            "先复述任务目标与交付物形态，确认理解一致。",
            "列出必要前提与假设；缺失项优先提问而非编造。",
            "分步骤完成，每步给出可检查的中间结果。",
            "输出最终交付物，并说明如何使用。",
            "附上自检清单，指出仍存在的风险。",
        ],
        "steps_en": [
            "Restate the goal and deliverable form to confirm alignment.",
            "List premises and assumptions; ask instead of inventing missing facts.",
            "Complete step by step with checkable intermediates.",
            "Deliver the final artifact and explain how to use it.",
            "Attach a self-check list and residual risks.",
        ],
        "output_zh": "结构化 Markdown，包含小标题与要点列表；关键结论加粗。",
        "output_en": "Structured Markdown with headings and bullets; key conclusions in bold.",
        "selfcheck_zh": ["目标是否被完整覆盖", "是否存在未标注的假设", "交付物是否可直接使用"],
        "selfcheck_en": ["Goal fully covered", "No unlabeled assumptions", "Deliverable usable as-is"],
    },
}

DOMAIN_HINTS = {
    "energy": {
        "zh": "行业语境：新能源。避免夸大续航与补贴表述；涉及政策口径须注明来源年份；用能数据需区分理论值与实测值。",
        "en": "Domain: new energy. Avoid overstated range or subsidy claims; cite the year for any policy figure; separate theoretical from measured data.",
    },
    "tech": {
        "zh": "行业语境：技术研发。需说明版本、运行环境与兼容范围；性能结论须给出测试条件。",
        "en": "Domain: technology. State versions, runtime and compatibility scope; performance claims need test conditions.",
    },
    "marketing": {
        "zh": "行业语境：市场营销。杜绝「最」「第一」「国家级」等绝对化用语；卖点需可验证。",
        "en": "Domain: marketing. No absolute superlatives; every claim must be verifiable.",
    },
    "ecommerce": {
        "zh": "行业语境：电商。价格、库存、活动规则等易变信息用占位符标注，不臆造具体数字。",
        "en": "Domain: e-commerce. Mark volatile facts (price, stock, promo rules) as placeholders; do not invent numbers.",
    },
    "education": {
        "zh": "行业语境：教育。难度需与目标学段匹配，给出可布置、可批改的产出。",
        "en": "Domain: education. Match difficulty to the grade level; outputs must be assignable and gradable.",
    },
    "finance": {
        "zh": "行业语境：金融。数据须标注口径与时间；不得给出投资建议式表述，改为条件化分析。",
        "en": "Domain: finance. Label data basis and date; avoid advice framing, use conditional analysis.",
    },
    "medical": {
        "zh": "行业语境：医疗健康。仅作科普信息，不做诊断结论；涉及用药须提示遵医嘱。",
        "en": "Domain: healthcare. Informational only, no diagnosis; defer medication questions to clinicians.",
    },
    "legal": {
        "zh": "行业语境：法务。按条款化表达，区分强制性与建议性；提示不构成正式法律意见。",
        "en": "Domain: legal. Use clause-style language, separate mandatory from advisory; note it is not formal legal advice.",
    },
    "game": {
        "zh": "行业语境：游戏。数值需给出计算公式与取值区间，避免失衡的极端值。",
        "en": "Domain: gaming. Provide formulas and ranges for numbers; avoid unbalanced extremes.",
    },
    "hr": {
        "zh": "行业语境：人力资源。避免歧视性表述（年龄/性别/婚育），评价维度需与岗位能力对应。",
        "en": "Domain: HR. Avoid discriminatory wording; tie every criterion to job competencies.",
    },
    # —— 第二组领域语境：新增行业特有的合规与可验证性约束 ——
    "manufacturing": {
        "zh": "行业语境：制造与供应链。区分计划值与实测值；良率、节拍等指标须注明统计口径与样本区间；涉及产线变更要说明切换风险。",
        "en": "Domain: manufacturing. Separate planned from measured values; state the measurement basis for yield and cycle time; call out changeover risk.",
    },
    "auto": {
        "zh": "行业语境：汽车。续航、油耗等指标须标注测试工况（如 CLTC/WLTP）；不得对安全性能作绝对化承诺；参数以官方口径为准。",
        "en": "Domain: automotive. Label the test cycle for range or efficiency figures; never make absolute safety claims; cite official specs for parameters.",
    },
    "travel": {
        "zh": "行业语境：文旅。价格与库存属易变信息，用占位符标注；行程需注明时长与交通方式；避免无法验证的景点排名表述。",
        "en": "Domain: travel. Mark volatile price and availability as placeholders; specify duration and transport per leg; avoid unverifiable rankings.",
    },
    "food": {
        "zh": "行业语境：餐饮。不得虚构食材来源与功效；价格与份量用占位符；涉及食品安全的表述须保守。",
        "en": "Domain: food service. Do not invent sourcing or health claims; placeholder pricing and portions; keep food-safety wording conservative.",
    },
    "realestate": {
        "zh": "行业语境：房产。面积、价格、学区等信息须标注口径与时效；不得承诺升值或入学资格；具体数字用占位符。",
        "en": "Domain: real estate. State the basis and date for area, price or school-district claims; never promise appreciation or admission; placeholder hard numbers.",
    },
    "research": {
        "zh": "行业语境：科研。区分事实、推断与假设；引用须标注来源类型；不得虚构文献、DOI 或实验数据。",
        "en": "Domain: research. Separate fact, inference and hypothesis; label source types; never fabricate references, DOIs or experimental data.",
    },
    # —— 第三组领域语境：安全、物流、政务、客服、农业、内容制作 ——
    "security": {
        "zh": "行业语境：安全与合规。只描述防御与加固思路，不给出可直接利用的攻击步骤；漏洞需标注影响面与利用前置条件；涉及授权范围必须显式声明。",
        "en": "Domain: security. Stay on defense and hardening; no turnkey exploitation steps; state impact and preconditions per finding; declare the authorization scope.",
    },
    "logistics": {
        "zh": "行业语境：物流与仓储。时效、成本、破损率等指标须注明统计口径与观察周期；涉及仓网布局要说明单量与波次假设；不臆造承运商报价。",
        "en": "Domain: logistics. State the measurement basis and observation window for time, cost and damage rates; give volume and wave assumptions; never invent carrier pricing.",
    },
    "government": {
        "zh": "行业语境：政务与公共事务。表述须与公开政策口径一致，引用文件标注名称与发布年份；避免绝对化承诺；涉及民生的数据用占位符并注明来源渠道。",
        "en": "Domain: public sector. Keep wording consistent with published policy; cite document names and years; avoid absolute commitments; placeholder civic statistics with their channel.",
    },
    "service": {
        "zh": "行业语境：客户服务。话术须区分场景（咨询/投诉/退换），给出情绪安抚与升级路径；不得承诺超出政策的补偿；涉及个人信息的环节提示合规要求。",
        "en": "Domain: customer service. Split scripts by scenario (inquiry, complaint, return); include de-escalation and escalation paths; promise nothing beyond policy; flag privacy handling.",
    },
    "agriculture": {
        "zh": "行业语境：农业。区分试验值与推广值；涉及产量、用药与施肥须注明地域、季节与作物品种；不得给出无来源的增产承诺。",
        "en": "Domain: agriculture. Separate trial results from field-adopted figures; state region, season and cultivar for yield, pesticide and fertilizer advice; no unsourced yield promises.",
    },
    "media": {
        "zh": "行业语境：内容与影视。脚本须区分画面、台词与音效；时长、分镜数量与拍摄条件用占位符；不得虚构播放数据或平台榜单。",
        "en": "Domain: media. Separate visuals, dialogue and sound in scripts; placeholder duration, shot count and shooting conditions; never fabricate view counts or rankings.",
    },
    "general": {"zh": "", "en": ""},
}

# 意图骨架：交付物本身的章节顺序（与 TEMPLATES 的“过程步骤”互补）。
# 步骤回答“怎么做”，骨架回答“成品长什么样”，两者都不允许缺省。
OUTLINES: dict[str, dict[str, list[str]]] = {
    "coding": {
        "zh": ["问题理解与关键假设", "方案与取舍（含被否决的替代方案）", "完整代码（导入／错误处理／边界）",
               "运行与验证步骤", "已知限制与后续优化"],
        "en": ["Problem restatement and key assumptions", "Approach and trade-offs (including the rejected one)",
               "Complete code with imports, error handling and edge guards", "Run and verification steps",
               "Known limitations and next steps"],
    },
    "marketing": {
        "zh": ["核心主张（一句话说清用户所得）", "3 个支撑卖点与对应证据", "开头钩子（3 秒内成立）",
               "正文与场景共鸣", "唯一行动号召", "备选标题与投放建议"],
        "en": ["Core claim in one sentence", "Three supporting points with proof", "Hook that lands in 3 seconds",
               "Body with scenario resonance", "One single call to action", "Alternative headlines and placement notes"],
    },
    "analysis": {
        "zh": ["结论先行（BLUF）", "分析对象与维度定义", "逐维度证据（事实／推断分离）",
               "量化依据与假设说明", "按影响×成本排序的建议", "结论失效条件"],
        "en": ["Bottom line up front", "Object of analysis and dimension definitions",
               "Evidence per dimension (fact vs. inference)", "Quantification and stated assumptions",
               "Recommendations ranked by impact vs. cost", "Conditions that invalidate the conclusion"],
    },
    "summarize": {
        "zh": ["一句话总览（≤40 字）", "分层要点（≤7 条）", "关键数字与专有名词",
               "存疑／待核实项", "被舍弃的信息类型"],
        "en": ["One-sentence overview (max 40 words)", "Hierarchical bullets (max 7)",
               "Key figures and proper nouns", "Claims needing verification", "Categories of detail dropped"],
    },
    "translate": {
        "zh": ["文本类型判断与翻译策略", "术语表（原文 → 译文）", "完整译文（保留段落与编号）",
               "歧义句与备选译法"],
        "en": ["Text-type judgement and strategy", "Glossary (source to target)",
               "Full translation with paragraphs and numbering preserved", "Ambiguous sentences with alternatives"],
    },
    "plan": {
        "zh": ["目标指标（基线 → 目标值）", "阶段划分与阶段产出物", "行动项表（负责人／依赖／工时）",
               "风险清单与前 3 个兜底方案", "本周可启动的最小行动"],
        "en": ["Target metric (baseline to target)", "Phases and deliverables per phase",
               "Action table with owner, dependencies and effort", "Top 3 risks with fallbacks",
               "Smallest action that can start this week"],
    },
    "writing": {
        "zh": ["读者应记住的核心观点", "3 个切入角度与推荐", "开头钩子", "主体论证（一段一事）",
               "收束与落点", "待补充事实标记"],
        "en": ["The single point readers should remember", "Three entry angles with a recommendation",
               "Opening hook", "Body (one idea per paragraph)", "Close and landing point",
               "Markers for facts only the user can supply"],
    },
    "qa": {
        "zh": ["一句话结论", "直觉类比及其失效边界", "严谨机制解释", "具体例子（输入 → 结果）", "常见误解纠正"],
        "en": ["One-sentence answer", "Intuition and where the analogy breaks", "Rigorous mechanism",
               "Worked example (input to result)", "Common misconceptions corrected"],
    },
    "agent": {
        "zh": ["角色与目标", "工具集与权限边界", "执行循环（步骤 → 中间产物）", "停止条件",
               "失败回退与人工介入点"],
        "en": ["Role and goal", "Toolset and permission boundaries", "Execution loop (step to intermediate)",
               "Stop condition", "Failure fallbacks and human handoff"],
    },
    "review": {
        "zh": ["评审对象与验收基线", "问题清单（严重度／位置／现象／影响／修复建议）",
               "必须修改项", "建议修改项", "缺失的测试与未覆盖边界"],
        "en": ["Review target and its baseline", "Issue table (severity, location, symptom, impact, fix)",
               "Must-fix items", "Nice-to-have items", "Missing tests and uncovered edge cases"],
    },
    "product": {
        "zh": ["用户故事（角色—目标—价值）", "范围表（必须／可选／不做）",
               "验收标准（Given-When-Then 或指标）", "依赖、风险与可验证假设", "MVP 边界与二期候选"],
        "en": ["User story (role, goal, value)", "Scope table (must, nice, out)",
               "Acceptance criteria (Given-When-Then or metric)", "Dependencies, risks and falsifiable assumptions",
               "MVP boundary and phase-two candidates"],
    },
    "general": {
        "zh": ["目标与交付物复述", "前提与假设", "执行步骤与中间结果", "最终交付物与使用说明",
               "自检清单与残余风险"],
        "en": ["Goal and deliverable restated", "Premises and assumptions", "Steps with intermediate results",
               "Final deliverable and usage notes", "Self-check list and residual risks"],
    },
}

MODE_HINTS = {
    "struct": {
        "zh": "输出必须采用分节结构，每节使用二级标题，禁止大段无结构文字。",
        "en": "Use sectioned structure with H2 headings; no long unstructured prose.",
    },
    "concise": {
        "zh": "极致精简：删除所有铺垫与客套，只保留信息密度最高的内容，总长度不超过原需求复杂度的 1/3。",
        "en": "Radically concise: drop preamble and pleasantries, keep only high-density content.",
    },
    "creative": {
        "zh": "允许并鼓励非常规表达，但必须给出 2 个风格差异明显的方案供选择，并说明各自风险。",
        "en": "Unconventional phrasing is welcome, but provide 2 clearly different options with their risks.",
    },
    "academic": {
        "zh": "论证需区分事实、推断与观点；引用他人结论须标注来源类型（论文/报告/媒体），不得虚构文献。",
        "en": "Separate fact, inference and opinion; label source types; never fabricate citations.",
    },
    "code": {
        "zh": "以可执行代码为主，解释从简；必须包含输入校验与异常路径。",
        "en": "Lead with runnable code, keep prose minimal; include input validation and error paths.",
    },
    "agent": {
        "zh": "以角色+工具+循环+停止条件组织，明确失败回退与人工介入点。",
        "en": "Organize as role + tools + loop + stop condition, with fallbacks and human handoff points.",
    },
}
