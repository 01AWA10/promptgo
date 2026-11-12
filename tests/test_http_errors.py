"""HTTP 错误分支测试：429 限流、411 空体、SSE 内 error 事件、500 ENGINE_ERROR。

这四条此前没有任何覆盖。要点：
- 限流用独立 server + 可重置的 limiter，避免污染 test_http 的共享实例（默认 90/min）；
- SSE 的两类错误都只能以 `event: error` 表达（此时响应头已发出，状态码固定 200）；
- 500 必须把任意异常收口成 `ENGINE_ERROR`，不能把 traceback 漏给客户端。
"""

from __future__ import annotations

import threading
import time
import unittest
from unittest import mock

# 先导入 test_http：它在模块级把 server/ 放进 sys.path，helper 也复用同一套报文逻辑
from test_http import ROOT, parse_sse, request  # noqa: E402

import http_layer  # noqa: E402
from http_layer import AppConfig, EnhancerServer, RateLimiter  # noqa: E402

TEXT = {"text": "帮我写个周报"}


class ErrorBranchTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = AppConfig(root=ROOT, origins=["*"], token=None, pace=0.0, quiet=True)
        cls.server = EnhancerServer(("127.0.0.1", 0), cls.cfg)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        # 每个用例重置计数窗口，避免用例之间互相「借」额度
        self.cfg.limiter = RateLimiter(limit=90)

    # ------------------------------------------------------------------ 429
    def test_rate_limited_returns_429(self):
        self.cfg.limiter = RateLimiter(limit=2)
        for _ in range(2):
            self.assertEqual(request(self.port, "POST", "/v1/enhance", TEXT).status, 200)
        res = request(self.port, "POST", "/v1/enhance", TEXT)
        self.assertEqual(res.status, 429)
        self.assertEqual(res.json()["error"]["code"], "RATE_LIMITED")
        self.assertIn("过于频繁", res.json()["error"]["message"])

    def test_rate_limit_also_covers_stream_endpoint(self):
        self.cfg.limiter = RateLimiter(limit=1)
        first = request(self.port, "POST", "/v1/enhance/stream", TEXT)
        self.assertEqual(first.status, 200)
        second = request(self.port, "POST", "/v1/enhance/stream", TEXT)
        self.assertEqual(second.status, 429)
        self.assertEqual(second.json()["error"]["code"], "RATE_LIMITED")

    def test_rate_limit_window_recovers(self):
        limiter = RateLimiter(limit=2, window=0.05)
        self.assertTrue(limiter.allow("127.0.0.1"))
        self.assertTrue(limiter.allow("127.0.0.1"))
        self.assertFalse(limiter.allow("127.0.0.1"))
        time.sleep(0.1)
        self.assertTrue(limiter.allow("127.0.0.1"), "窗口内额度应随时间恢复")

    def test_rate_limit_is_per_client(self):
        limiter = RateLimiter(limit=1)
        self.assertTrue(limiter.allow("127.0.0.1"))
        self.assertFalse(limiter.allow("127.0.0.1"))
        self.assertTrue(limiter.allow("10.0.0.2"), "不同来源不应共享额度")

    # ------------------------------------------------------------------ 411
    def test_empty_body_returns_411(self):
        res = request(self.port, "POST", "/v1/enhance", headers={"Content-Length": "0"})
        self.assertEqual(res.status, 411)
        self.assertEqual(res.json()["error"]["code"], "EMPTY_BODY")

    def test_empty_stream_body_returns_411(self):
        res = request(self.port, "POST", "/v1/enhance/stream", headers={"Content-Length": "0"})
        self.assertEqual(res.status, 411)
        self.assertEqual(res.json()["error"]["code"], "EMPTY_BODY")

    # ------------------------------------------------- SSE 内的 error 事件
    def test_sse_invalid_input_emits_error_event(self):
        """空 text 在流式里无法用状态码拒绝（头已发出），只能发 error 事件。"""
        res = request(self.port, "POST", "/v1/enhance/stream", {})
        self.assertEqual(res.status, 200)
        self.assertTrue(res.headers["content-type"].startswith("text/event-stream"))
        events = parse_sse(res.text)
        names = [name for name, _ in events]
        self.assertEqual(names[-1], "error")
        self.assertNotIn("result", names)
        self.assertNotIn("done", names)
        self.assertEqual(events[-1][1]["code"], "EMPTY_INPUT")

    def test_sse_error_event_keeps_stream_framing(self):
        """error 帧必须是完整 SSE 帧（event + data + 空行），前端手工分帧才不卡住。"""
        res = request(self.port, "POST", "/v1/enhance/stream", {})
        self.assertTrue(res.text.endswith("\n\n"), repr(res.text[-12:]))
        self.assertIn("event: error\n", res.text)

    def test_sse_engine_exception_emits_engine_error(self):
        with mock.patch.object(http_layer, "stream", side_effect=RuntimeError("boom")):
            res = request(self.port, "POST", "/v1/enhance/stream", TEXT)
        events = parse_sse(res.text)
        self.assertEqual(events[-1][0], "error")
        self.assertEqual(events[-1][1]["code"], "ENGINE_ERROR")
        self.assertIn("boom", events[-1][1]["message"])

    # ---------------------------------------------------------- 500 兜底
    def test_engine_error_returns_500(self):
        with mock.patch.object(http_layer, "enhance", side_effect=RuntimeError("kaboom")):
            res = request(self.port, "POST", "/v1/enhance", TEXT)
        self.assertEqual(res.status, 500)
        body = res.json()
        self.assertFalse(body["ok"])
        self.assertEqual(body["error"]["code"], "ENGINE_ERROR")
        self.assertIn("引擎内部错误", body["error"]["message"])
        self.assertNotIn("Traceback", res.text, "不能把堆栈泄露给客户端")

    def test_business_error_still_maps_to_its_status(self):
        """收口 500 之后，EnhanceError 仍必须按自带状态码返回。"""
        res = request(self.port, "POST", "/v1/enhance", {"text": 123})
        self.assertEqual(res.status, 422)
        self.assertEqual(res.json()["error"]["code"], "EMPTY_INPUT")


class ConfigOverridesTestCase(unittest.TestCase):
    """P2-12：三个上限来自 AppConfig，接口、元数据与实际行为必须一致。"""

    @classmethod
    def setUpClass(cls):
        cls.cfg = AppConfig(root=ROOT, origins=["*"], token=None, pace=0.0, quiet=True,
                            rate_limit=3, max_body=1024, max_chars=120)
        cls.server = EnhancerServer(("127.0.0.1", 0), cls.cfg)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        self.cfg.limiter = RateLimiter(limit=3)

    def test_meta_and_health_reflect_max_chars(self):
        self.assertEqual(request(self.port, "GET", "/v1/meta").json()["limits"]["max_chars"], 120)
        self.assertEqual(request(self.port, "GET", "/v1/health").json()["max_chars"], 120)

    def test_input_truncated_to_configured_limit(self):
        # 128 字、JSON 转义后约 800 B：既低于 1 KB 的请求体上限，又超过 120 字的上限
        result = request(self.port, "POST", "/v1/enhance", {"text": "写个方案" * 32}).json()
        self.assertTrue(result["truncated"])
        self.assertLessEqual(len(result["original"]), 120)

    def test_body_limit_comes_from_config(self):
        res = request(self.port, "POST", "/v1/enhance", {"text": "写" * 2000})
        self.assertEqual(res.status, 413)
        self.assertIn("1KB", res.json()["error"]["message"])

    def test_rate_limit_comes_from_config(self):
        for _ in range(3):
            self.assertEqual(request(self.port, "POST", "/v1/enhance", TEXT).status, 200)
        self.assertEqual(request(self.port, "POST", "/v1/enhance", TEXT).status, 429)


if __name__ == "__main__":
    unittest.main()
