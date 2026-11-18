"""输入分析器。

职责：把一段自由文本解析为可复用的结构化事实——语言、意图、领域、显式约束、
缺失槽位（需要向用户追问的信息）与风险点（会让提示词失效的模糊表述）。

设计约束：纯函数、零 IO、零第三方依赖、结果可复现。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

from . import visual

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
    # —— 图像意图：只收「产出物是图」的强词；「海报」「封面」单出现不足以判图像，
    #    真正的判定见 `_is_image_request`（产物词 + 创作动词/视觉描述双条件）——
    "image": (
        "画一张", "画一幅", "画一只", "画个", "绘制", "出图", "文生图", "生成图片",
        "插画", "主图", "白底图", "头像", "人设图", "壁纸", "封面图", "概念图",
        "分镜图", "宣传图", "配图", "主视觉", "展板", "midjourney", "sdxl",
        "stable diffusion", "文生图提示词",
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

INTENT_PRIORITY = ("review", "image", "coding", "translate", "summarize", "marketing",
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
    "image": ("图像提示词", "image prompt"),
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
    ("zh", "subject"): "画面上要出现什么主体？请说清对象、数量与状态（如「一位骑车穿过老街的年轻人」）。",
    ("en", "audience"): "Who is the audience? Role, seniority, and what they care about.",
    ("en", "tone"): "What tone and style? e.g. formal, conversational, punchy sales copy.",
    ("en", "length"): "What is the length budget? e.g. under 300 words, 800-1200 words.",
    ("en", "format"): "What output structure? Markdown bullets, table, JSON, or final copy.",
    ("en", "context"): "What context must be respected? Positioning, source material, banned terms.",
    ("en", "success"): "How do we judge success? Give 2-3 checkable acceptance criteria.",
    ("en", "input"): "What source material should be processed? Paste the text or key data.",
    ("en", "scope"): "What are the boundaries? Must-include vs. explicitly exclude.",
    ("en", "channel"): "Where will this be published? Length, hook and CTA differ sharply per channel.",
    ("en", "subject"): "What exactly should appear in the frame? Name the object, count and state.",
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
    # 图像只有一个真正必须问的槽位：主体。其余一律走默认值（规范 §6）。
    "image": ("subject",),
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
    # 仅 intent=image 时非空：8 段切分、默认值来源、裁剪记录与安全结论（契约 §9.2）
    image: dict | None = None

    def constraint_values(self, kind: str) -> list[str]:
        return [c.value for c in self.constraints if c.kind == kind]

    def as_dict(self) -> dict:
        data = {
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
        if self.image is not None:
            data["image"] = self.image
        return data


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
    # 图像场景只有主体必须问：能从原话剥出主体就不再追问（规范 §6）
    if intent == "image" and len(re.sub(r"\s+", "", text)) >= 4:
        have.add("subject")

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


# ---------------------------------------------------------------- 图像意图判定
# 「海报」「封面」既是渠道词也是产物词，单出现不足以判图像；
# 真正的判定要求「产物词 + 创作动词/视觉描述」双条件（见 _is_image_request）。
_IMAGE_PRODUCTS = ("插画", "海报", "主图", "白底图", "详情页图", "商品图", "产品图",
                   "封面", "头像", "人设", "立绘", "壁纸", "概念图", "分镜图", "配图",
                   "图片", "图像", "画面", "主视觉", "展板", "易拉宝", "效果图", "图标")
_IMAGE_VERBS = ("画", "绘制", "生成图", "出图", "做一张", "做张", "来一张", "出一张",
                "设计一", "渲染", "美化", "重绘")
# 强产物词：出现即视为图像需求，不必再配动词（「保温杯的白底主图」这类省略句很常见）
_IMAGE_STRONG_PRODUCTS = ("白底主图", "白底图", "主图", "详情页图", "商品图", "产品图",
                          "人设图", "立绘", "概念图", "分镜图", "宣传图", "配图", "主视觉",
                          "插画", "头像", "壁纸", "展板", "易拉宝", "封面", "海报")
_IMAGE_STRONG = re.compile(r"画(一|个|只|幅|张|两|三)|绘制|出图|文生图|生成图片|"
                           r"midjourney|sdxl|stable diffusion|"
                           r"\b(draw|illustration|poster|concept art|avatar|wallpaper|"
                           r"generate an image|image of|photo of)\b")
# 产出是文字而非图的诉求：即使出现「海报/封面」也不走图像分支。
# 注意别把「标题」放进来自动否决——「留标题位」是排版需求，正是图像场景。
_TEXT_ONLY = ("文案", "脚本", "口号", "slogan", "推文", "详情页文案", "起个标题", "写标题")
# 结构化图表不是图像生成，命中即退出（否则「画个流程图」会被判成文生图）
_TEXT_BLOCK = ("流程图", "架构图", "思维导图", "拓扑图", "表格", "示意图")


def _is_image_request(text: str) -> bool:
    # 「留出文案区」是排版需求，不是要写文案：先摘掉这类短语再判文本诉求
    lowered = text.lower()
    for phrase in ("文案区", "文案位", "文案空间", "留白区"):
        lowered = lowered.replace(phrase, "")
    if any(w in lowered for w in _TEXT_BLOCK):
        return False
    product = any(w in lowered for w in _IMAGE_PRODUCTS)
    verb = any(w in lowered for w in _IMAGE_VERBS)
    strong = bool(_IMAGE_STRONG.search(lowered))
    text_only = any(w in lowered for w in _TEXT_ONLY)
    if text_only and not strong:
        return False
    if any(w in lowered for w in _IMAGE_STRONG_PRODUCTS):
        return True
    matched = visual.match_terms(lowered, visual.pick_scene(lowered))
    if strong and (product or matched):
        return True
    if strong and len(lowered) >= 4:
        return True
    return product and (verb or bool(matched))


# ---------------------------------------------------------------- 图像 8 段规划
# 每段只给「术语 + 一句限定」，避免为凑长度堆同义形容词（规范 §5 裁剪顺序）。
_QUALIFIER = {
    "composition": {"default": "主体位置明确，四周留出安全边距，画面重心稳定",
                    "EC": "主体居中，无裁切，倒影与投影自然",
                    "MK": "主体落在视觉焦点，另一侧留出约三分之一版面的文案区，前景不遮挡主体",
                    "AV": "主体居中，四周不切边，肩线完整",
                    "PS": "中央与边角留出排版空间，主体不压字"},
    "lighting": {"default": "光线方向明确，阴影有层次，高光不溢出、暗部保留细节",
                 "EC": "布光均匀，产品轮廓清晰，高光柔和不过曝",
                 "MK": "暖色温，光影过渡自然，主体与背景分离，曝光准确",
                 "IL": "色温统一，氛围与主题一致，明暗层次清晰",
                 "CD": "光比控制得当，暗部保留细节，光源方向可辨"},
    "style": {"default": "质感真实，色彩克制，整体色调统一"},
    # 插画/3D/像素等非摄影媒介：套「质感真实」会自相矛盾（盲评中 AV 场景因此掉分）
    "style_illus": {"default": "笔触与色块关系清晰，色彩克制，整体色调统一"},
    "texture": {"default": "表面质感清晰，细节可辨，高光与纹理过渡自然"},
}
# 这些词本身已是完整短语，不再追加「构图」后缀
_COMP_AS_IS = {"负空间", "中心留空", "版式留白", "上方留白", "右侧留白", "左侧留白",
               "浅景深", "深景深", "平视", "仰视", "俯视", "鸟瞰", "前景层次",
               "框架构图"}
# 英文输入的默认文案：中文短语不可机翻，改用等价的英文短语，避免中英混排
_SHOT_EN = {"平视中景": "eye-level medium shot", "平视特写": "eye-level close-up",
            "平视近景": "eye-level close shot", "平视全景": "eye-level full shot",
            "平视远景": "eye-level long shot"}
_SETTING_EN = {"MK": "outdoor natural setting with a clean backdrop",
               "EC": "pure white seamless backdrop, no props",
               "IL": "simple background that keeps the subject dominant",
               "AV": "light grey solid backdrop",
               "PS": "gradient backdrop with empty space for layout",
               "CD": "detailed real-world environment",
               "general": "uncluttered background"}
_ZH_LIMIT = 260          # 中文上限：多元素场景（规范 §5）
_ZH_LIMIT_SINGLE = 220   # 中文上限：单主体/纯背景场景（EC / AV / PS）
_SINGLE_SCENES = ("EC", "AV", "PS")
_PREFERRED_PLATFORM_LEN = {"generic": (120, 260), "mj": (40, 120), "flux": (45, 120),
                           "dalle3": (120, 600), "sdxl": (30, 75)}


def _comp_phrase(term: str) -> str:
    if term in _COMP_AS_IS or term.endswith("构图") or term.endswith("视角"):
        return term
    return term + "构图"


def _dedupe(items: Iterable[str]) -> list[str]:
    out: list[str] = []
    for item in items:
        if item and item not in out:
            out.append(item)
    return out


def _unbanned(term: str, banned_forms: set[str]) -> str:
    """被禁配命中的词不能再回填正文（否则等于把禁用词又塞回去）。"""
    if not term:
        return ""
    return "" if any(form in term or term in form for form in banned_forms) else term


def _image_plan(text: str, lang: str, domain: str, platform: str = "generic",
                ratio: str | None = None) -> dict:
    """把一句话拆成 8 段：命中优先、缺省按场景补，并记录默认值与裁剪。"""
    lowered = text.lower()
    zh = lang != "en"
    scene = visual.pick_scene(lowered)
    matched = visual.match_terms(lowered, scene)
    # 主体维命中（建筑外观/风光/食物特写）会被用户主体覆盖；画质维（干净背景/胶片颗粒）
    # 此前没有任何段落承接。两者先留副本，禁配过滤后再按真实维度归位，而不是静默丢弃。
    raw_subject = matched.get("subject", "")
    raw_quality = matched.get("quality", "")
    matched["subject"] = visual.extract_subject(text)
    preferred = visual.DOMAIN_STYLE.get(domain, ("", ()))[0]
    defaults: list[str] = []
    warnings: list[dict] = []
    trims: list[str] = []
    domain_label = DOMAIN_LABEL.get(domain, (domain,))[0]

    # 领域禁配（映射表第 5 列）：判据是「输入命中禁配词」而不是「style 槽位是否在 ban 列表」——
    # 禁配列里有光线（低调）、镜头（鱼眼镜头）、材质（做旧）、负面（恐怖元素）等跨维度词，
    # 只比对 style 会让它们照进正文。命中即从所有命中维度清除，风格维再补领域首选。
    conflicts = visual.banned_hits(lowered, domain)
    for doc_term, forms in conflicts:
        hit = []
        for dim, value in list(matched.items()):
            if not value:
                continue
            if dim == "subject":
                # 主体里的风格词是描述而非主体本身（「金融发布会的赛博朋克海报」），按词剔除；
                # 整个主体就是禁配词时才连主体一起丢（交由下方占位逻辑补场景名）
                for form in forms:
                    value = value.replace(form, "")
                value = value.strip(" 的，,、")
                if value:
                    matched["subject"] = value
                else:
                    hit.append(dim)
                continue
            if any(form in value or value in form for form in forms):
                hit.append(dim)
        for dim in hit:
            matched.pop(dim, None)
        if "style" in hit and preferred:
            matched["style"] = preferred
            defaults.append("style")
            warnings.append({"type": "style_conflict",
                             "text": f"「{doc_term}」与{domain_label}场景的视觉调性冲突，"
                                     f"已替换为「{preferred}」；如需保留原风格请明确说明。"})
        else:
            warnings.append({"type": "style_conflict",
                             "text": f"「{doc_term}」与{domain_label}场景的视觉调性冲突，"
                                     f"已从提示词中移除；如需保留请明确说明。"})

    # 禁配命中过的词即使来自主体/画质维也不能回填（否则等于把禁用词又塞回正文）
    banned_forms = {form for _term, forms in conflicts for form in forms}
    if not matched.get("subject"):
        # 用户没说主体、但点到了主体维词（「做一张…建筑外观」）：直接当主体，比场景名占位更准
        fallback = _unbanned(raw_subject, banned_forms)
        if fallback:
            matched["subject"] = fallback
        else:
            # 整句只有「做一张 9:16 竖版海报」这类壳 + 比例词：用场景名占位并留痕，
            # 而不是把比例词当主体（「9:16竖版，渐变背景…」读起来是残句）
            matched["subject"] = visual.SCENES[scene][0 if zh else 1]
            warnings.append({"type": "missing_subject",
                             "text": "未识别到具体主体，已用场景名占位，建议补充主体描述"})
    subject_hit = _unbanned(raw_subject, banned_forms)
    quality_hit = _unbanned(raw_quality, banned_forms)
    matched.pop("quality", None)

    # 口语 → 术语：形容词不可执行，只在对应维度空缺时补位，不覆盖用户明确指定
    for word, (dim, term) in visual.SPOKEN_MAP.items():
        if word in lowered and dim not in matched:
            matched[dim] = term
            warnings.append({"type": "spoken", "text": f"「{word}」转译为「{term}」"})

    scene_default = visual.SCENE_DEFAULT.get(scene, {})
    # 景别优先取用户点名的镜头词（大特写/航拍…），否则用场景默认机位
    lens = matched.get("lens")
    shot = lens or visual.SCENE_SHOT.get(scene, "平视中景")
    shot_en = visual.to_en(lens) if lens else _SHOT_EN.get(shot, "eye-level medium shot")
    segs: dict[str, str] = {}
    for seg in visual.SEGMENT_ORDER:
        if seg in ("negative", "technical"):
            continue
        term = matched.get(seg)
        is_default = False
        if not term:
            # S6 选填：非必填场景且无场景默认材质时留空，避免为凑长度堆材质词
            if (seg == "texture" and scene not in visual.TEXTURE_REQUIRED
                    and not scene_default.get(seg)):
                continue
            # 场景默认优先于领域首选：插画/海报的媒介比行业调性更决定画面形态
            term = scene_default.get(seg) or (preferred if seg == "style" else None)
            if not term:
                continue
            is_default = True
        if is_default:
            defaults.append(seg)
        if seg == "subject":
            segs[seg] = term
        elif not zh:
            head = _SETTING_EN.get(scene, _SETTING_EN["general"]) if (seg == "setting" and is_default) \
                else visual.to_en(term)
            segs[seg] = f"{head}, {shot_en}" if seg == "composition" else head
        else:
            key = ("style_illus" if (seg == "style" and term in visual.ILLUSTRATION_STYLES)
                   else seg)
            qualifier = _QUALIFIER.get(key, {}).get(scene) or _QUALIFIER.get(key, {}).get("default", "")
            head = _comp_phrase(term) if seg == "composition" else term
            if seg == "texture" and term in segs.get("subject", ""):
                # 主体里已写明材质（如「磨砂玻璃香水瓶」），S6 再复述一遍就是冗余
                segs[seg] = qualifier or head
            else:
                segs[seg] = f"{head}，{qualifier}" if qualifier else head
            if seg == "composition":
                segs[seg] = f"{segs[seg]}，{shot}"

    # 主体维命中与用户主体并存时（「房产」+「建筑外观」），挂到环境段而不是丢掉：
    # 它描述的是画面里有什么，放进 S2 读得通，塞进 S5 就会被当成风格误判。
    if subject_hit and subject_hit != matched.get("subject"):
        head = subject_hit if zh else visual.to_en(subject_hit)
        holder = "setting" if segs.get("setting") else "composition"
        if holder in segs:
            segs[holder] = f"{head}，{segs[holder]}" if zh else f"{head}, {segs[holder]}"

    # 纯色/无缝背景 + 浅景深 是互斥组合：背景本来就没东西可虚化
    if zh and "浅景深" in segs.get("composition", "") and (
            "纯色" in segs.get("setting", "") or "无缝" in segs.get("setting", "")):
        base = _comp_phrase(visual.SCENE_DEFAULT[scene]["composition"])
        qual = _QUALIFIER["composition"].get(scene) or _QUALIFIER["composition"]["default"]
        segs["composition"] = f"{base}，{qual}，{shot}"
        trims.append("shallow_dof_conflict")

    resolved_ratio = visual.pick_ratio(lowered, scene, ratio)
    # 画质维（干净背景/胶片颗粒/8K…）此前无处可去：命中即丢。技术参数段是它唯一的自然归宿。
    # 用 _dedupe 拼装：「高分辨率」既可能是用户说的（高清），也可能是模板自带，不能写两遍。
    if zh:
        segs["technical"] = "，".join(_dedupe(
            [f"{resolved_ratio} 画幅", quality_hit, "高分辨率", "细节清晰", "边缘干净", "构图完整"]))
    else:
        segs["technical"] = ", ".join(_dedupe(
            [f"{resolved_ratio} frame", visual.to_en(quality_hit) if quality_hit else "",
             "high resolution", "crisp details", "clean edges"]))

    # 灰区风格（映射表第 4 列）：保留但说清「什么条件下才成立」——
    # 「电影感」不限定就是高对比大片，「像素艺术」放进 K12 课件则跑偏。
    # 必须在 S7 之后跑：灰区词可能落在 technical（画质维）或 lighting（光线维），
    # 且文档写法与引擎主词可能不同（「暗调低调」→「低调」），按主词一起找 holder。
    gray_label = DOMAIN_LABEL.get(domain, (domain,))[0]
    for term, (mode, note) in visual.DOMAIN_STYLE_GRAY.get(domain, {}).items():
        forms = (term, visual.TERM_CANON.get(term, term))
        holder = next((key for key, value in segs.items()
                       if any(form and form in value for form in forms)), None)
        if holder is None:            # 没命中（或已被互斥/裁剪处理掉）就不硬塞
            continue
        if mode == "q":
            if note and note not in segs[holder]:
                segs[holder] = f"{segs[holder]}，{note}"
            warnings.append({"type": "style_gray",
                             "text": f"「{term}」在{gray_label}场景需限定，已补充「{note}」"})
        else:
            warnings.append({"type": "style_gray",
                             "text": f"「{term}」在{gray_label}场景仅适用于：{note}"})

    # 人物负面按需追加：核心 3 条 → 提到手才加手指类 → 提到皮肤才加磨皮类
    person_negative: list[str] = []
    if visual.has_person(lowered):
        person_negative += list(visual.PERSON_CORE_NEGATIVE)
        if "手" in lowered:
            person_negative += list(visual.HAND_NEGATIVE)
        if any(word in lowered for word in visual.SKIN_HINTS):
            person_negative += list(visual.SKIN_NEGATIVE)
    negatives = _dedupe(list(visual.BASE_NEGATIVE) + person_negative
                        + list(visual.SCENE_NEGATIVE.get(scene, ())))
    segs["negative"] = ("、".join(negatives) if zh
                        else ", ".join(visual.to_en(n) for n in negatives))

    # 长度兜底：超限按「S6 → S3 修饰 → S7 修饰」顺序裁，永不裁主体与通用负面
    def _body_len() -> int:
        # 与规范同口径：正文 + 「；避免 」+ 负面，不含平台参数
        body = "，".join(v for key, v in segs.items() if key != "negative")
        return len(body) + 3 + len(segs.get("negative", ""))

    limit = _ZH_LIMIT_SINGLE if scene in _SINGLE_SCENES else _ZH_LIMIT
    if zh and _body_len() > limit:
        for key in ("texture", "composition"):
            if key in segs:
                trims.append(key)
                segs.pop(key)
                break
    if zh and _body_len() > limit and len(segs["technical"]) > 24:
        segs["technical"] = f"{resolved_ratio} 画幅，高分辨率，细节清晰"
        trims.append("technical_quality")

    blocked, soft = visual.check_safety(lowered)
    # 命中的术语按维度透出：前端 chips 要显示「风格/构图/光线」，
    # 从 segments 文本里反解不可靠（限定句会混进同一条字符串）。
    picks = {dim: matched[dim] for dim in ("style", "lighting", "composition", "lens", "texture")
             if matched.get(dim)}
    return {
        "scene": scene,
        "scene_label": visual.SCENES[scene][0 if zh else 1],
        "platform": platform,
        "ratio": resolved_ratio,
        "picks": picks,
        "segments": segs,
        "defaults": _dedupe(defaults),
        "trims": _dedupe(trims),
        "warnings": warnings[:4],
        "safety": {"blocked": bool(blocked), "reasons": blocked, "rewrites": soft},
    }


def analyze(text: str, lang: str = "auto", platform: str = "generic",
            ratio: str | None = None, enable_image: bool = True) -> Analysis:
    raw = (text or "").strip()
    resolved_lang = detect_lang(raw) if lang in (None, "", "auto") else (
        "en" if lang.startswith("en") else "zh")
    lowered = raw.lower()

    intent_scores = _score_hits(lowered, INTENT_KEYWORDS)
    domain_scores = _score_hits(lowered, DOMAIN_KEYWORDS)
    intent = _pick(intent_scores, INTENT_PRIORITY, "general")
    # 关键词只做初筛：「画个流程图」会命中 image 词，但双条件不成立，回退到次优意图
    if intent == "image" and not _is_image_request(lowered):
        intent_scores.pop("image", None)
        intent = _pick(intent_scores, INTENT_PRIORITY, "general")
    if intent != "review" and any(marker in lowered for marker in REVIEW_MARKERS):
        intent = "review"
    elif intent == "coding" and any(marker in lowered for marker in SCRIPT_MARKERS):
        intent = "writing"
    # 灰度开关关闭时不识别图像意图：请求回落到原文本增强行为（计划 §5.5 回滚路径）
    if not enable_image:
        intent_scores.pop("image", None)
        if intent == "image":
            intent = _pick(intent_scores, INTENT_PRIORITY, "general")
    # 图像意图放在评审之后：写「评审这张海报」仍走 review，不因产物词改判
    elif intent != "review" and _is_image_request(lowered):
        intent = "image"
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
    if intent == "image":
        analysis.image = _image_plan(raw, resolved_lang, domain, platform, ratio)
    analysis.missing = _find_missing(intent, resolved_lang, constraints, raw)
    analysis.risks = _find_risks(raw, resolved_lang, constraints)
    return analysis
