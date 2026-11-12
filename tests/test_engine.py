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
from engine.analyzer import analyze, detect_lang  # noqa: E402
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
