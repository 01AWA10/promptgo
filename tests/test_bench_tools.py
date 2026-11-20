"""阶段 3/4 的两个验收工具：领域 × 风格抽样、性能与体积基准。

这两个脚本是「验收证据」而不是一次性脚本，因此需要守住三件事：
    1. 解析口径不漂移（文档改了表/数字，脚本与报告要能对上）；
    2. 门槛是布尔判定，不是人读的形容词；
    3. 报告里写的数字必须能由脚本复现（本用例只校验结构性数字，避免把 2.5 ms 写死）。
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))
sys.path.insert(0, str(ROOT / "tools"))

import perf_bench  # noqa: E402
import style_matrix_check  # noqa: E402
from engine import visual  # noqa: E402

MAP_DOC = ROOT / "docs" / "image-prompt" / "DOMAIN-STYLE-MAP-v0.1.md"
PERF_DOC = ROOT / "docs" / "image-prompt" / "PERF-REPORT-v0.1.md"


class StyleMatrixParseTestCase(unittest.TestCase):
    def test_all_domains_parsed(self):
        rows = style_matrix_check.load_rows()
        self.assertEqual(len(rows), 22, "映射表应有 22 个领域")

    def test_comma_inside_quotes_is_not_separator(self):
        """「（需限定「企业级、非废土」）」里的顿号不能把限定词切成两半。"""
        pieces = style_matrix_check._split_terms("电影感（需「稳重、不高对比」）、硬光")
        self.assertEqual(pieces, ["电影感（需「稳重、不高对比」）", "硬光"])

    def test_gray_qualifier_and_condition_parsed(self):
        terms = {term: (qualifier, condition) for term, qualifier, condition
                 in style_matrix_check._terms("电影感（需「稳重、不高对比」）、像素艺术（仅年轻向活动）、硬光")}
        self.assertEqual(terms["电影感"], ("稳重、不高对比", ""))
        self.assertEqual(terms["像素艺术"], ("", "仅年轻向活动"), "适用条件不是要补进正文的限定词")
        self.assertEqual(terms["硬光"], ("", ""))

    def test_sample_size_and_tier_spread(self):
        samples = style_matrix_check.build_samples(style_matrix_check.load_rows(), 100)
        self.assertEqual(len(samples), 100)
        self.assertEqual(len({s["domain"] for s in samples}), 22)
        self.assertTrue(all(any(s["tier"] == tier for s in samples)
                            for tier in style_matrix_check.TIERS))
        self.assertEqual(len({s["id"] if "id" in s else (s["domain"], s["tier"], s["term"])
                              for s in samples}), 100, "样本不应重复")


class StyleMatrixResultTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = style_matrix_check.run()

    def test_accounting_adds_up(self):
        r = self.result
        self.assertEqual(r["measured"] + len(r["untestable"]), r["samples"])
        self.assertEqual(r["passed"] + len(r["failures"]), r["measured"])
        self.assertEqual(sum(bucket["total"] for bucket in r["by_tier"].values()), r["measured"])
        self.assertEqual(sum(r["buckets"].values()), len(r["failures"]))

    def test_every_failure_has_reason(self):
        for fail in self.result["failures"]:
            self.assertTrue(fail["reason"], f"{fail['id']} 缺少不合理原因")
            self.assertIn(style_matrix_check.attribute(fail),
                          ("灰区归属维度错配", "禁用表未覆盖该词", "命中缺失或槽位被覆盖"))

    def test_documented_rate_matches_run(self):
        """文档 §4.1 写的「80 / 87 = 92%」必须与脚本实测一致，否则报告与代码脱钩。"""
        text = MAP_DOC.read_text(encoding="utf-8")
        match = re.search(r"\*\*(\d+) / (\d+) = (\d+)%\*\*", text)
        self.assertIsNotNone(match, "文档 §4.1 未写实测合理率")
        passed, measured, rate = (int(value) for value in match.groups())
        self.assertEqual((passed, measured), (self.result["passed"], self.result["measured"]))
        self.assertEqual(rate, round(self.result["rate"] * 100))


def probe(domain: str, term: str) -> str:
    """与抽样脚本同构的请求句式：领域首个关键词 + 宣传图 + 点名风格。"""
    from engine.analyzer import DOMAIN_KEYWORDS
    return f"做一张{DOMAIN_KEYWORDS[domain][0]}的宣传图，风格要{term}"


class GrayTierTestCase(unittest.TestCase):
    """灰区梯队（映射表第 4 列）：文档说「保留 + 追加限定词 + 留痕」，引擎必须真的这么做。"""

    def test_engine_table_matches_document(self):
        """引擎灰区表与映射表 §2 逐字一致（术语 + 限定词/适用条件），改表必须同时改代码。"""
        from engine import visual
        doc = {}
        for row in style_matrix_check.load_rows():
            for term, qualifier, condition in row["灰区"]:
                doc[row["domain"]] = (term, qualifier or condition)
        engine = {domain: (term, note)
                  for domain, table in visual.DOMAIN_STYLE_GRAY.items()
                  for term, (_mode, note) in table.items()}
        self.assertEqual(engine, doc)

    def test_qualifier_is_appended_to_body(self):
        """「需限定」类：限定词必须写进正文，否则「电影感」会变成高对比大片。"""
        from engine import enhance
        image = enhance({"text": probe("energy", "电影感")})["analysis"]["image"]
        self.assertIn("克制调色", image["segments"]["style"])
        kinds = [w["type"] for w in image["warnings"]]
        self.assertIn("style_gray", kinds)

    def test_condition_only_leaves_warning(self):
        """「适用条件」类：只留提示，不把「仅年轻向活动」塞进正文。"""
        from engine import enhance
        image = enhance({"text": probe("marketing", "像素艺术")})["analysis"]["image"]
        body = "，".join(value for key, value in image["segments"].items() if key != "negative")
        self.assertNotIn("仅年轻向活动", body)
        texts = [w["text"] for w in image["warnings"] if w["type"] == "style_gray"]
        self.assertTrue(any("仅年轻向活动" in text for text in texts), texts)

    def test_gray_does_not_fire_for_other_domains(self):
        """同一风格换个领域就不该触发（避免把灰区表做成全局黑名单）。"""
        from engine import enhance
        image = enhance({"text": probe("game", "电影感")})["analysis"]["image"]
        self.assertNotIn("style_gray", [w["type"] for w in image["warnings"]])


class DomainBanTestCase(unittest.TestCase):
    """跨维度禁配（映射表第 5 列）：判据是「输入命中禁配词」，不只看 style 槽位。"""

    def test_engine_table_matches_document(self):
        """引擎禁配表与映射表 §2「禁配」逐字一致（含顺序），改表必须同时改代码。"""
        from engine import visual
        doc = {row["domain"]: tuple(term for term, _qualifier, _condition in row["禁配"])
               for row in style_matrix_check.load_rows()}
        engine = {domain: ban for domain, ban in visual.DOMAIN_BAN.items() if domain != "general"}
        self.assertEqual(engine, doc)

    def test_cross_dimension_terms_are_cleared(self):
        """「鱼眼镜头」属 lens、「低调暗调」属 lighting：只比 style 槽位会让它们照进正文。"""
        from engine import enhance
        for domain, term, forbidden in (("realestate", "鱼眼镜头", "鱼眼镜头"),
                                        ("service", "低调暗调", "低调")):
            image = enhance({"text": probe(domain, term)})["analysis"]["image"]
            body = "，".join(value for key, value in image["segments"].items() if key != "negative")
            self.assertNotIn(forbidden, body, f"{domain} 的 {term} 未被清除")
            self.assertIn("style_conflict", [w["type"] for w in image["warnings"]])

    def test_alias_writing_is_caught(self):
        """文档写「卡通」、引擎词是「低多边形」：语义等价，必须一起清除并替换为领域首选。"""
        from engine import enhance
        image = enhance({"text": probe("auto", "卡通")})["analysis"]["image"]
        body = "，".join(value for key, value in image["segments"].items() if key != "negative")
        self.assertNotIn("卡通", body)
        self.assertNotIn("低多边形", body)
        self.assertTrue(image["segments"]["style"].startswith("商业产品摄影"), image["segments"]["style"])

    def test_english_input_is_caught(self):
        """英文输入（"cyberpunk"）也要命中禁配，否则英文请求会绕过整张禁配表。"""
        from engine import enhance
        image = enhance({"text": "a cyberpunk poster for our payment product launch",
                         "lang": "en"})["analysis"]["image"]
        self.assertNotIn("cyberpunk", image["segments"].get("style", "").lower())
        self.assertIn("style_conflict", [w["type"] for w in image["warnings"]])

    def test_ban_does_not_fire_for_other_domains(self):
        """同一禁配词换个领域不该触发（禁配表是按领域的，不是全局黑名单）。"""
        from engine import enhance
        image = enhance({"text": probe("marketing", "鱼眼镜头")})["analysis"]["image"]
        body = "，".join(value for key, value in image["segments"].items() if key != "negative")
        self.assertNotIn("style_conflict", [w["type"] for w in image["warnings"]])
        self.assertIn("鱼眼镜头", body)


class DimensionRoutingTestCase(unittest.TestCase):
    """T3：文档把光线/画质/主体维词写进「风格」列，引擎要按真实维度归位，不能丢词或误判。"""

    def test_quality_term_lands_in_technical(self):
        from engine import enhance
        image = enhance({"text": probe("medical", "干净背景")})["analysis"]["image"]
        self.assertIn("干净背景", image["segments"]["technical"])
        self.assertNotIn("干净背景", image["segments"]["style"], "画质词不该占风格槽")

    def test_quality_term_not_duplicated(self):
        """用户说的「高清」与模板自带的「高分辨率」是同一个词，不能写两遍。"""
        from engine import enhance
        image = enhance({"text": "做一张咖啡店宣传图，要高分辨率"})["analysis"]["image"]
        self.assertEqual(image["segments"]["technical"].count("高分辨率"), 1)

    def test_subject_term_goes_to_setting(self):
        """「建筑外观」是主体维词：与用户主体并存时挂环境段，不覆盖主体也不丢。"""
        from engine import enhance
        image = enhance({"text": probe("realestate", "建筑外观")})["analysis"]["image"]
        self.assertIn("建筑外观", image["segments"]["setting"])
        self.assertNotIn("建筑外观", image["segments"]["subject"])
        self.assertNotIn("建筑外观", image["segments"]["style"])

    def test_gray_term_matched_by_engine_word(self):
        """灰区词按引擎主词找落点：文档写「暗调低调」，正文里是「低调」。"""
        from engine import enhance
        image = enhance({"text": probe("food", "暗调低调")})["analysis"]["image"]
        body = "，".join(value for key, value in image["segments"].items() if key != "negative")
        self.assertIn("低调", body)
        self.assertIn("style_gray", [w["type"] for w in image["warnings"]])

    def test_no_sample_left_outside_vocabulary(self):
        """v1.3 补入 `概念设定` 后，映射表里的 100 条样本应全部可测（词表外为 0）。"""
        result = style_matrix_check.run()
        self.assertEqual({row["term"] for row in result["untestable"]}, set())
        self.assertEqual(result["measured"], result["samples"])


class UppercaseTermTestCase(unittest.TestCase):
    def test_uppercase_style_term_is_reachable(self):
        """回归：含大写拉丁字母的主词（3D 渲染 / 2.5D 插画）曾因 lower 文本比对而永不命中。"""
        for term in ("3D 渲染", "2.5D 插画"):
            hits = visual.match_terms(f"风格要{term}".lower(), "IL")
            self.assertEqual(hits.get("style"), term)


class PerfBenchTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = perf_bench.run(rounds=50)   # 用例内缩短轮次，结论只看门槛

    def test_all_gates_pass(self):
        self.assertTrue(all(self.result["gates"].values()), f"未通过：{self.result['gates']}")

    def test_p95_far_below_budget(self):
        p95 = self.result["latency"]["image_500"]["p95_ms"]
        self.assertLess(p95, perf_bench.P95_BUDGET_MS / 3, f"P95 {p95} ms 已逼近 30 ms 门槛")

    def test_sizes_within_budget(self):
        sizes = self.result["sizes"]
        self.assertLessEqual(sizes["component_bytes"], sizes["component_budget_bytes"])
        self.assertLessEqual(sizes["meta_bytes"], sizes["meta_budget_bytes"])
        self.assertLessEqual(sizes["meta_image_bytes"], sizes["meta_image_budget_bytes"])

    def test_documented_budgets_match_code(self):
        """报告里写的门槛（30 ms / 44 KB / 12 KB / 5 KB）必须与脚本常量一致。"""
        text = PERF_DOC.read_text(encoding="utf-8")
        self.assertIn(f"{perf_bench.P95_BUDGET_MS:.0f} ms", text)
        self.assertIn(f"{perf_bench.SIZE_BUDGET // 1024} KB", text)
        self.assertIn(f"{perf_bench.META_BUDGET // 1024} KB", text)
        self.assertIn(f"{perf_bench.META_IMAGE_BUDGET // 1024} KB", text)


if __name__ == "__main__":
    unittest.main()
