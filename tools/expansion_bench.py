"""模板库扩充前后的效果对比基准。

用法：
    py tools/expansion_bench.py          # 打印对比表
    py tools/expansion_bench.py --json   # 机器可读结果

为什么这个对比可信（而不是「凭感觉写个数」）：
    1. 「扩充前」不是近似值：扩充前的词表原样快照在下方，再走**同一套打分函数**
       （analyzer._score_hits / _pick）复算，新旧差异只来自词表与匹配策略。
    2. 「扩充前的输出」通过临时清空 renderer.OUTLINES 重新渲染得到，
       其余渲染逻辑完全一致，字符数差异只来自成品骨架。
    3. 语料固定、指标确定，可重复；tests/test_expansion.py 直接复用本模块并断言不退化。
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))

from engine import enhance  # noqa: E402
from engine import renderer  # noqa: E402
from engine.analyzer import (  # noqa: E402
    CHANNEL_WORDS, DOMAIN_KEYWORDS, DOMAIN_PRIORITY, INTENT_KEYWORDS, INTENT_PRIORITY,
    REVIEW_MARKERS, TONE_WORDS, _pick, _score_hits, analyze,
)
from engine.scorer import score  # noqa: E402
from engine.templates import OUTLINES  # noqa: E402

# ---------------------------------------------------------------- 扩充前快照
BASELINE_DOMAINS: dict[str, tuple[str, ...]] = {
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
}

BASELINE_DOMAIN_PRIORITY = ("auto", "energy", "tech", "medical", "legal", "finance", "research",
                            "manufacturing", "ecommerce", "education", "hr", "game",
                            "realestate", "travel", "food", "marketing", "general")

BASELINE_TONES = {
    "正式": "正式", "严谨": "严谨", "专业": "专业", "口语": "口语化", "轻松": "轻松",
    "幽默": "幽默", "亲切": "亲切", "简洁": "简洁", "学术": "学术", "犀利": "犀利",
    "温暖": "温暖", "高级感": "高级感", "活泼": "活泼", "理性": "理性",
    "克制": "克制", "权威": "权威", "治愈": "治愈", "硬核": "硬核",
    "温柔": "温柔", "煽动": "煽动性", "official": "正式", "casual": "口语化",
    "professional": "专业", "concise": "简洁",
}

BASELINE_CHANNELS = {
    "小红书": "小红书", "公众号": "微信公众号", "抖音": "抖音", "知乎": "知乎",
    "微博": "微博", "朋友圈": "朋友圈", "官网": "官网", "短视频": "短视频",
    "直播": "直播", "邮件": "邮件", "ppt": "PPT", "海报": "海报", "banner": "Banner",
    "视频号": "微信视频号", "b站": "B站", "bilibili": "B站", "快手": "快手",
    "linkedin": "LinkedIn", "instagram": "Instagram", "tiktok": "TikTok",
    "短信": "短信", "新闻稿": "新闻稿", "白皮书": "白皮书", "播客": "播客",
    "落地页": "落地页", "详情页": "商品详情页",
}

# ---------------------------------------------------------------- 固定语料
# (文本, 期望领域 | "", 期望渠道列表, 期望语气列表)
CORPUS: list[tuple[str, str, list[str], list[str]]] = [
    # —— 扩充前已支持的 16 个领域：守住「不回归」——
    ("帮我写个新能源汽车的营销文案", "energy", [], []),
    ("写个 python 函数合并两个字典", "tech", [], []),
    ("策划一场品牌小红书的种草活动", "marketing", ["小红书"], []),
    ("优化电商店铺的 SKU 结构与复购", "ecommerce", [], []),
    ("设计一份初中数学的教案", "education", [], []),
    ("分析一份基金产品的风险与收益", "finance", [], []),
    ("给患者写一份术后护理科普", "medical", [], []),
    ("起草一份劳动仲裁的答辩状", "legal", [], []),
    ("调整游戏的数值平衡与抽卡概率", "game", [], []),
    ("写一份招聘 JD 与面试问题", "hr", [], []),
    ("整理一份产线良率提升的精益改善方案", "manufacturing", [], []),
    ("写一段新能源汽车的试驾活动文案", "auto", [], []),
    ("设计一条三天两晚的杭州亲子旅游行程", "travel", [], []),
    ("给新开的川菜馆写外卖平台的门店介绍", "food", [], []),
    ("写一篇楼盘开盘的微信公众号推文", "realestate", ["微信公众号"], []),
    ("帮我起草一份课题申报书的立项依据", "research", [], []),
    # —— 扩充分新增的 6 个领域 ——
    ("写一份内网渗透测试报告，标注漏洞影响面", "security", [], []),
    ("优化华东区域的冷链仓储与配送时效", "logistics", [], []),
    ("起草一份街道办的惠民政策解读公告", "government", [], []),
    ("整理客服客诉话术，覆盖退换货场景", "service", [], []),
    ("写一份水稻种植的病虫害防治方案", "agriculture", [], []),
    ("拆分一条 60 秒短剧的分镜脚本", "media", [], []),
    # —— 渠道：旧词组合（旧实现只取第一个）与新词 ——
    ("把技术文章发到掘金和 GitHub 上", "", ["掘金", "GitHub"], []),
    ("通知同步到企业微信，再走站内信", "", ["企业微信", "站内信"], []),
    ("做成信息流广告，配合开屏曝光", "", ["信息流广告", "开屏广告"], []),
    ("这条内容发小红书，同时发公众号", "", ["小红书", "微信公众号"], []),
    ("这条内容发朋友圈和抖音", "", ["朋友圈", "抖音"], []),
    ("做成短视频，再剪成播客", "", ["短视频", "播客"], []),
    # —— 语气：长词与多值 ——
    ("语气要冷幽默一点", "", [], ["冷幽默"]),
    ("语气既真诚又干练", "", [], ["真诚", "干练"]),
    ("风格要接地气，写出烟火气", "", [], ["接地气", "烟火气"]),
    ("语气要克制但温暖", "", [], ["克制", "温暖"]),
    ("语气正式，面向企业客户", "", [], ["正式"]),
]

MARKETING_PROBE = "帮我写个关于新能源汽车的营销文案，要发小红书"
PERF_TEXT = ("帮我写一篇关于新能源汽车的推广文章，面向家庭用户，语气亲切，"
             "字数控制在 800 字以内，发在公众号上，需要包含三个卖点与行动号召。") * 6
PERF_TEXT = PERF_TEXT[:320]


def baseline_domain(text: str) -> str:
    """复刻扩充前的领域判定：同一打分函数 + 旧词表 + 旧优先级。"""
    return _pick(_score_hits(text.lower(), BASELINE_DOMAINS), BASELINE_DOMAIN_PRIORITY, "general")


def baseline_intent(text: str) -> str:
    """复刻扩充前的意图判定：仅保留评审强信号，没有脚本类改判。"""
    lowered = text.lower()
    intent = _pick(_score_hits(lowered, INTENT_KEYWORDS), INTENT_PRIORITY, "general")
    if intent != "review" and any(marker in lowered for marker in REVIEW_MARKERS):
        intent = "review"
    return intent


def baseline_labels(text: str, table: dict[str, str]) -> list[str]:
    """复刻扩充前的渠道/语气判定：按字典顺序取第一个命中即停。"""
    lowered = text.lower()
    for word, label in table.items():
        if word in lowered:
            return [label]
    return []


def _hits(expected: list[str], actual: list[str]) -> tuple[int, int]:
    return sum(1 for item in expected if item in actual), len(expected)


def _render_without_outline(payload: dict) -> str:
    """临时清空骨架表后渲染，等价于扩充前的输出。"""
    saved = renderer.OUTLINES
    renderer.OUTLINES = {}
    try:
        return enhance(payload)["enhanced"]
    finally:
        renderer.OUTLINES = saved


def run_bench(perf_rounds: int = 300) -> dict:
    domain_old = domain_new = labeled = 0
    ch_hit_old = ch_hit_new = ch_total = 0
    tone_hit_old = tone_hit_new = tone_total = 0
    intent_changes: list[dict] = []

    for text, exp_domain, exp_channels, exp_tones in CORPUS:
        analysis = analyze(text)
        if exp_domain:
            labeled += 1
            domain_old += baseline_domain(text) == exp_domain
            domain_new += analysis.domain == exp_domain
        old_intent, new_intent = baseline_intent(text), analysis.intent
        if old_intent != new_intent:
            intent_changes.append({"text": text, "old": old_intent, "new": new_intent})
        if exp_channels:
            hit, total = _hits(exp_channels, baseline_labels(text, BASELINE_CHANNELS))
            ch_hit_old += hit
            ch_total += total
            hit, _ = _hits(exp_channels, analysis.constraint_values("channel"))
            ch_hit_new += hit
        if exp_tones:
            hit, total = _hits(exp_tones, baseline_labels(text, BASELINE_TONES))
            tone_hit_old += hit
            tone_total += total
            hit, _ = _hits(exp_tones, analysis.constraint_values("tone"))
            tone_hit_new += hit

    new_out = enhance({"text": MARKETING_PROBE})["enhanced"]
    old_out = _render_without_outline({"text": MARKETING_PROBE})

    start = time.perf_counter()
    for _ in range(perf_rounds):
        baseline_domain(PERF_TEXT)
    domain_old_ms = (time.perf_counter() - start) * 1000 / perf_rounds

    start = time.perf_counter()
    for _ in range(perf_rounds):
        _pick(_score_hits(PERF_TEXT.lower(), DOMAIN_KEYWORDS), DOMAIN_PRIORITY, "general")
    domain_new_ms = (time.perf_counter() - start) * 1000 / perf_rounds

    start = time.perf_counter()
    for _ in range(perf_rounds):
        analyze(PERF_TEXT)
    analyze_ms = (time.perf_counter() - start) * 1000 / perf_rounds

    return {
        "corpus_size": len(CORPUS),
        "labeled_domains": labeled,
        "domain_old": domain_old,
        "domain_new": domain_new,
        "domain_accuracy_old": round(domain_old / labeled, 3),
        "domain_accuracy_new": round(domain_new / labeled, 3),
        "channel_recall_old": round(ch_hit_old / ch_total, 3),
        "channel_recall_new": round(ch_hit_new / ch_total, 3),
        "channel_hits_new": f"{ch_hit_new}/{ch_total}",
        "tone_recall_old": round(tone_hit_old / tone_total, 3),
        "tone_recall_new": round(tone_hit_new / tone_total, 3),
        "tone_hits_new": f"{tone_hit_new}/{tone_total}",
        "intent_changes": intent_changes,
        "channel_slot_enforced": "channel" in {m["slot"] for m in analyze("写个文案").missing},
        "vocab": {
            "domains_old": len(BASELINE_DOMAINS),
            "domains_new": len(DOMAIN_KEYWORDS),
            "channels_old": len(BASELINE_CHANNELS),
            "channels_new": len(CHANNEL_WORDS),
            "tones_old": len(BASELINE_TONES),
            "tones_new": len(TONE_WORDS),
            "skeleton_intents": len(OUTLINES),
            "skeleton_items": sum(len(v["zh"]) for v in OUTLINES.values()),
        },
        "output": {
            "chars_old": len(old_out),
            "chars_new": len(new_out),
            "delta_chars": len(new_out) - len(old_out),
            "score_old": score(old_out)["total"],
            "score_new": score(new_out)["total"],
        },
        "latency": {
            "domain_scan_old_ms": round(domain_old_ms, 3),
            "domain_scan_new_ms": round(domain_new_ms, 3),
            "full_analyze_ms": round(analyze_ms, 2),
        },
    }


def format_report(r: dict) -> str:
    v = r["vocab"]
    lines = [
        "## 识别层",
        f"- 领域准确率：{r['domain_old']}/{r['labeled_domains']}"
        f"（{r['domain_accuracy_old']:.0%}）→ {r['domain_new']}/{r['labeled_domains']}"
        f"（{r['domain_accuracy_new']:.0%}）",
        f"- 渠道召回：{r['channel_recall_old']:.0%} → {r['channel_recall_new']:.0%}"
        f"（命中 {r['channel_hits_new']}）",
        f"- 语气召回：{r['tone_recall_old']:.0%} → {r['tone_recall_new']:.0%}"
        f"（命中 {r['tone_hits_new']}）",
        f"- 营销渠道槽位追问：{'已强制' if r['channel_slot_enforced'] else '未生效'}",
        f"- 意图判定变化：{len(r['intent_changes'])} 条"
        + ("（" + "；".join(f"{c['old']}→{c['new']}" for c in r["intent_changes"]) + "）"
           if r["intent_changes"] else ""),
        "## 词表与骨架",
        f"- 领域词典：{v['domains_old']} → {v['domains_new']}",
        f"- 渠道词表：{v['channels_old']} → {v['channels_new']}",
        f"- 语气词表：{v['tones_old']} → {v['tones_new']}",
        f"- 成品骨架：0 → {v['skeleton_intents']} 个意图 / {v['skeleton_items']} 条",
        "## 输出与开销（同一营销样例）",
        f"- 字符数：{r['output']['chars_old']} → {r['output']['chars_new']}"
        f"（{r['output']['delta_chars']:+d}）",
        f"- 自评总分：{r['output']['score_old']} → {r['output']['score_new']}",
        f"- 领域扫描：{r['latency']['domain_scan_old_ms']} ms → "
        f"{r['latency']['domain_scan_new_ms']} ms；完整 analyze："
        f"{r['latency']['full_analyze_ms']} ms",
    ]
    return "\n".join(lines)


def main() -> int:
    result = run_bench()
    if "--json" in sys.argv:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(format_report(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
