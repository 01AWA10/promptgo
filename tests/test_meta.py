"""`/v1/meta` 的识别清单（intents / domains / channels / tones）。

宿主不该在客户端硬编码这些枚举，所以 META 必须与词典**零漂移**：
任何新增意图/领域而忘记同步标签、或渠道词条指到重复标签，都会在这里失败。
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))

from engine import META  # noqa: E402
from engine.analyzer import (  # noqa: E402
    CHANNEL_WORDS, DOMAIN_KEYWORDS, DOMAIN_LABEL, INTENT_KEYWORDS, INTENT_LABEL, TONE_WORDS,
)
from engine.templates import OUTLINES, TEMPLATES  # noqa: E402

PAYLOAD_BUDGET = 12 * 1024


def ids(key: str) -> list[str]:
    return [item["id"] for item in META[key]]


class MetaShapeTestCase(unittest.TestCase):
    def test_lists_present_and_non_empty(self):
        for key in ("intents", "domains", "channels", "tones"):
            self.assertIn(key, META, f"META 缺少 {key}")
            self.assertTrue(META[key], f"{key} 为空")
            self.assertIn("id", META[key][0])
            self.assertIn("label", META[key][0])

    def test_no_duplicate_ids(self):
        for key in ("intents", "domains", "channels", "tones"):
            values = ids(key)
            self.assertEqual(len(values), len(set(values)), f"{key} 存在重复 id：{values}")

    def test_payload_within_budget(self):
        size = len(json.dumps(META, ensure_ascii=False).encode("utf-8"))
        self.assertLess(size, PAYLOAD_BUDGET, f"META 已膨胀到 {size} B")


class MetaIntentTestCase(unittest.TestCase):
    def test_covers_dictionary_plus_general(self):
        self.assertEqual(ids("intents"), list(INTENT_KEYWORDS) + ["general"])

    def test_labels_match_dictionary(self):
        for item in META["intents"]:
            self.assertEqual((item["label"], item["label_en"]), INTENT_LABEL[item["id"]])
            self.assertTrue(item["label_en"].strip())

    def test_every_intent_has_template_and_outline(self):
        spread = set(ids("intents"))
        self.assertEqual(spread, set(TEMPLATES), "META 意图与模板库不一致")
        self.assertEqual(spread, set(OUTLINES), "META 意图与成品骨架不一致")


class MetaDomainTestCase(unittest.TestCase):
    def test_covers_dictionary_plus_general(self):
        self.assertEqual(ids("domains"), list(DOMAIN_KEYWORDS) + ["general"])
        self.assertEqual(len(ids("domains")), len(DOMAIN_KEYWORDS) + 1)

    def test_labels_match_dictionary(self):
        for item in META["domains"]:
            self.assertEqual((item["label"], item["label_en"]), DOMAIN_LABEL[item["id"]])
            self.assertTrue(item["label_en"].strip())

    def test_every_domain_has_label(self):
        self.assertEqual(set(ids("domains")), set(DOMAIN_LABEL))


class MetaChannelToneTestCase(unittest.TestCase):
    def test_channels_are_deduped_labels(self):
        expected: list[str] = []
        for label in CHANNEL_WORDS.values():
            if label not in expected:
                expected.append(label)
        self.assertEqual(ids("channels"), expected)
        self.assertLess(len(expected), len(CHANNEL_WORDS), "词条数应多于标签数（存在同义拼写）")

    def test_tones_are_deduped_labels(self):
        expected: list[str] = []
        for label in TONE_WORDS.values():
            if label not in expected:
                expected.append(label)
        self.assertEqual(ids("tones"), expected)

    def test_id_equals_label_for_tags(self):
        """渠道/语气没有独立 slug：id 必须等于 label，宿主可直接回填分析结果。"""
        for key in ("channels", "tones"):
            for item in META[key]:
                self.assertEqual(item["id"], item["label"])


if __name__ == "__main__":
    unittest.main()
