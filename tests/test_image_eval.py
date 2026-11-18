"""阶段 4：120 条语料的自动断言门禁。

语料与断言都在 `tools/image_eval.py` 里，这里只做「不许退化」的守护：
覆盖比例、逐条通过率、长度区间、盲评包结构。
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import image_eval  # noqa: E402

_RESULT = image_eval.run()   # 全量只跑一次，多个用例共享


class CorpusGateTestCase(unittest.TestCase):
    def test_corpus_shape(self):
        cases = image_eval.build_corpus()
        self.assertEqual(len(cases), 120)
        self.assertEqual({c["scene"] for c in cases}, {"MK", "EC", "IL", "AV", "PS", "CD"})
        self.assertEqual({c["platform"] for c in cases}, {"generic", "mj", "flux", "sdxl"})
        self.assertEqual({c["tier"] for c in cases}, set("ABCDE"))
        self.assertEqual(len({c["id"] for c in cases}), 120)

    def test_all_cases_pass(self):
        self.assertEqual(_RESULT["failed"], 0,
                         msg="自动断言未通过：" + "; ".join(
                             f"{f['id']}={f['failures']}" for f in _RESULT["failures"][:5]))

    def test_every_bucket_full(self):
        for key, bucket in _RESULT["by_bucket"].items():
            self.assertEqual(bucket["pass"], bucket["total"], f"{key} 有失败")

    def test_length_inside_spec(self):
        self.assertGreaterEqual(_RESULT["length_min"], 150,
                                f"最短 {_RESULT['length_min']} 低于单主体下限")
        self.assertLessEqual(_RESULT["length_max"], 260,
                             f"最长 {_RESULT['length_max']} 超过中文上限")

    def test_packet_structure(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "packet.json"
            packet = image_eval.build_packet(target)
            loaded = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(len(loaded["items"]), 120)
        self.assertEqual(len(loaded["dims"]), 5)
        orders = {(item["source"]["A"], item["source"]["B"]) for item in loaded["items"]}
        self.assertEqual(orders, {("system", "raw"), ("raw", "system")})
        for item in loaded["items"][:5]:
            self.assertIn("A", item)
            self.assertIn("B", item)
            self.assertEqual(item["scores"]["A"], {})
            self.assertIsNone(item["preference"])
        self.assertEqual(len(packet["items"]), 120)

    def test_html_is_self_contained(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "blind.html"
            image_eval.build_html(target)
            html = target.read_text(encoding="utf-8")
        self.assertIn('id="case"', html)
        self.assertIn('id="export"', html)
        self.assertEqual(html.count('"platform":'), 120, "120 条数据未内联")
        self.assertNotIn("src=", html, "页面不应引用外部脚本")

    def test_aggregate_maps_sides_by_source(self):
        """系统组 5 分 / 原话组 3 分，折算表必须按 source 认边，不能按 A/B 认边。"""
        packet = image_eval.make_packet()
        for item in packet["items"]:
            for side in ("A", "B"):
                value = 5 if item["source"][side] == "system" else 3
                item["scores"][side] = {dim: value for dim in packet["dims"]}
            item["preference"] = "A"      # A 是系统的只有一半，故偏好率应为 50%
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "scores.json"
            target.write_text(json.dumps(packet, ensure_ascii=False), encoding="utf-8")
            table = image_eval.aggregate_scores(target)
        self.assertIn("5.00 | 3.00 | +2.00", table)
        self.assertIn("**5.00**", table)
        self.assertIn("系统 50%", table)

    def test_subset_keeps_scene_tier_grid(self):
        """30 条子集必须铺满 6 场景 × 5 难度，并轮流覆盖 4 个平台。"""
        items = image_eval.make_packet()["items"]
        subset = image_eval.pick_subset(items, 30)
        self.assertEqual(len(subset), 30)
        self.assertEqual({i["scene"] for i in subset},
                         {"MK", "EC", "IL", "AV", "PS", "CD"})
        self.assertEqual({i["tier"] for i in subset}, set("ABCDE"))
        self.assertEqual({i["platform"] for i in subset}, {"generic", "mj", "flux", "sdxl"})
        self.assertEqual(len({(i["scene"], i["tier"]) for i in subset}), 30)

    def test_full_size_subset_is_noop(self):
        items = image_eval.make_packet()["items"]
        self.assertEqual(len(image_eval.pick_subset(items, 120)), 120)

    def test_packet_is_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp) / "a.json"
            second = Path(tmp) / "b.json"
            image_eval.build_packet(first)
            image_eval.build_packet(second)
            self.assertEqual(first.read_text(encoding="utf-8"), second.read_text(encoding="utf-8"))


class RedundancyTestCase(unittest.TestCase):
    """客观冗余检测：硬信号（跨段重复、壳词）判失败，软信号（长片段回声）只报告。"""

    def test_cross_segment_duplicate_is_hard_failure(self):
        segments = {"subject": "海边咖啡店",
                    "composition": "三分法构图，另一侧留出文案区",
                    "technical": "16:9 画幅，高分辨率，另一侧留出文案区"}
        red = image_eval.redundancy(segments)
        self.assertEqual([(d["first"], d["again"]) for d in red["dup_pieces"]],
                         [("composition", "technical")])
        self.assertTrue(red["redundant"])

    def test_shell_word_is_hard_failure(self):
        red = image_eval.redundancy({"subject": "做一张海报", "composition": "对称构图"})
        self.assertEqual([hit["word"] for hit in red["shell"]], ["做一张"])
        self.assertTrue(red["redundant"])

    def test_longest_shell_word_wins(self):
        red = image_eval.redundancy({"subject": "请帮我画海报"})
        self.assertEqual([hit["word"] for hit in red["shell"]], ["请帮我"])

    def test_negative_segment_is_exempt(self):
        """负面词按规范本就成串重复，不算冗余。"""
        red = image_eval.redundancy({"subject": "香水瓶", "negative": "文字水印、文字水印"})
        self.assertFalse(red["redundant"])
        self.assertEqual(red["echoes"], [])

    def test_echo_is_soft_signal(self):
        red = image_eval.redundancy({"subject": "赛博朋克雨夜街道",
                                     "style": "赛博朋克，质感真实，整体色调统一"})
        self.assertEqual([e["text"] for e in red["echoes"]], ["赛博朋克"])
        self.assertFalse(red["redundant"], "题材词在 style 复述属正常，不能判失败")

    def test_sliding_windows_merge_into_one_run(self):
        runs = image_eval._repeated_runs("画面，边缘干净，细节，边缘干净，收尾")
        self.assertEqual(runs, ["，边缘干净，"])

    def test_corpus_is_redundancy_free(self):
        self.assertEqual(_RESULT["redundancy"]["dup_cases"], 0)
        self.assertEqual(_RESULT["redundancy"]["shell_cases"], 0)

    def test_conflict_phrase_keeps_real_subject(self):
        """回归：产物词在前（tier E）时，不能把「做一张宣传图」整壳当成主体。"""
        from engine import visual
        subject = visual.extract_subject("做一张宣传图，秋日露营帐篷营地，极简构图，但画面要满版铺满")
        self.assertEqual(subject, "秋日露营帐篷营地")


if __name__ == "__main__":
    unittest.main()
