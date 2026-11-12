"""扩充效果回归测试。

两类断言：
1. 新增能力本身（长词优先、不重叠、多值顺序、骨架完整性）；
2. 与扩充前快照的对比不退化——直接复用 tools/expansion_bench.py 的固定语料，
   任何「为了新词把老词挤掉」的改动都会在这里失败。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))
sys.path.insert(0, str(ROOT))

from engine import enhance  # noqa: E402
from engine.analyzer import (  # noqa: E402
    CHANNEL_WORDS, SLOT_QUESTIONS, TONE_WORDS, _match_labels, analyze,
)
from engine.templates import OUTLINES  # noqa: E402
from tools.expansion_bench import BASELINE_DOMAINS, CORPUS, run_bench  # noqa: E402


class MatchLabelTestCase(unittest.TestCase):
    def test_longest_match_wins(self):
        self.assertEqual(_match_labels("语气冷幽默", TONE_WORDS, 2), ["冷幽默"])

    def test_no_overlapping_double_count(self):
        self.assertEqual(_match_labels("发到企业微信", CHANNEL_WORDS, 2), ["企业微信"])

    def test_order_follows_text(self):
        self.assertEqual(_match_labels("先发站内信，再发小红书", CHANNEL_WORDS, 2),
                         ["站内信", "小红书"])

    def test_limit_caps_results(self):
        self.assertEqual(len(_match_labels("发到小红书、抖音和知乎", CHANNEL_WORDS, 2)), 2)


class BenchGateTestCase(unittest.TestCase):
    """扩充前后对比的硬门槛。"""

    @classmethod
    def setUpClass(cls):
        cls.result = run_bench(perf_rounds=1)

    def test_domain_accuracy_improves_to_full(self):
        self.assertEqual(self.result["domain_accuracy_new"], 1.0)
        self.assertLess(self.result["domain_accuracy_old"], self.result["domain_accuracy_new"])

    def test_channel_recall_improves(self):
        self.assertEqual(self.result["channel_recall_new"], 1.0)
        self.assertGreater(self.result["channel_recall_new"], self.result["channel_recall_old"])

    def test_tone_recall_improves(self):
        self.assertEqual(self.result["tone_recall_new"], 1.0)
        self.assertGreater(self.result["tone_recall_new"], self.result["tone_recall_old"])

    def test_intent_change_limited_to_script_case(self):
        """意图层只应有一处有意的改判：短剧/分镜脚本 coding → writing。"""
        changes = self.result["intent_changes"]
        self.assertEqual(len(changes), 1, changes)
        self.assertEqual((changes[0]["old"], changes[0]["new"]), ("coding", "writing"))

    def test_output_delta_bounded(self):
        """骨架只该增加几十到两百字符，不能把输出撑成原文副本。"""
        delta = self.result["output"]["delta_chars"]
        self.assertGreater(delta, 50)
        self.assertLess(delta, 250)

    def test_old_domains_not_regressed(self):
        rows = [(text, domain) for text, domain, _, _ in CORPUS if domain in BASELINE_DOMAINS]
        self.assertGreaterEqual(len(rows), 16, "语料里的旧领域样本被删减了")
        for text, expected in rows:
            self.assertEqual(analyze(text).domain, expected, text)


class SkeletonQualityTestCase(unittest.TestCase):
    def test_no_duplicate_or_empty_items(self):
        for intent, pair in OUTLINES.items():
            for lang in ("zh", "en"):
                items = pair[lang]
                self.assertEqual(items, list(dict.fromkeys(items)), f"{intent}/{lang} 有重复骨架")
                self.assertTrue(all(item.strip() for item in items), f"{intent}/{lang} 有空条目")

    def test_deep_mode_keeps_skeleton_and_risks(self):
        result = enhance({"text": "写个活动方案", "intensity": "deep"})
        self.assertIn("输出骨架", result["enhanced"])
        self.assertIn("风险提示", result["enhanced"])

    def test_text_format_keeps_skeleton(self):
        result = enhance({"text": "写个活动方案", "format": "text"})
        self.assertIn("输出骨架", result["enhanced"])
        self.assertNotIn("## ", result["enhanced"])

    def test_channel_slot_question_bilingual(self):
        for lang in ("zh", "en"):
            self.assertTrue(SLOT_QUESTIONS[(lang, "channel")].strip())


if __name__ == "__main__":
    unittest.main()
