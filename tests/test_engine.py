"""引擎单元测试：python -m unittest discover -s tests -v"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent.parent / "server"
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from engine import META, EnhanceError, enhance, normalize, stream  # noqa: E402
from engine.analyzer import (  # noqa: E402
    CHANNEL_WORDS, TONE_WORDS, _find_missing, _match_labels, analyze, detect_lang,
)
from engine.renderer import Profile, assemble, build_blocks  # noqa: E402
from engine.scorer import compare, score  # noqa: E402


class TestAnalysis(unittest.TestCase):
    def test_lang_detection(self):
        self.assertEqual(detect_lang("帮我写一段文案"), "zh")
        self.assertEqual(detect_lang("write me a blog post"), "en")
        self.assertEqual(detect_lang("用 Python 写个 fastapi 接口 demo"), "zh")

    def test_marketing_energy(self):
        a = analyze("帮我写个关于新能源汽车的营销文案，要发小红书")
        self.assertEqual(a.intent, "marketing")
        self.assertEqual(a.domain, "energy")
        self.assertEqual(a.topic, "新能源汽车")
        kinds = {c.kind for c in a.constraints}
        self.assertIn("channel", kinds)

    def test_coding_intent(self):
        a = analyze("写个 python 函数合并两个字典")
        self.assertEqual(a.intent, "coding")
        self.assertEqual(a.domain, "tech")

    def test_constraints_extraction(self):
        a = analyze("写一篇 800 字以内的公众号文章，语气正式，面向企业客户，输出 markdown")
        values = {(c.kind, c.value) for c in a.constraints}
        self.assertIn(("length", "800 字以内"), values)
        self.assertIn(("channel", "微信公众号"), values)
        self.assertIn(("tone", "正式"), values)
        self.assertIn(("audience", "企业客户"), values)
        self.assertIn(("format", "Markdown"), values)

    def test_missing_slots_reported(self):
        a = analyze("写个文案")
        slots = {m["slot"] for m in a.missing}
        self.assertTrue(slots)
        self.assertTrue(a.risks)

    def test_audience_not_truncated_at_ren(self):
        """「面向技术负责人」不能因为「人」被当终止符而截成「技术负责」。"""
        a = analyze("写一份渗透测试报告，面向技术负责人")
        self.assertEqual(a.constraint_values("audience"), ["技术负责人"])

    def test_vague_detection(self):
        a = analyze("随便写点东西，差不多就行，尽量好一些")
        self.assertTrue(a.vague_hits)
        self.assertTrue(any(r["level"] == "high" for r in a.risks))


class TestEnhance(unittest.TestCase):
    def test_structure_sections(self):
        r = enhance({"text": "帮我写个新能源汽车营销文案，发小红书"})
        self.assertIn("## 角色", r["enhanced"])
        self.assertIn("## 约束条件", r["enhanced"])
        self.assertIn("## 输出格式", r["enhanced"])
        self.assertIn("## 质量自检", r["enhanced"])

    def test_score_improves(self):
        r = enhance({"text": "写个文案"})
        self.assertGreater(r["score"]["after"], r["score"]["before"])
        self.assertEqual(len(r["score"]["dims"]), 5)

    def test_concise_fewer_sections(self):
        full = enhance({"text": "写个活动方案", "mode": "struct"})
        short = enhance({"text": "写个活动方案", "mode": "concise"})
        self.assertLess(len(short["blocks"]), len(full["blocks"]))

    def test_deep_has_risks_section(self):
        r = enhance({"text": "写个活动方案", "intensity": "deep"})
        keys = [b["key"] for b in r["blocks"]]
        self.assertIn("risks", keys)
        self.assertIn("questions", keys)

    def test_english_output(self):
        r = enhance({"text": "Explain how HTTP caching works to a junior developer"})
        self.assertEqual(r["analysis"]["lang"], "en")
        self.assertIn("## Role", r["enhanced"])

    def test_text_format(self):
        r = enhance({"text": "写个周报", "format": "text"})
        self.assertIn("【角色】", r["enhanced"])
        self.assertNotIn("## ", r["enhanced"])

    def test_invalid_mode_falls_back(self):
        r = enhance({"text": "测试", "mode": "nonsense"})
        self.assertEqual(r["profile"]["mode"], "struct")

    def test_empty_input_rejected(self):
        with self.assertRaises(EnhanceError):
            enhance({"text": "   "})

    def test_truncation(self):
        opts = normalize({"text": "啊" * 9000})
        self.assertEqual(len(opts["text"]), 8000)
        self.assertTrue(opts["truncated"])

    def test_deterministic(self):
        a = enhance({"text": "写个产品介绍"})["enhanced"]
        b = enhance({"text": "写个产品介绍"})["enhanced"]
        self.assertEqual(a, b)

    def test_meta_section_counts_match_blocks(self):
        """META 文案里的章节数必须等于 build_blocks 的实际块数，避免文档漂移。"""
        for item in META["intensities"]:
            expected = int(re.search(r"(\d+)\s*个章节", item["desc"]).group(1))
            blocks = enhance({"text": "写个活动方案", "intensity": item["id"]})["blocks"]
            self.assertEqual(len(blocks), expected, f"{item['id']} 章节数不符")

    def test_no_fabrication_clause_present(self):
        r = enhance({"text": "写个产品介绍"})
        self.assertIn("不得编造", r["enhanced"])

    def test_long_input_does_not_bloat_output(self):
        """长输入只应被截断引用，而不是整段复制进「目标」章节。"""
        text = "帮我写一篇关于新能源汽车的推广文章，面向家庭用户。" * 300
        self.assertGreater(len(text), 3000)
        r = enhance({"text": text})
        self.assertLess(len(r["enhanced"]), 3000)
        self.assertIn("…", r["enhanced"])
        self.assertNotIn(text[:200].strip(), r["enhanced"])


class TestStream(unittest.TestCase):
    def test_event_order_and_consistency(self):
        events = list(stream({"text": "帮我写个新能源汽车文案"}, pace=0))
        names = [e[0] for e in events]
        self.assertEqual(names[0], "stage")
        self.assertIn("analysis", names)
        self.assertIn("plan", names)
        self.assertIn("result", names)
        self.assertEqual(names[-1], "done")

        chunks = "".join(d["delta"] for e, d in events if e == "chunk")
        result = next(d for e, d in events if e == "result")["enhanced"]
        self.assertEqual(chunks, result)   # 逐字符一致，不允许用 strip 放宽

    def test_stream_equals_json_for_all_formats(self):
        """流式与一次性接口在 markdown / text、struct / concise 下必须完全一致。"""
        for fmt in ("markdown", "text"):
            for mode in ("struct", "concise"):
                payload = {"text": "帮我写个新能源汽车文案，要发小红书",
                           "format": fmt, "mode": mode}
                one_shot = enhance(payload)["enhanced"]
                events = list(stream(payload, pace=0))
                chunks = "".join(d["delta"] for e, d in events if e == "chunk")
                self.assertEqual(chunks, one_shot, f"{fmt}/{mode} 流式与一次性输出不一致")

    def test_sections_stream_in_order(self):
        events = list(stream({"text": "写个方案"}, pace=0))
        order = [d["section"] for e, d in events if e == "chunk"]
        uniq = list(dict.fromkeys(order))
        self.assertEqual(uniq[0], "role")
        self.assertEqual(uniq[-1], "questions")


class TestScore(unittest.TestCase):
    def test_vague_scores_low(self):
        self.assertLess(score("随便写点")["total"], 55)

    def test_structured_scores_higher_than_vague(self):
        text = (
            "## 角色\n你是资深编辑\n\n## 约束条件\n- 不超过 300 字\n- 禁止使用绝对化用语\n"
            "- 待确认：品牌名\n\n## 输出格式\n- Markdown\n\n## 质量自检\n- [ ] 检查事实\n"
        )
        self.assertGreater(score(text)["total"], 60)
        self.assertGreater(score(text)["total"] - score("随便写点")["total"], 20)

    def test_compare_delta(self):
        c = compare("写个文案", "## 角色\n你是文案\n## 约束条件\n- 不超过 200 字\n")
        self.assertGreater(c["delta"], 0)


class TestConstraintLimits(unittest.TestCase):
    """P2-10：多渠道/多语气不再静默丢弃，超出保留上限要能被统计出来。"""

    MULTI = ("要在小红书、抖音、知乎、微博、B站、微信公众号同时投放，"
             "语气正式、严谨、专业、简洁、亲切")

    def test_keeps_four_in_document_order(self):
        analysis = analyze(self.MULTI)
        self.assertEqual(analysis.constraint_values("channel"),
                         ["小红书", "抖音", "知乎", "微博"])
        self.assertEqual(analysis.constraint_values("tone"),
                         ["正式", "严谨", "专业", "简洁"])

    def test_reports_dropped_counts(self):
        analysis = analyze(self.MULTI)
        self.assertEqual(analysis.truncated, {"tone": 1, "channel": 2})

    def test_within_limit_reports_nothing(self):
        analysis = analyze("发到小红书和抖音，语气正式一点")
        self.assertEqual(analysis.truncated, {})
        self.assertEqual(analysis.constraint_values("channel"), ["小红书", "抖音"])

    def test_as_dict_exposes_truncated(self):
        self.assertEqual(analyze(self.MULTI).as_dict()["truncated"]["channel"], 2)


class TestContextSignal(unittest.TestCase):
    """P2-13：背景是否已给不能只看字数。

    旧实现 `len(text) > 120` 就把 context 视为已给，复读/口号式长文本会让
    最有价值的「背景」追问被跳过；改为字数 + 信息量（去重字符数/去重率）。
    """

    CONCRETE_ZH = (
        "产品是面向中小企业的报销 SaaS，目前有 1200 家客户，客单价 3000 元/年，"
        "主要竞品是分贝通与汇联易。这次要在钉钉应用市场做一轮投放，"
        "素材只有客户访谈记录和三张产品截图，预算 8 万元，周期两周。"
    )
    REPETITIVE_ZH = "我们要做好产品，服务好每一位客户，持续提升体验。" * 6
    CONCRETE_EN = (
        "Our product is an expense-management SaaS for SMBs. We have 1200 paying "
        "customers at roughly 3000 CNY per year, and our main competitors are "
        "Fenbeitong and Huilianyi. We now want a launch plan for the DingTalk app "
        "marketplace, using three customer interviews and two screenshots."
    )
    REPETITIVE_EN = "we will do our best to make it better " * 6

    def slots(self, text: str, lang: str = "zh", intent: str = "coding") -> set[str]:
        return {m["slot"] for m in _find_missing(intent, lang, [], text)}

    def test_short_text_asks_for_context(self):
        self.assertIn("context", self.slots("写个脚本"))

    def test_concrete_text_counts_as_context(self):
        self.assertNotIn("context", self.slots(self.CONCRETE_ZH))
        self.assertNotIn("context", self.slots(self.CONCRETE_EN, "en"))

    def test_repetitive_text_still_asks_for_context(self):
        """字数够但语义重复：去重字符数不足，不能算给了背景。"""
        self.assertGreater(len(self.REPETITIVE_ZH), 120)
        self.assertIn("context", self.slots(self.REPETITIVE_ZH))

    def test_filler_only_text_still_asks_for_context(self):
        self.assertIn("context", self.slots("啊" * 400))

    def test_english_repetition_still_asks_for_context(self):
        self.assertGreater(len(self.REPETITIVE_EN), 120)
        self.assertIn("context", self.slots(self.REPETITIVE_EN, "en"))

    def test_analyze_reports_context_for_vacuous_request(self):
        """端到端：复读式长请求仍应在 missing 里出现 context。"""
        text = "帮我写个 Python 脚本。" + "我们要努力做好每一个细节，持续优化。" * 8
        analysis = analyze(text)
        self.assertEqual(analysis.intent, "coding")
        self.assertIn("context", {m["slot"] for m in analysis.missing})

    def test_analyze_accepts_concrete_request(self):
        text = (
            "用 Python 写个 nginx 日志解析脚本：现有 access.log 约 2 GB，每天增量 200 MB，"
            "需要按状态码聚合、统计 Top 10 路径，输出 CSV 给运营同学，跑在 8 核 16 G 的机器上。"
        )
        analysis = analyze(text)
        self.assertEqual(analysis.intent, "coding")
        self.assertNotIn("context", {m["slot"] for m in analysis.missing})


class TestSynonymCoverage(unittest.TestCase):
    """P2-11：同义改写与英文表述不能因为「字面不同」就漏判。

    只扩充词表，不改打分与优先级；因此这些断言同时起到「防领域漂移」的作用：
    新增词若抢走了别的领域，下面的期望值会直接失败。
    """

    ZH_CASES = (
        ("帮我写一份社群运营的月度计划", "marketing"),
        ("给学员准备一份结课测试的题库", "education"),
        ("写一套二手房的挂牌文案", "realestate"),
        ("给工厂车间做一份工艺改善方案", "manufacturing"),
        ("把快递和仓库的时效问题整理成方案", "logistics"),
        ("写一份法务用的保密协议模板", "legal"),
        ("策划一场老客拉新与会员裂变活动", "marketing"),
        ("分析一下这支股票的走势", "finance"),
        ("整理一份门诊处方的合规要求", "medical"),
        ("写一份勒索软件应急响应预案", "security"),
        ("给农场写一份播种与收割的排期", "agriculture"),
        ("整理一份纪录片摄制的排期", "media"),
        ("写一份政务大厅的公共服务公告", "government"),
        ("写一份智驾功能的用户说明", "auto"),
        ("写一份餐厅的菜谱", "food"),
        ("写一份科研项目的同行评审意见", "research"),
        ("优化 k8s 集群的运维方案", "tech"),
    )
    EN_CASES = (
        ("design a solar battery system for a home", "energy"),
        ("review our kubernetes deployment and database schema", "tech"),
        ("draft a contract for a vendor with compliance notes", "legal"),
        ("plan a five-day itinerary with flight and hotel details", "travel"),
        ("write a recipe for a restaurant menu", "food"),
        ("audit our phishing response and ransomware playbook", "security"),
        ("list mortgage options for a property purchase", "realestate"),
        ("create a hiring plan for onboarding and compensation", "hr"),
        ("write a clinic prescription guide for patients", "medical"),
        ("analyze our payment and loan portfolio risk", "finance"),
        ("write a marketing funnel and lifecycle email plan", "marketing"),
    )

    def test_chinese_synonyms(self):
        for text, expected in self.ZH_CASES:
            with self.subTest(text=text):
                self.assertEqual(analyze(text).domain, expected, text)

    def test_english_terms(self):
        for text, expected in self.EN_CASES:
            with self.subTest(text=text):
                self.assertEqual(analyze(text).domain, expected, text)

    def test_channel_aliases(self):
        self.assertEqual(_match_labels("发到 rednote 和 douyin", CHANNEL_WORDS, 4),
                         ["小红书", "抖音"])
        self.assertEqual(_match_labels("press release 与 whitepaper", CHANNEL_WORDS, 4),
                         ["新闻稿", "白皮书"])

    def test_tone_aliases(self):
        self.assertEqual(_match_labels("语气 serious 一点", TONE_WORDS, 2), ["正式"])
        self.assertEqual(_match_labels("friendly and warm", TONE_WORDS, 2), ["亲切", "温暖"])


class TestSkeletonScoring(unittest.TestCase):
    """P2-9：成品骨架必须真正反映到分数上。

    旧公式里 4 个标题就把「结构性」顶到 100，骨架只能再加列表条数，
    而条数早已封顶，于是「加了骨架但分数没涨」，容易被当成增强无效。
    """

    TEXT = "给新能源车企写一条小红书文案，突出充电 5 分钟续航 300 公里"

    def _blocks(self):
        analysis = analyze(self.TEXT)
        profile = Profile(mode="struct", lang="zh", intensity="standard", fmt="markdown")
        return build_blocks(analysis, profile)

    def test_structure_keeps_headroom(self):
        result = enhance({"text": self.TEXT})
        structure = next(d for d in result["score"]["dims"] if d["key"] == "structure")
        self.assertLess(structure["after"], 100, "结构性顶满后，骨架与深度都无法体现在分数上")

    def test_skeleton_raises_structure_and_total(self):
        blocks = self._blocks()
        with_skeleton = assemble(blocks, "markdown")

        stripped = [dict(b) for b in blocks]
        for block in stripped:
            if block["key"] == "steps" and "输出骨架" in block["body"]:
                block["body"] = block["body"].split("\n输出骨架")[0].rstrip()
        without = assemble(stripped, "markdown")

        hit, miss = score(with_skeleton), score(without)
        self.assertTrue(hit["skeleton"])
        self.assertFalse(miss["skeleton"])
        self.assertGreater(hit["dims"]["structure"], miss["dims"]["structure"])
        self.assertGreater(hit["total"], miss["total"], "同素材下带骨架的总分必须严格更高")

    def test_skeleton_marker_needs_real_items(self):
        """只写一句「输出骨架」不配条目，不给分。"""
        bare = "## 角色\n你是编辑\n\n## 任务拆解\n输出骨架（成品按此顺序成文）：\n1. 做点什么\n"
        self.assertFalse(score(bare)["skeleton"])

    def test_compare_exposes_skeleton_flag(self):
        result = enhance({"text": self.TEXT})
        self.assertTrue(result["score"]["skeleton"])
        self.assertIsInstance(result["score"]["skeleton"], bool)


if __name__ == "__main__":
    unittest.main()
