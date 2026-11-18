"""灰度上线与回滚演练（阶段 5 验收：开关一关即回到纯文本行为，反馈只落本地日志）。

这里用真实服务跑两条链路：
    1. 灰度开启：健康检查如实上报、meta 带 image_*、图像意图生效、反馈写 JSONL；
    2. 回滚态（--enable-image off）：meta 不再下发图像清单、图像意图不识别、
       输出里不出现比例参数与负面词行——即「关掉开关就回到上线前的行为」。

本文件同时充当计划 §5.5 的**回滚演练证据**：跑通即演练成功，不需要人工再点一遍。
"""

from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT / "tools"))

import feedback_report  # noqa: E402
from http_layer import AppConfig, EnhancerServer  # noqa: E402
from test_http import request  # noqa: E402

IMAGE_TEXT = "画一只橘猫坐在窗台上，水彩风格，留出文案区"


def start_server(**kwargs) -> tuple[EnhancerServer, int]:
    cfg = AppConfig(root=ROOT, origins=["*"], token=None, pace=0.0, quiet=True, **kwargs)
    server = EnhancerServer(("127.0.0.1", 0), cfg)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, server.server_address[1]


class GrayOnTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.log = Path(cls.tmp.name) / "feedback.log"
        cls.server, cls.port = start_server(feedback_log=cls.log, image_platform="mj")

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.tmp.cleanup()

    def test_health_reports_gray_state(self):
        data = request(self.port, "GET", "/v1/health").json()
        self.assertEqual(data["image"], {"enabled": True, "platform": "mj"})
        self.assertTrue(data["feedback"])

    def test_meta_ships_image_groups(self):
        data = request(self.port, "GET", "/v1/meta").json()
        self.assertIn("image_styles", data)
        self.assertGreater(len(data["image_platforms"]), 0)

    def test_default_platform_applies(self):
        data = request(self.port, "POST", "/v1/enhance", {"text": IMAGE_TEXT}).json()
        image = data["analysis"]["image"]
        self.assertEqual(image["platform"], "mj", "请求未指定时应落到 --image-platform")
        self.assertTrue(image["picks"].get("style"), "picks 要能供前端渲染风格 chip")

    def test_request_platform_wins(self):
        data = request(self.port, "POST", "/v1/enhance",
                       {"text": IMAGE_TEXT, "platform": "flux"}).json()
        self.assertEqual(data["analysis"]["image"]["platform"], "flux")

    def test_feedback_is_logged_locally(self):
        events = [
            {"kind": "enhance", "text": IMAGE_TEXT, "intent": "image", "platform": "mj", "chars": 120},
            {"kind": "copy", "text": IMAGE_TEXT, "platform": "mj"},
            {"kind": "vote", "useful": False, "text": "画一只橘猫，赛博朋克风格", "platform": "mj"},
        ]
        for event in events:
            res = request(self.port, "POST", "/v1/feedback", event)
            self.assertEqual(res.status, 200)
            self.assertTrue(res.json()["logged"])
        lines = [json.loads(line) for line in self.log.read_text(encoding="utf-8").splitlines() if line]
        self.assertEqual([line["kind"] for line in lines[-3:]], ["enhance", "copy", "vote"])
        self.assertNotIn("ip", lines[-1], "反馈不记来源 IP")

    def test_feedback_rejects_unknown_kind(self):
        res = request(self.port, "POST", "/v1/feedback", {"kind": "like"})
        self.assertEqual(res.status, 400)
        self.assertEqual(res.json()["error"]["code"], "BAD_KIND")

    def test_feedback_vote_needs_useful(self):
        res = request(self.port, "POST", "/v1/feedback", {"kind": "vote"})
        self.assertEqual(res.status, 400)
        self.assertEqual(res.json()["error"]["code"], "MISSING_USEFUL")

    def test_report_aggregates_log(self):
        result = feedback_report.run(self.log)
        self.assertGreaterEqual(result["enhances"], 1)
        self.assertGreaterEqual(result["copy_rate"], 0.0)
        self.assertTrue(any(item["reason"] == "没用票" for item in result["failures"]))
        self.assertTrue(result["failures"][0]["candidate"], "失败样本应给出归因候选")


class RollbackDrillTestCase(unittest.TestCase):
    """关闭灰度开关：输出必须与「图像功能上线前」一致。"""

    @classmethod
    def setUpClass(cls):
        cls.server, cls.port = start_server(enable_image=False, image_platform="mj")

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_health_shows_disabled(self):
        data = request(self.port, "GET", "/v1/health").json()
        self.assertFalse(data["image"]["enabled"])

    def test_meta_drops_image_groups(self):
        data = request(self.port, "GET", "/v1/meta").json()
        self.assertEqual([key for key in data if key.startswith("image_")], [],
                         "回滚态不应再下发图像清单")
        self.assertIn("modes", data, "文本能力不受影响")

    def test_image_input_falls_back_to_text(self):
        data = request(self.port, "POST", "/v1/enhance", {"text": IMAGE_TEXT}).json()
        self.assertNotIn("image", data["analysis"], "回滚态不产出图像分析")
        self.assertNotEqual(data["analysis"]["intent"], "image")
        enhanced = data["enhanced"]
        for marker in ("--ar", "--v", "负面词", "16:9"):
            self.assertNotIn(marker, enhanced, f"回滚态输出不应包含图像参数 {marker}")

    def test_feedback_still_accepted_when_disabled(self):
        """反馈通道与灰度开关解耦：关掉图像不影响反馈收集。"""
        res = request(self.port, "POST", "/v1/feedback", {"kind": "retry", "text": IMAGE_TEXT})
        self.assertEqual(res.status, 200)
        self.assertFalse(res.json()["logged"], "未配置日志路径时应返回 logged=False 而不是报错")


if __name__ == "__main__":
    unittest.main()
