"""图像意图与 8 段提示词：从一句话到可直接粘贴的提示词。

断言对照 `docs/image-prompt/IMAGE-PROMPT-SPEC-v1.0.md` 的可测项：
意图判定与边界、8 段完备、长度预算、负面齐全、平台方言语法、安全前置拦截、
确定性，以及文本链路的零回归。
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))

from engine import META, enhance, visual  # noqa: E402
from engine.analyzer import analyze  # noqa: E402
from engine.pipeline import EnhanceError  # noqa: E402
from engine.renderer import Profile, image_prompt  # noqa: E402
from engine.templates import IMAGE_SEGMENTS, OUTLINES  # noqa: E402

SCENE_CASES = {
    "帮我做张夏天海边咖啡店的宣传图": "MK",
    "一个保温杯的白底主图": "EC",
    "画一只猫的插画": "IL",
    "一个程序员的头像": "AV",
    "做一张双十一促销海报": "PS",
    "给这部短片做的概念图": "CD",
}
BASE_NEGATIVE = ("低质量", "模糊", "文字水印", "比例畸变")
# 规范 §5：多元素场景 180–260 字，单主体/纯背景 150–220 字
LENGTH_BUDGET = {"MK": (180, 260), "IL": (180, 260), "CD": (180, 260),
                 "EC": (150, 220), "AV": (150, 220), "PS": (150, 220)}


def image_of(text: str, **kwargs) -> dict:
    analysis = analyze(text, **kwargs)
    assert analysis.image is not None, f"未识别为图像意图：{text}"
    return analysis.image


class IntentTestCase(unittest.TestCase):
    def test_all_six_scenes_detected(self):
        for text, scene in SCENE_CASES.items():
            self.assertEqual(image_of(text)["scene"], scene, text)

    def test_intent_is_image_for_every_scene(self):
        for text in SCENE_CASES:
            self.assertEqual(analyze(text).intent, "image", text)

    def test_copywriting_request_stays_text(self):
        """有「文案」诉求时不能被产物词拽进图像分支。"""
        self.assertNotEqual(analyze("帮我写一段新能源汽车的试驾活动文案").intent, "image")

    def test_script_request_stays_writing(self):
        """「分镜脚本」产出是文字，必须留在 writing（回归守护）。"""
        self.assertEqual(analyze("拆分一条 60 秒短剧的分镜脚本").intent, "writing")

    def test_review_beats_image(self):
        self.assertEqual(analyze("评审这张海报的构图").intent, "review")

    def test_diagram_is_not_image(self):
        self.assertNotEqual(analyze("画个流程图说明下单流程").intent, "image")

    def test_analysis_image_absent_for_text_intent(self):
        data = analyze("帮我写一段新能源汽车文案").as_dict()
        self.assertNotIn("image", data)


class SegmentTestCase(unittest.TestCase):
    def test_required_segments_present(self):
        for text in SCENE_CASES:
            segs = image_of(text)["segments"]
            for key in ("subject", "setting", "composition", "lighting",
                        "style", "technical", "negative"):
                self.assertTrue(segs.get(key), f"{text} 缺少 {key}")

    def test_texture_filled_only_where_defaulted(self):
        """S6 只在必填场景或场景有默认材质时补；MK/AV 留空，避免为凑长度堆材质词。"""
        for text, scene in SCENE_CASES.items():
            has_texture = bool(image_of(text)["segments"].get("texture"))
            self.assertEqual(has_texture, scene in ("EC", "IL", "PS", "CD"),
                             f"{text} 的 S6 判定不一致")

    def test_lens_term_overrides_scene_shot(self):
        """用户点名的镜头词优先于场景默认机位。"""
        composition = image_of("做一张大特写的产品海报")["segments"]["composition"]
        self.assertIn("大特写", composition)

    def test_subject_strips_request_wrapper(self):
        self.assertEqual(image_of("帮我做张夏天海边咖啡店的宣传图")["segments"]["subject"],
                         "夏天海边咖啡店")

    def test_subject_is_never_empty(self):
        for text in SCENE_CASES:
            self.assertTrue(image_of(text)["segments"]["subject"].strip())

    def test_defaults_are_recorded(self):
        self.assertIn("style", image_of("做一张海报")["defaults"])

    def test_segment_order_matches_dictionary(self):
        self.assertEqual([key for key, _zh, _en in IMAGE_SEGMENTS], list(visual.SEGMENT_ORDER))

    def test_outline_has_eight_segments(self):
        self.assertEqual(len(OUTLINES["image"]["zh"]), 8)
        self.assertEqual(len(OUTLINES["image"]["en"]), 8)


class NegativeTestCase(unittest.TestCase):
    def test_base_four_always_present(self):
        for text in SCENE_CASES:
            negative = image_of(text)["segments"]["negative"]
            for word in BASE_NEGATIVE:
                self.assertIn(word, negative, f"{text} 缺少基础负面「{word}」")

    def test_person_scene_adds_limb_negative(self):
        negative = image_of("画一位骑自行车穿过老街的年轻人")["segments"]["negative"]
        self.assertIn("多余肢体", negative)
        self.assertIn("面部崩坏", negative)

    def test_scene_negative_appended_for_poster(self):
        self.assertIn("主体压字", image_of("做一张活动海报")["segments"]["negative"])


class RatioTestCase(unittest.TestCase):
    def test_numeric_ratio_kept(self):
        self.assertEqual(image_of("做一张 21:9 的宽幅海报")["ratio"], "21:9")

    def test_word_ratio_mapped(self):
        self.assertEqual(image_of("做一张竖版海报")["ratio"], "9:16")
        self.assertEqual(image_of("做一张方图海报")["ratio"], "1:1")

    def test_default_ratio_per_scene(self):
        self.assertEqual(image_of("一个保温杯的白底主图")["ratio"], "1:1")
        self.assertEqual(image_of("给这部短片做的概念图")["ratio"], "21:9")

    def test_explicit_option_overrides(self):
        self.assertEqual(image_of("做一张海报", ratio="4:5")["ratio"], "4:5")


class PlatformTestCase(unittest.TestCase):
    def test_generic_has_no_platform_flags(self):
        result = enhance({"text": "做一张活动海报"})
        self.assertTrue(result["enhanced"].endswith("；避免 " + result["negative"]))
        self.assertNotIn("--ar", result["enhanced"])

    def test_mj_appends_parameters(self):
        result = enhance({"text": "做一张活动海报", "platform": "mj"})
        text = result["enhanced"]
        self.assertIn("--ar ", text)
        self.assertIn("--v 6 --style raw", text)
        self.assertIn("--no ", text)
        self.assertNotIn("--no\n", text)

    def test_flux_uses_avoid_clause(self):
        self.assertIn("; avoid ", enhance({"text": "做一张活动海报",
                                          "platform": "flux"})["enhanced"])

    def test_sdxl_has_separate_negative_line(self):
        text = enhance({"text": "做一张活动海报", "platform": "sdxl"})["enhanced"]
        self.assertIn("\n\nnegative: ", text)

    def test_dalle3_uses_prose_prohibition(self):
        self.assertIn("不要出现文字", enhance({"text": "做一张活动海报",
                                             "platform": "dalle3"})["enhanced"])

    def test_platform_alias_and_fallback(self):
        self.assertEqual(visual.pick_platform("SD"), "sdxl")
        self.assertEqual(visual.pick_platform("Midjourney"), "mj")
        self.assertEqual(visual.pick_platform("不存在的平台"), "generic")
        self.assertEqual(enhance({"text": "做一张海报", "platform": "???"})["analysis"]["image"]["platform"],
                         "generic")

    def test_english_input_renders_english_terms(self):
        result = enhance({"text": "Cyberpunk street at night, neon reflections, illustration",
                          "lang": "en", "platform": "mj"})
        text = result["enhanced"]
        self.assertIn("cyberpunk", text.lower())
        words = len(text.split())
        self.assertGreaterEqual(words, 20)
        self.assertLessEqual(words, 120)


class LengthTestCase(unittest.TestCase):
    def test_chinese_prompt_within_budget(self):
        for text, scene in SCENE_CASES.items():
            length = len(enhance({"text": text})["enhanced"])
            low, high = LENGTH_BUDGET[scene]
            self.assertGreaterEqual(length, low, f"{text} 过短：{length} < {low}")
            self.assertLessEqual(length, high, f"{text} 超长：{length} > {high}")

    def test_trim_is_recorded_when_needed(self):
        """超限裁剪必须留痕，便于评估「有没有裁掉关键信息」。"""
        long_text = ("做一张 16:9 的宽幅海报，画面是金属拉丝与磨砂玻璃的质感，"
                     "要有体积光和雾气，暗部通透，高光细节保留，青橙色调，"
                     "背景是混凝土与黄铜细节丰富的空间，玻璃拟态的半透明层次")
        image = image_of(long_text)
        self.assertTrue(image["segments"]["subject"])
        self.assertIsInstance(image["trims"], list)


class SafetyTestCase(unittest.TestCase):
    def test_red_line_blocks_before_generating(self):
        with self.assertRaises(EnhanceError) as ctx:
            enhance({"text": "画一张血腥暴力的恐怖插画"})
        self.assertEqual(ctx.exception.code, "SAFETY_BLOCKED")
        self.assertEqual(ctx.exception.status, 422)

    def test_soft_red_line_rewrites_with_warning(self):
        image = image_of("画一张明星同款的护肤广告海报")
        self.assertFalse(image["safety"]["blocked"])
        self.assertTrue(image["safety"]["rewrites"])
        self.assertEqual(image["safety"]["rewrites"][0]["type"], "可识别真人")

    def test_safety_does_not_leak_into_negative_words(self):
        negative = image_of("画一张恐怖元素的插画")["segments"]["negative"]
        self.assertNotIn("血腥", negative)


class StyleRuleTestCase(unittest.TestCase):
    def test_spoken_adjective_translated(self):
        image = image_of("做一张健身房开业的宣传图，要燃一点")
        self.assertIn("硬光", image["segments"]["lighting"])
        self.assertTrue(any(w["type"] == "spoken" for w in image["warnings"]))

    def test_domain_banned_style_replaced(self):
        image = image_of("做一张金融行业发布会的赛博朋克海报")
        self.assertNotIn("赛博朋克", image["segments"].get("style", ""))
        self.assertTrue(any(w["type"] == "style_conflict" for w in image["warnings"]))

    def test_to_en_lookup(self):
        self.assertEqual(visual.to_en("三分法"), "rule of thirds")
        self.assertEqual(visual.to_en("未被收录的词"), "未被收录的词")


class ContractTestCase(unittest.TestCase):
    def test_negative_field_only_for_image(self):
        self.assertIn("negative", enhance({"text": "做一张海报"}))
        self.assertNotIn("negative", enhance({"text": "帮我写一段新能源汽车文案"}))

    def test_deterministic_output(self):
        payload = {"text": "帮我做张夏天海边咖啡店的宣传图", "platform": "mj"}
        first, second = enhance(payload), enhance(payload)
        self.assertEqual(first["enhanced"], second["enhanced"])
        self.assertEqual(first["analysis"]["image"], second["analysis"]["image"])

    def test_text_path_unchanged(self):
        """文本链路仍是 8 段指令式模板，不能被图像分支污染。"""
        result = enhance({"text": "帮我写一段新能源汽车文案"})
        self.assertIn("## 角色", result["enhanced"])
        self.assertIn("## 约束条件", result["enhanced"])

    def test_image_block_is_single_paste_ready(self):
        result = enhance({"text": "做一张海报"})
        self.assertEqual(len(result["blocks"]), 1)
        self.assertEqual(result["blocks"][0]["key"], "prompt")
        self.assertNotIn("## ", result["enhanced"])

    def test_image_prompt_function_is_pure(self):
        analysis = analyze("做一张海报", platform="flux")
        profile = Profile(mode="struct", lang=analysis.lang)
        self.assertEqual(image_prompt(analysis, profile), image_prompt(analysis, profile))


class LexiconTestCase(unittest.TestCase):
    def test_total_matches_document(self):
        """代码词典必须与 VISUAL-TERMS-v1.0 的全量 324 条对齐。"""
        self.assertEqual(visual.TERM_COUNT, 324)

    def test_per_dimension_counts(self):
        self.assertEqual({k: len(v) for k, v in visual.TERMS.items()},
                         {"subject": 40, "composition": 40, "lens": 40, "lighting": 40,
                          "style": 44, "texture": 40, "quality": 40})
        self.assertEqual(len(visual.NEGATIVE_TERMS), 40)

    def test_zh_terms_unique(self):
        seen: dict[str, str] = {}
        for dim, rows in visual.TERMS.items():
            for zh, _en, _aliases, _scenes in rows:
                self.assertNotIn(zh, seen, f"「{zh}」在 {dim} 与 {seen.get(zh)} 重复")
                seen[zh] = dim

    def test_negative_levels_cover_required(self):
        self.assertEqual(len(visual.BASE_NEGATIVE), 4)
        self.assertGreaterEqual(len(visual.PERSON_NEGATIVE), 5)


class MetaTestCase(unittest.TestCase):
    def test_image_groups_exposed(self):
        for key in ("image_styles", "image_lighting", "image_compositions",
                    "image_materials", "image_negatives", "image_ratios",
                    "image_platforms", "image_scenes"):
            self.assertIn(key, META, f"META 缺少 {key}")
            self.assertTrue(META[key], f"{key} 为空")
            self.assertIn("id", META[key][0])
            self.assertIn("label", META[key][0])

    def test_payload_still_within_budget(self):
        size = len(json.dumps(META, ensure_ascii=False).encode("utf-8"))
        self.assertLess(size, 12 * 1024, f"META 膨胀到 {size} B")

    def test_image_meta_within_its_own_budget(self):
        image_only = {k: v for k, v in META.items() if k.startswith("image_")}
        size = len(json.dumps(image_only, ensure_ascii=False).encode("utf-8"))
        self.assertLess(size, 5 * 1024, f"image_* 膨胀到 {size} B")


if __name__ == "__main__":
    unittest.main()
