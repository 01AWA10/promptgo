"""模板库与词表的覆盖度测试。

除了验证新增领域/意图能被识别，更重要的一组断言是「结构完整性」：
任何新增的领域或意图，必须同时补齐标签、语境提示、模板字段与槽位配置，
否则会在运行时静默降级成 general。这些断言把「漏配」变成测试失败。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))

from engine import enhance  # noqa: E402
from engine.analyzer import (  # noqa: E402
    DOMAIN_KEYWORDS, DOMAIN_LABEL, DOMAIN_PRIORITY, INTENT_KEYWORDS,
    INTENT_LABEL, REQUIRED_SLOTS, analyze,
)
from engine.renderer import INTENT_DELIVERABLE, INTENT_VERB  # noqa: E402
from engine.templates import DOMAIN_HINTS, MODE_HINTS, OUTLINES, TEMPLATES  # noqa: E402

NEW_DOMAINS = [
    ("整理一份产线良率提升的精益改善方案", "manufacturing"),
    ("帮我写一段新能源汽车的试驾活动文案", "auto"),
    ("设计一条三天两晚的杭州亲子旅游行程", "travel"),
    ("给新开的川菜馆写外卖平台的门店介绍", "food"),
    ("写一篇楼盘开盘的微信公众号推文", "realestate"),
    ("帮我起草一份课题申报书的立项依据", "research"),
]

# 第三组领域：安全 / 物流 / 政务 / 客服 / 农业 / 内容制作
NEW_DOMAINS_3 = [
    ("写一份内网渗透测试报告，标注漏洞影响面", "security"),
    ("优化华东区域的冷链仓储与配送时效", "logistics"),
    ("起草一份街道办的惠民政策解读公告", "government"),
    ("整理客服客诉话术，覆盖退换货场景", "service"),
    ("写一份水稻种植的病虫害防治方案", "agriculture"),
    ("拆分一条 60 秒短剧的分镜脚本", "media"),
]

TEMPLATE_FIELDS = ("role_zh", "role_en", "steps_zh", "steps_en",
                   "output_zh", "output_en", "selfcheck_zh", "selfcheck_en")


class DomainCoverageTestCase(unittest.TestCase):
    def test_new_domains_detected(self):
        for text, expected in NEW_DOMAINS:
            self.assertEqual(analyze(text).domain, expected, f"未能识别：{text}")

    def test_specific_domain_wins_over_generic(self):
        """「新能源汽车试驾」同时命中 energy 与 auto，应取更具体的 auto。"""
        self.assertEqual(analyze("帮我写一段新能源汽车的试驾活动文案").domain, "auto")
        self.assertEqual(analyze("帮我写个关于新能源汽车的营销文案").domain, "energy")

    def test_every_domain_has_label_hint_and_priority(self):
        for key in DOMAIN_KEYWORDS:
            self.assertIn(key, DOMAIN_LABEL, f"{key} 缺少 DOMAIN_LABEL")
            self.assertIn(key, DOMAIN_HINTS, f"{key} 缺少 DOMAIN_HINTS")
            self.assertIn(key, DOMAIN_PRIORITY, f"{key} 未加入 DOMAIN_PRIORITY")
        self.assertIn("general", DOMAIN_LABEL)
        self.assertIn("general", DOMAIN_HINTS)

    def test_domain_hint_injected_into_constraints(self):
        result = enhance({"text": "整理一份产线良率提升的精益改善方案"})
        self.assertIn("制造与供应链", result["enhanced"])
        self.assertEqual(result["analysis"]["domain"], "manufacturing")


class IntentCoverageTestCase(unittest.TestCase):
    def test_review_intent(self):
        analysis = analyze("评审这段 Python 代码的并发安全问题")
        self.assertEqual(analysis.intent, "review")
        self.assertEqual(analysis.intent_label, "评审与走查")

    def test_product_intent(self):
        analysis = analyze("写一份会员积分体系的 PRD，包含验收标准")
        self.assertEqual(analysis.intent, "product")

    def test_review_marker_overrides_content_intent(self):
        """带「评审」字样的写作类请求也要走 review，而不是 writing。"""
        self.assertEqual(analyze("评审一下这份活动方案的文案").intent, "review")

    def test_every_intent_has_all_assets(self):
        for key in INTENT_KEYWORDS:
            self.assertIn(key, TEMPLATES, f"{key} 缺少模板")
            self.assertIn(key, INTENT_LABEL, f"{key} 缺少标签")
            self.assertIn(key, INTENT_VERB, f"{key} 缺少动词")
            self.assertIn(key, INTENT_DELIVERABLE, f"{key} 缺少交付物描述")
            self.assertIn(key, REQUIRED_SLOTS, f"{key} 缺少必填槽位")
            for name in TEMPLATE_FIELDS:
                self.assertIn(name, TEMPLATES[key], f"{key} 模板缺少 {name}")

    def test_template_steps_are_bilingual_and_paired(self):
        for key, tpl in TEMPLATES.items():
            self.assertEqual(len(tpl["steps_zh"]), len(tpl["steps_en"]),
                             f"{key} 的中英步骤数量不一致")
            self.assertGreaterEqual(len(tpl["steps_zh"]), 4, f"{key} 步骤过少")
            self.assertGreaterEqual(len(tpl["selfcheck_zh"]), 3, f"{key} 自检项过少")

    def test_every_mode_has_hint(self):
        for mode in ("struct", "concise", "creative", "academic", "code", "agent"):
            self.assertIn(mode, MODE_HINTS)
            self.assertIn("zh", MODE_HINTS[mode])
            self.assertIn("en", MODE_HINTS[mode])


class ConstraintExpansionTestCase(unittest.TestCase):
    def test_new_channels(self):
        cases = {
            "发在视频号": "微信视频号",
            "投稿到B站": "B站",
            "写成新闻稿": "新闻稿",
            "做成播客": "播客",
            "放到落地页": "落地页",
        }
        for text, expected in cases.items():
            self.assertIn(expected, analyze(text).constraint_values("channel"), text)

    def test_new_tones(self):
        cases = {"语气要克制": "克制", "风格活泼一点": "活泼", "要显得权威": "权威"}
        for text, expected in cases.items():
            self.assertIn(expected, analyze(text).constraint_values("tone"), text)

    def test_review_deliverable_mentioned(self):
        result = enhance({"text": "评审这段代码的错误处理"})
        self.assertIn("问题清单", result["enhanced"])

    def test_marketing_requires_channel_slot(self):
        """渠道是营销文案的必填槽位：没说渠道时必须追问，而不是默认小红书。"""
        slots = {m["slot"] for m in analyze("写个文案").missing}
        self.assertIn("channel", slots)


class ThirdWaveTestCase(unittest.TestCase):
    def test_new_domains_detected(self):
        for text, expected in NEW_DOMAINS_3:
            self.assertEqual(analyze(text).domain, expected, f"未能识别：{text}")

    def test_security_beats_tech_on_tie(self):
        """「漏洞」「渗透测试」带技术味，平局时必须落到 security 而不是 tech。"""
        self.assertEqual(analyze("排查服务器漏洞并做渗透测试").domain, "security")

    def test_third_wave_domain_hint_injected(self):
        result = enhance({"text": "写一份内网渗透测试报告，标注漏洞影响面"})
        self.assertIn("安全与合规", result["enhanced"])

    def test_third_wave_channels(self):
        cases = {
            "发到掘金": "掘金",
            "同步到企业微信": "企业微信",
            "走站内信": "站内信",
            "做成信息流": "信息流广告",
        }
        for text, expected in cases.items():
            self.assertIn(expected, analyze(text).constraint_values("channel"), text)

    def test_multiple_channels_and_tones_in_text_order(self):
        a = analyze("发在企业微信和站内信上，语气冷幽默一点，也要真诚")
        self.assertEqual(a.constraint_values("channel")[:2], ["企业微信", "站内信"])
        self.assertEqual(a.constraint_values("tone")[:2], ["冷幽默", "真诚"])

    def test_longest_tone_wins_over_substring(self):
        """「冷幽默」不能被更短的「幽默」抢先命中。"""
        self.assertEqual(analyze("语气冷幽默").constraint_values("tone"), ["冷幽默"])

    def test_script_marker_overrides_coding(self):
        """短剧/分镜脚本虽含「脚本」二字，产出是文案，不能套工程骨架。"""
        self.assertEqual(analyze("拆分一条 60 秒短剧的分镜脚本").intent, "writing")


class OutlineTestCase(unittest.TestCase):
    def test_every_intent_has_bilingual_outline(self):
        for key in TEMPLATES:
            self.assertIn(key, OUTLINES, f"{key} 缺少意图骨架")
            zh_len = len(OUTLINES[key]["zh"])
            en_len = len(OUTLINES[key]["en"])
            self.assertEqual(zh_len, en_len, f"{key} 骨架中英条数不一致")
            self.assertGreaterEqual(zh_len, 4, f"{key} 骨架过粗")

    def test_outline_rendered_in_steps_block(self):
        result = enhance({"text": "帮我写个新能源汽车文案，发小红书"})
        steps = next(b for b in result["blocks"] if b["key"] == "steps")["body"]
        self.assertIn("输出骨架", steps)
        self.assertIn(OUTLINES["marketing"]["zh"][0], steps)

    def test_outline_follows_intent(self):
        result = enhance({"text": "写个 python 函数合并两个字典"})
        steps = next(b for b in result["blocks"] if b["key"] == "steps")["body"]
        self.assertIn("完整代码", steps)

    def test_concise_mode_skips_outline(self):
        result = enhance({"text": "帮我写个新能源汽车文案", "mode": "concise"})
        self.assertNotIn("输出骨架", result["enhanced"])

    def test_english_outline(self):
        result = enhance({"text": "Write a launch post for a new battery product"})
        self.assertIn("Output skeleton", result["enhanced"])


if __name__ == "__main__":
    unittest.main()
