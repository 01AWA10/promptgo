"""输入分析器。

职责：把一段自由文本解析为可复用的结构化事实——语言、意图、领域、显式约束、
缺失槽位（需要向用户追问的信息）与风险点（会让提示词失效的模糊表述）。

设计约束：纯函数、零 IO、零第三方依赖、结果可复现。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

CJK_RE = re.compile(r"[\u4e00-\u9fff]")
LATIN_WORD_RE = re.compile(r"[A-Za-z]+")
NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
QUOTED_RE = re.compile(r"[「『“\"']([^」』”\"']{2,40})[」』”\"']")
TOPIC_PATTERNS = (
    re.compile(r"关于\s*([\u4e00-\u9fffA-Za-z0-9]{2,24})"),
    re.compile(r"针对\s*([\u4e00-\u9fffA-Za-z0-9]{2,24})"),
    re.compile(r"围绕\s*([\u4e00-\u9fffA-Za-z0-9]{2,24})"),
    re.compile(r"(?:为|给)\s*([\u4e00-\u9fffA-Za-z0-9]{2,16}?)\s*(?:写|做|设计|制定|生成|翻译)"),
    re.compile(r"(?:about|regarding|for|on)\s+([A-Za-z0-9 \-]{3,32})", re.I),
)

TOPIC_STOPWORDS = {
    "explain", "write", "generate", "analyze", "analyse", "build", "design",
    "summarize", "summarise", "translate", "compare", "evaluate", "how", "what",
    "why", "some", "please", "help", "make", "create", "draft", "give",
    "帮我", "写个", "写一个", "生成", "做一", "一下", "怎么", "如何", "关于",
}

# ---------------------------------------------------------------- 意图词表
INTENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "coding": (
        "代码", "函数", "脚本", "报错", "异常", "重构", "单元测试", "接口", "正则",
        "python", "java", "javascript", "typescript", "sql", "react", "vue", "css",
        "html", "docker", "bug", "api", "code", "debug", "refactor", "leetcode",
    ),
    "marketing": (
        "文案", "营销", "推广", "广告", "slogan", "口号", "种草", "带货", "品牌",
        "卖点", "转化", "投放", "标题", "宣传", "朋友圈", "小红书", "详情页",
        "copywriting", "marketing", "ad copy", "campaign", "landing page",
    ),
    "analysis": (
        "分析", "对比", "评估", "调研", "洞察", "归因", "竞品", "swot", "复盘",
        "数据", "指标", "趋势", "优缺点", "可行性", "analyze", "analysis", "compare",
        "evaluate", "research", "insight",
    ),
    "summarize": (
        "总结", "摘要", "概括", "提炼", "要点", "精简", "缩写", "summary",
        "summarize", "tldr", "key points", "condense",
    ),
    "translate": (
        "翻译", "译成", "中译英", "英译中", "translate", "translation", "localize",
    ),
    "plan": (
        "计划", "方案", "规划", "排期", "路线图", "流程", "步骤", "落地", "执行",
        "里程碑", "roadmap", "plan", "strategy", "playbook", "checklist",
    ),
    "writing": (
        "写一篇", "撰写", "文章", "博客", "故事", "小说", "演讲稿", "作文", "邮件",
        "周报", "述职", "文案稿", "essay", "article", "blog", "story", "speech",
        "write a", "draft",
    ),
    "qa": (
        "是什么", "什么是", "为什么", "区别", "原理", "解释", "科普", "怎么理解",
        "explain", "what is", "why", "difference", "how does",
    ),
    "agent": (
        "助手", "助理", "agent", "工作流", "自动化", "提示词", "prompt", "角色设定",
        "system prompt", "自动化流程", "工具调用", "workflow",
    ),
    # —— 新增：评审与产品需求。两者都有独有强词，避免与其他意图互相抢分 ——
    "review": (
        "代码审查", "评审", "走查", "变更审查", "安全审计", "code review",
        "pull request", "review",
    ),
    "product": (
        "prd", "需求文档", "用户故事", "功能设计", "原型图", "mvp",
        "产品需求", "需求清单", "迭代计划", "埋点",
    ),
}

# ---------------------------------------------------------------- 领域词表
DOMAIN_KEYWORDS: dict[str, tuple[str, ...]] = {
    "energy": ("新能源", "光伏", "储能", "电池", "充电桩", "双碳", "电动车", "碳中和", "风电"),
    "tech": ("代码", "程序", "数据库", "服务器", "算法", "部署", "前端", "后端", "架构",
             "接口", "微服务", "云原生", "devops", "linux", "git", "函数", "脚本",
             "数据结构", "字典", "排序", "并发", "缓存", "正则", "报错", "性能"),

    "marketing": ("营销", "品牌", "广告", "转化", "增长", "私域", "投放", "种草", "曝光"),
    "ecommerce": ("电商", "商品", "店铺", "直播", "选品", "客单价", "sku", "复购", "供应链"),
    "education": ("教学", "课程", "学生", "老师", "教案", "作业", "考试", "知识点", "培训"),
    "finance": ("金融", "投资", "基金", "保险", "风控", "财报", "估值", "信贷", "利率"),
    "medical": ("医疗", "患者", "临床", "诊断", "用药", "病历", "健康", "医院", "体检"),
    "legal": ("法律", "合同", "条款", "合规", "诉讼", "知识产权", "劳动仲裁", "协议"),
    "game": ("游戏", "关卡", "数值", "玩家", "策划", "副本", "抽卡", "平衡性"),
    "hr": ("招聘", "简历", "面试", "绩效", "组织", "任职资格", "hc", "offer"),
    # —— 第二组领域：覆盖制造、汽车、文旅、餐饮、地产、科研六类高频场景 ——
    "manufacturing": ("产线", "良率", "工单", "产能", "精益", "质检", "供应商",
                      "库存周转", "mes", "设备点检", "节拍"),
    "auto": ("车型", "试驾", "4s店", "购车", "保养", "油耗", "座舱", "变速箱",
             "发动机", "车机", "续航里程"),
    "travel": ("行程", "景点", "机票", "酒店", "民宿", "签证", "旅游", "出游",
               "自由行", "跟团"),
    "food": ("菜品", "门店", "外卖", "套餐", "堂食", "翻台率", "菜单", "餐厅",
             "出餐", "试吃"),
    "realestate": ("楼盘", "户型", "租金", "装修", "物业", "学区", "购房", "家居",
                   "精装", "公摊"),
    "research": ("论文", "实验", "文献", "显著性", "假设检验", "课题", "基金申请",
                 "学术", "综述", "样本量"),
    # —— 第三组领域：安全、物流、政务、客服、农业、内容制作 ——
    # 选词原则同上：只用本行业独有词，避免与 tech/marketing 的泛词互相抢分
    "security": ("网络安全", "渗透测试", "漏洞", "等保", "防火墙", "零信任",
                 "攻防", "数据泄露", "加密", "应急响应", "越权", "注入"),
    "logistics": ("物流", "仓储", "运单", "冷链", "分拣", "干线", "配送", "承运商",
                  "签收", "运费", "揽收", "仓配"),
    "government": ("政务", "公文", "政策解读", "通知公告", "民生", "街道办", "政务公开",
                   "红头文件", "信访", "政府", "惠民"),
    "service": ("客服", "客诉", "售后", "满意度", "话术", "呼叫中心", "服务规范",
                "退换货", "投诉", "服务体验"),
    "agriculture": ("农业", "种植", "养殖", "农户", "农产品", "化肥", "亩产", "病虫害",
                    "采摘", "农机", "示范田"),
    "media": ("影视", "剧本", "分镜", "综艺", "短剧", "剪辑", "拍摄", "达人",
              "爆款视频", "选题会", "口播"),
}

# ---------------------------------------------------------------- 领域同义词（P2-11）
# 关键词匹配只能命中字面：用户把「私域」写成「社群」、或用英文描述行业时会漏判。
# 这里按领域补高频别名与英文表述，仍然只做「命中即计分」，不引入语义模型。
# 新增词的三条约束：① 只加本行业独有词，避免与相邻领域抢分；
# ② 英文词长度 ≥4 且不会成为其他单词的子串（如 "api" 会命中 "rapid"）；
# ③ 不改动 DOMAIN_PRIORITY，防止平局时的归属被悄悄改变。
DOMAIN_SYNONYMS: dict[str, tuple[str, ...]] = {
    "energy": ("太阳能", "储能电站", "充电站", "solar", "battery", "renewable"),
    "tech": ("研发", "运维", "容器", "集群", "k8s", "database", "backend", "frontend",
             "algorithm", "kubernetes", "deploy"),
    "marketing": ("社群", "裂变", "拉新", "获客", "留存", "会员", "branding", "funnel",
                  "lifecycle"),
    "ecommerce": ("网店", "购物车", "下单", "listing", "checkout"),
    "education": ("学员", "题库", "考点", "授课", "课件", "curriculum", "tutoring"),
    "finance": ("理财", "贷款", "证券", "股票", "支付", "结算", "loan", "portfolio",
                "payment"),
    "medical": ("门诊", "诊所", "处方", "护理", "康复", "clinic", "diagnosis", "prescription"),
    "legal": ("法务", "律师", "侵权", "保密协议", "contract", "compliance", "litigation"),
    "game": ("手游", "端游", "氪金", "装备", "公会", "gameplay"),
    "hr": ("入职", "离职", "薪酬", "社保", "公积金", "背调", "recruiting", "onboarding",
           "compensation"),
    "manufacturing": ("工厂", "车间", "工艺", "设备", "生产线", "factory", "production line"),
    "auto": ("经销商", "智驾", "辅助驾驶", "车展", "二手车", "dealership", "vehicle"),
    "travel": ("旅行社", "攻略", "自驾", "门票", "航班", "itinerary", "flight"),
    "food": ("餐饮", "菜谱", "食谱", "厨师", "recipe", "restaurant"),
    "realestate": ("房地产", "二手房", "租房", "按揭", "mortgage", "property"),
    "research": ("科研", "期刊", "试验", "对照组", "同行评审", "hypothesis", "peer review"),
    "security": ("信息安全", "勒索软件", "钓鱼邮件", "漏洞扫描", "弱口令", "ransomware",
                 "phishing", "vulnerability"),
    "logistics": ("快递", "货运", "仓库", "快递柜", "freight", "warehouse"),
    "government": ("公共服务", "政务大厅", "公告", "municipal", "public sector"),
    "service": ("客户服务", "服务台", "helpdesk", "csat"),
    "agriculture": ("农场", "田间", "播种", "收割", "果园", "farm", "harvest", "greenhouse"),
    "media": ("纪录片", "栏目", "摄制", "vlog", "documentary"),
}
for _domain, _extra in DOMAIN_SYNONYMS.items():
    DOMAIN_KEYWORDS[_domain] = DOMAIN_KEYWORDS[_domain] + _extra
del _domain, _extra

# 领域平局时的决胜顺序：越靠前越“具体”，避免泛行业词抢走细分行业
# security/logistics 前置：它们的词常与 tech/manufacturing 重叠，平局时必须优先
DOMAIN_PRIORITY = ("security", "auto", "energy", "tech", "medical", "legal", "finance",
                   "research", "manufacturing", "logistics", "ecommerce", "education",
                   "hr", "game", "realestate", "travel", "food", "government", "media",
                   "agriculture", "service", "marketing", "general")

INTENT_PRIORITY = ("review", "coding", "translate", "summarize", "marketing",
                   "product", "analysis", "plan", "agent", "writing", "qa")

# 评审类动词是强信号：这类请求会同时命中 coding/marketing 的内容词，
# 纯比分会把「评审这段代码」误判成「编写代码」。
REVIEW_MARKERS = ("评审", "审查", "走查", "code review", "pull request")

# 影视/短视频脚本同样命中 coding 的「脚本」字样，但产出是文案而非程序，
# 命中这些标记时改判 content writing，避免套用工程骨架。
SCRIPT_MARKERS = ("分镜", "剧本", "短剧", "口播", "台词", "脚本大纲")

INTENT_LABEL = {
    "coding": ("代码与工程", "coding & engineering"),
    "marketing": ("营销与文案", "marketing copy"),
    "analysis": ("分析与评估", "analysis & evaluation"),
    "summarize": ("总结与提炼", "summarization"),
    "translate": ("翻译与本地化", "translation"),
    "plan": ("方案与规划", "planning"),
    "writing": ("内容创作", "content writing"),
    "qa": ("解释与问答", "explanation"),
    "agent": ("智能体设定", "agent setup"),
    "review": ("评审与走查", "review & audit"),
    "product": ("产品需求", "product requirements"),
    "general": ("通用任务", "general task"),
}

DOMAIN_LABEL = {
    "energy": ("新能源", "new energy"),
    "tech": ("技术研发", "technology"),
    "marketing": ("市场营销", "marketing"),
    "ecommerce": ("电子商务", "e-commerce"),
    "education": ("教育培训", "education"),
    "finance": ("金融", "finance"),
    "medical": ("医疗健康", "healthcare"),
    "legal": ("法务合规", "legal"),
    "game": ("游戏", "gaming"),
    "hr": ("人力资源", "human resources"),
    "manufacturing": ("制造与供应链", "manufacturing"),
    "auto": ("汽车", "automotive"),
    "travel": ("文旅与酒店", "travel & hospitality"),
    "food": ("餐饮与本地生活", "food & local services"),
    "realestate": ("房产与家居", "real estate"),
    "research": ("科研与学术", "research"),
    "security": ("安全与合规", "security"),
    "logistics": ("物流与仓储", "logistics"),
    "government": ("政务与公共事务", "public sector"),
    "service": ("客户服务", "customer service"),
    "agriculture": ("农业", "agriculture"),
    "media": ("内容与影视", "media & entertainment"),
    "general": ("通用", "general"),
}

VAGUE_ZH = ("尽量", "大概", "差不多", "一些", "有点", "可能", "等等", "之类",
            "比较好", "适当", "合理", "相关", "各方面", "随便", "看情况", "稍微",
            "好好地", "不错的")
VAGUE_EN = ("some", "maybe", "kind of", "sort of", "etc", "appropriate",
            "reasonable", "as needed", "a bit", "roughly", "various", "nice")

# ---------------------------------------------------------------- 约束抽取
LENGTH_PATTERNS = (
    (re.compile(r"(\d+)\s*(?:个)?(?:字|词)(?:以内|以下|左右)"), "max"),
    (re.compile(r"不超过\s*(\d+)\s*(?:个)?字"), "max"),
    (re.compile(r"(\d+)\s*[-~到至]\s*(\d+)\s*(?:个)?字"), "range"),
    (re.compile(r"(?:under|within|no more than)\s*(\d+)\s*words?", re.I), "max"),
)
FORMAT_WORDS = {
    "markdown": "Markdown", "表格": "表格", "table": "表格", "json": "JSON",
    "yaml": "YAML", "csv": "CSV", "列表": "列表", "大纲": "大纲", "ppt": "PPT 提纲",
    "思维导图": "思维导图", "邮件格式": "邮件格式", "bullet": "要点列表",
}
TONE_WORDS = {
    "正式": "正式", "严谨": "严谨", "专业": "专业", "口语": "口语化", "轻松": "轻松",
    "幽默": "幽默", "亲切": "亲切", "简洁": "简洁", "学术": "学术", "犀利": "犀利",
    "温暖": "温暖", "高级感": "高级感", "活泼": "活泼", "理性": "理性",
    "克制": "克制", "权威": "权威", "治愈": "治愈", "硬核": "硬核",
    "温柔": "温柔", "煽动": "煽动性", "official": "正式", "casual": "口语化",
    "professional": "专业", "concise": "简洁",
    # —— 语气扩展：人格化、文学化与网感表达，覆盖非正式场景 ——
    "毒舌": "毒舌", "冷幽默": "冷幽默", "俏皮": "俏皮", "松弛": "松弛",
    "真诚": "真诚", "干练": "干练", "沉稳": "沉稳", "冷静": "冷静",
    "激情": "激情", "极简": "极简", "诗意": "诗意", "纪实": "纪实",
    "悬念": "悬念", "高冷": "高冷", "网感": "网感", "文艺": "文艺",
    "接地气": "接地气", "烟火气": "烟火气", "温情": "温情", "热血": "热血",
    "witty": "幽默", "playful": "俏皮", "empathetic": "共情",
    # —— P2-11 同义改写：只加指向既有标签的别名，META 标签数不变 ——
    "风趣": "幽默", "诙谐": "幽默", "亲和": "亲切", "简练": "简洁", "精炼": "简洁",
    "严肃": "正式", "热情": "激情", "暖心": "温暖",
    "serious": "正式", "friendly": "亲切", "humorous": "幽默", "energetic": "活泼",
    "calm": "冷静", "minimal": "极简", "warm": "温暖", "authoritative": "权威",
}
# 语气与渠道可同时存在多个（一次投放多平台），保留条数上限；超出计入 truncated
MAX_MULTI = 4
CHANNEL_WORDS = {
    "小红书": "小红书", "公众号": "微信公众号", "抖音": "抖音", "知乎": "知乎",
    "微博": "微博", "朋友圈": "朋友圈", "官网": "官网", "短视频": "短视频",
    "直播": "直播", "邮件": "邮件", "ppt": "PPT", "海报": "海报", "banner": "Banner",
    "视频号": "微信视频号", "b站": "B站", "bilibili": "B站", "快手": "快手",
    "linkedin": "LinkedIn", "instagram": "Instagram", "tiktok": "TikTok",
    "短信": "短信", "新闻稿": "新闻稿", "白皮书": "白皮书", "播客": "播客",
    "落地页": "落地页", "详情页": "商品详情页",
    # —— 渠道扩展：开发者社区、站内与广告位、企业 IM ——
    "掘金": "掘金", "juejin": "掘金", "github": "GitHub", "应用商店": "应用商店",
    "信息流": "信息流广告", "开屏": "开屏广告", "电梯广告": "电梯广告",
    "楼宇": "楼宇广告", "站内信": "站内信", "企业微信": "企业微信",
    "钉钉": "钉钉", "push": "Push 推送",
    # —— P2-11 同义改写：平台别称与英文写法，仍映射到既有标签 ——
    "douyin": "抖音", "weibo": "微博", "zhihu": "知乎", "wechat": "微信公众号",
    "rednote": "小红书", "kuaishou": "快手", "twitter": "微博", "podcast": "播客",
    "press release": "新闻稿", "whitepaper": "白皮书", "newsletter": "邮件",
    "app store": "应用商店", "google play": "应用商店", "wecom": "企业微信",
    "dingtalk": "钉钉", "elevator ad": "电梯广告", "in-app message": "站内信",
}
# 终止符只认标点/空白/结尾：早期版本把「人」「们」也当终止符，
# 导致「面向技术负责人」被截成「技术负责」。
AUDIENCE_RE = re.compile(
    r"(?:面向|针对|给|向)\s*([\u4e00-\u9fffA-Za-z0-9 ]{2,14}?)"
    r"(?:的|看|用|写|讲|[，。、；,;：:\s]|$)",
)
LANG_WORDS = {
    "英文": "英文", "英语": "英文", "english": "英文", "中文": "中文",
    "日语": "日文", "韩语": "韩文", "双语": "中英双语",
}

SLOT_QUESTIONS = {
    ("zh", "audience"): "这份内容的读者是谁？请给出人群画像（角色/经验水平/关注点）。",
    ("zh", "tone"): "希望是什么语气与风格？例如专业严谨、轻松口语、有攻击性的销售风。",
    ("zh", "length"): "篇幅上限是多少？例如 300 字以内、800–1200 字。",
    ("zh", "format"): "期望的输出结构？例如 Markdown 分点、表格、JSON、可直接发布的成稿。",
    ("zh", "context"): "有哪些必须遵守的背景信息？产品定位、已有素材、禁忌词、参考样例。",
    ("zh", "success"): "怎样算这次输出合格？给出 2–3 条可检验的验收标准。",
    ("zh", "input"): "需要处理的具体材料是什么？请粘贴原文片段或关键数据。",
    ("zh", "scope"): "范围边界是什么？哪些必须包含、哪些明确不要写。",
    ("zh", "channel"): "内容投放在哪个渠道？不同渠道的字数、开头与行动号召写法差异很大。",
    ("en", "audience"): "Who is the audience? Role, seniority, and what they care about.",
    ("en", "tone"): "What tone and style? e.g. formal, conversational, punchy sales copy.",
    ("en", "length"): "What is the length budget? e.g. under 300 words, 800-1200 words.",
    ("en", "format"): "What output structure? Markdown bullets, table, JSON, or final copy.",
    ("en", "context"): "What context must be respected? Positioning, source material, banned terms.",
    ("en", "success"): "How do we judge success? Give 2-3 checkable acceptance criteria.",
    ("en", "input"): "What source material should be processed? Paste the text or key data.",
    ("en", "scope"): "What are the boundaries? Must-include vs. explicitly exclude.",
    ("en", "channel"): "Where will this be published? Length, hook and CTA differ sharply per channel.",
}

REQUIRED_SLOTS = {
    "coding": ("context", "format", "success"),
    "marketing": ("audience", "tone", "length", "channel", "format"),
    "analysis": ("audience", "format", "success"),
    "summarize": ("input", "length", "format"),
    "translate": ("tone", "format"),
    "plan": ("audience", "format", "scope"),
    "writing": ("audience", "tone", "length"),
    "qa": ("audience", "format"),
    "agent": ("context", "format", "success"),
    "review": ("context", "format", "success"),
    "product": ("audience", "scope", "success"),
    "general": ("audience", "length", "format"),
}


@dataclass
class Constraint:
    kind: str      # length | format | tone | audience | channel | language
    label: str     # 面向人类展示的名称
    value: str
    source: str = "explicit"

    def as_dict(self) -> dict:
        return {"kind": self.kind, "label": self.label, "value": self.value,
                "source": self.source}


@dataclass
class Analysis:
    text: str
    lang: str
    length: int
    intent: str
    intent_label: str
    domain: str
    domain_label: str
    constraints: list[Constraint] = field(default_factory=list)
    missing: list[dict] = field(default_factory=list)
    risks: list[dict] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    topic: str = ""
    entities: list[str] = field(default_factory=list)
    vague_hits: list[str] = field(default_factory=list)
    numbers: list[str] = field(default_factory=list)
    truncated: dict[str, int] = field(default_factory=dict)   # kind → 超出上限被丢弃的条数

    def constraint_values(self, kind: str) -> list[str]:
        return [c.value for c in self.constraints if c.kind == kind]

    def as_dict(self) -> dict:
        return {
            "lang": self.lang,
            "length": self.length,
            "intent": self.intent,
            "intent_label": self.intent_label,
            "domain": self.domain,
            "domain_label": self.domain_label,
            "constraints": [c.as_dict() for c in self.constraints],
            "missing": self.missing,
            "risks": self.risks,
            "keywords": self.keywords,
            "topic": self.topic,
            "entities": self.entities,
            "vague": self.vague_hits,
            "truncated": self.truncated,
        }


def detect_lang(text: str) -> str:
    cjk = len(CJK_RE.findall(text))
    words = len(LATIN_WORD_RE.findall(text))
    if cjk == 0:
        return "en" if words else "zh"
    return "en" if words > cjk * 6 else "zh"


def _score_hits(lowered: str, table: dict[str, Iterable[str]]) -> dict[str, int]:
    scores: dict[str, int] = {}
    for key, words in table.items():
        hit = 0
        for w in words:
            if w.lower() in lowered:
                # 中文两字词（如「试驾」「良率」）已具备足够区分度，与三字词同权；
                # 英文按字符长度分级，避免 "cr" 这类短词抢分
                if CJK_RE.search(w):
                    hit += 3 if len(w) >= 2 else 2
                else:
                    hit += 3 if len(w) >= 3 else 2
        if hit:
            scores[key] = hit
    return scores


def _pick(scores: dict[str, int], order: tuple[str, ...], default: str) -> str:
    if not scores:
        return default
    best = max(scores.values())
    candidates = [k for k, v in scores.items() if v == best]
    for key in order:
        if key in candidates:
            return key
    return candidates[0]


def _match_labels(lowered: str, table: dict[str, str],
                  limit: int | None = None) -> list[str]:
    """按「长词优先 + 命中不重叠 + 按出现位置排序」抽取标签。

    长词优先：避免「冷幽默」被更短的「幽默」抢先；
    不重叠：避免同一段文字既算「企业微信」又算别的短词；
    按位置排序：多渠道/多语气时，输出顺序与原文一致。
    `limit=None` 返回全部命中，调用方据此统计被截断的数量。
    """
    hits: list[tuple[int, str]] = []
    spans: list[tuple[int, int]] = []
    # 不再命中 limit 条就提前退出：超出部分要能统计成「被截断」，否则是静默丢弃
    for word in sorted(table, key=len, reverse=True):
        start = lowered.find(word)
        while start != -1:
            end = start + len(word)
            if not any(start < e and s < end for s, e in spans):
                spans.append((start, end))
                hits.append((start, table[word]))
                break
            start = lowered.find(word, start + 1)
    hits.sort()
    labels: list[str] = []
    for _, label in hits:
        if label not in labels:
            labels.append(label)
    return labels[:limit]


def _extract_constraints(text: str, lang: str) -> tuple[list[Constraint], dict[str, int]]:
    """返回约束列表与被截断数量（kind → 丢弃条数）。

    语气与渠道各保留 MAX_MULTI 条：多渠道投放常出现 4 个以上渠道，
    早期固定 2 条且静默丢弃，用户既看不到漏配也无法追溯。
    """
    out: list[Constraint] = []
    lowered = text.lower()
    dropped: dict[str, int] = {}

    for pattern, mode in LENGTH_PATTERNS:
        m = pattern.search(lowered)
        if not m:
            continue
        if mode == "range":
            out.append(Constraint("length", "篇幅", f"{m.group(1)}–{m.group(2)} 字"))
        else:
            out.append(Constraint("length", "篇幅", f"{m.group(1)} 字以内"))
        break

    for label in _match_labels(lowered, FORMAT_WORDS, 1):
        out.append(Constraint("format", "输出格式", label))

    tones = _match_labels(lowered, TONE_WORDS)
    for label in tones[:MAX_MULTI]:
        out.append(Constraint("tone", "语气风格", label))
    if len(tones) > MAX_MULTI:
        dropped["tone"] = len(tones) - MAX_MULTI

    channels = _match_labels(lowered, CHANNEL_WORDS)
    for label in channels[:MAX_MULTI]:
        out.append(Constraint("channel", "发布渠道", label))
    if len(channels) > MAX_MULTI:
        dropped["channel"] = len(channels) - MAX_MULTI

    for label in _match_labels(lowered, LANG_WORDS, 1):
        out.append(Constraint("language", "输出语言", label))

    m = AUDIENCE_RE.search(text)
    if m:
        out.append(Constraint("audience", "目标读者", m.group(1).strip()))

    return out, dropped


def _extract_keywords(text: str, lang: str) -> list[str]:
    words: list[str] = []
    # 先领域后意图：领域词通常是“用户真正在说的事物”，意图词更像动作
    for table in (DOMAIN_KEYWORDS, INTENT_KEYWORDS):
        for group in table.values():
            for w in group:
                if w.lower() in text.lower() and w not in words:
                    words.append(w)
    # 高频中文二元词组，作为“用户真正在说的事”的粗线索
    cjk_chunks = re.findall(r"[\u4e00-\u9fff]{2,6}", text)
    freq: dict[str, int] = {}
    for chunk in cjk_chunks:
        freq[chunk] = freq.get(chunk, 0) + 1
    for chunk, count in sorted(freq.items(), key=lambda kv: (-kv[1], -len(kv[0]))):
        if count >= 2 and chunk not in words:
            words.append(chunk)
    return words[:10]


def _extract_topic(text: str, domain: str, keywords: list[str],
                   entities: list[str]) -> str:
    for pattern in TOPIC_PATTERNS:
        m = pattern.search(text)
        if m:
            candidate = re.split(r"[的，。、；,;:：(]", m.group(1))[0].strip()
            if len(candidate) >= 2 and candidate.lower() not in TOPIC_STOPWORDS:
                return candidate
    lowered = text.lower()
    domain_terms = [w for w in DOMAIN_KEYWORDS.get(domain, ()) if w.lower() in lowered]
    candidate = max(domain_terms, key=len) if domain_terms else ""
    if not candidate:
        pool = [k for k in keywords if k.lower() not in TOPIC_STOPWORDS]
        candidate = max(pool[:6], key=len) if pool else ""
    if candidate and len(candidate) <= 3 and entities:
        return entities[0]
    if candidate:
        return candidate
    cleaned = text.replace("\n", " ").strip()
    return cleaned[:24] + ("…" if len(cleaned) > 24 else "")


def _extract_entities(text: str) -> list[str]:
    found = [m.group(1).strip() for m in QUOTED_RE.finditer(text)]
    for token in re.findall(r"\b[A-Z][A-Za-z0-9+#.]{1,15}\b", text):
        if token not in found:
            found.append(token)
    return found[:8]


# —— 背景是否已给的判定阈值（P2-13）——
# 旧实现只看字数（>120 即视为已给背景），复读、口号、纯填充的长文本会骗过判定，
# 让最该问的「背景」被跳过。这里改为长度 + 信息量双条件：中文看去重字符数与
# 去重率（复读文本去重率极低），英文看去重词占比（英语字母表有限，不能用字符）。
CONTEXT_MIN_CHARS = 80         # 有效字符数下限（去空白后）
CONTEXT_MIN_DISTINCT = 40      # 中文：去重后的有效字符数下限
CONTEXT_MIN_DENSITY = 0.30     # 中文：去重字符 / 总有效字符
CONTEXT_MIN_WORDS = 25         # 英文：有效词数下限
CONTEXT_MIN_WORD_RATIO = 0.45  # 英文：去重词 / 总词数


def _has_context(text: str, lang: str) -> bool:
    """判断输入是否已交代背景：长度够，且信息量不是靠复读堆出来的。"""
    compact = re.sub(r"\s+", "", text)
    if len(compact) < CONTEXT_MIN_CHARS:
        return False
    if lang == "en":
        words = [w.lower() for w in LATIN_WORD_RE.findall(text)]
        if len(words) < CONTEXT_MIN_WORDS:
            return False
        return len(set(words)) / len(words) >= CONTEXT_MIN_WORD_RATIO
    chars = re.findall(r"[A-Za-z0-9\u4e00-\u9fff]", compact)
    if not chars or len(set(chars)) < CONTEXT_MIN_DISTINCT:
        return False
    return len(set(chars)) / len(chars) >= CONTEXT_MIN_DENSITY


def _find_missing(intent: str, lang: str, constraints: list[Constraint],
                  text: str) -> list[dict]:
    have = {c.kind for c in constraints}
    if _has_context(text, lang):
        have.add("context")
    if re.search(r"(验收|成功标准|合格|标准是|acceptance|criteria|done when)", text, re.I):
        have.add("success")
    if re.search(r"(原文|材料|数据如下|背景如下|以下是)", text, re.I):
        have.add("input")
    if re.search(r"(只要|仅限|不要|排除|除了|不含|exclude|avoid)", text, re.I):
        have.add("scope")

    missing = []
    for slot in REQUIRED_SLOTS.get(intent, REQUIRED_SLOTS["general"]):
        if slot not in have:
            missing.append({
                "slot": slot,
                "question": SLOT_QUESTIONS.get((lang, slot), SLOT_QUESTIONS[("zh", slot)]),
            })
    return missing


def _find_risks(text: str, lang: str, constraints: list[Constraint]) -> list[dict]:
    risks: list[dict] = []
    lowered = text.lower()
    vague_pool = VAGUE_EN if lang == "en" else VAGUE_ZH
    hits = [w for w in vague_pool if w in lowered]
    if hits:
        risks.append({
            "level": "high" if len(hits) > 2 else "mid",
            "text": ("存在模糊表述：%s，模型无法判断具体标准" if lang == "zh"
                     else "Vague wording: %s — no measurable standard")
                    % "、".join(hits[:4]),
        })
    if len(text.strip()) < 12:
        risks.append({
            "level": "high",
            "text": "原始需求过短，缺少目标、对象与交付形态" if lang == "zh"
                    else "Request too short: goal, audience and deliverable are unspecified",
        })
    if not any(c.kind == "format" for c in constraints):
        risks.append({
            "level": "mid",
            "text": "未指定输出结构，模型会自行决定格式" if lang == "zh"
                    else "No output structure specified; the model will improvise",
        })
    if not any(c.kind == "audience" for c in constraints):
        risks.append({
            "level": "mid",
            "text": "未指明读者对象，内容深度与用词将不可控" if lang == "zh"
                    else "No audience specified; depth and vocabulary are uncontrolled",
        })
    multi = sum(lowered.count(w) for w in ("并且", "同时", "然后", "以及", "还要", "and also"))
    if multi >= 2:
        risks.append({
            "level": "mid",
            "text": "一句话里并置了多个任务，建议拆成编号子任务" if lang == "zh"
                    else "Multiple tasks merged in one sentence; split into numbered subtasks",
        })
    if not re.search(r"[。？！.?!；;]", text) and len(text) > 40:
        risks.append({
            "level": "low",
            "text": "长句无标点，语义边界不清" if lang == "zh"
                    else "Long sentence without punctuation; semantic boundaries unclear",
        })
    return risks


def analyze(text: str, lang: str = "auto") -> Analysis:
    raw = (text or "").strip()
    resolved_lang = detect_lang(raw) if lang in (None, "", "auto") else (
        "en" if lang.startswith("en") else "zh")
    lowered = raw.lower()

    intent_scores = _score_hits(lowered, INTENT_KEYWORDS)
    domain_scores = _score_hits(lowered, DOMAIN_KEYWORDS)
    intent = _pick(intent_scores, INTENT_PRIORITY, "general")
    if intent != "review" and any(marker in lowered for marker in REVIEW_MARKERS):
        intent = "review"
    elif intent == "coding" and any(marker in lowered for marker in SCRIPT_MARKERS):
        intent = "writing"
    domain = _pick(domain_scores, DOMAIN_PRIORITY, "general")

    constraints, truncated = _extract_constraints(raw, resolved_lang)
    keywords = _extract_keywords(raw, resolved_lang)
    entities = _extract_entities(raw)
    analysis = Analysis(
        text=raw,
        lang=resolved_lang,
        length=len(raw),
        intent=intent,
        intent_label=INTENT_LABEL[intent][0 if resolved_lang == "zh" else 1],
        domain=domain,
        domain_label=DOMAIN_LABEL[domain][0 if resolved_lang == "zh" else 1],
        constraints=constraints,
        truncated=truncated,
        keywords=keywords,
        topic=_extract_topic(raw, domain, keywords, entities),
        entities=entities,
        vague_hits=[w for w in (VAGUE_EN if resolved_lang == "en" else VAGUE_ZH)
                    if w in lowered][:6],
        numbers=NUMBER_RE.findall(raw)[:8],
    )
    analysis.missing = _find_missing(intent, resolved_lang, constraints, raw)
    analysis.risks = _find_risks(raw, resolved_lang, constraints)
    return analysis
