"""HTTP 层端到端测试：python tests/run.py

在随机空闲端口上拉起真实服务，覆盖 REST、SSE、CORS、静态资源与错误分支。
为避免依赖 urllib 的 IDNA 编解码（部分精简版 Python 缺失 encodings.idna），
这里用最原始的 socket 发报文，顺带精确验证线上协议本身。
"""

from __future__ import annotations

import json
import socket
import sys
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))

from http_layer import AppConfig, EnhancerServer  # noqa: E402


class Response:
    def __init__(self, raw: bytes):
        head, _, self.body = raw.partition(b"\r\n\r\n")
        lines = head.decode("iso-8859-1").split("\r\n")
        self.status = int(lines[0].split(" ")[1])
        self.headers = {}
        for line in lines[1:]:
            if ":" in line:
                k, v = line.split(":", 1)
                self.headers[k.strip().lower()] = v.strip()

    @property
    def text(self) -> str:
        return self.body.decode("utf-8")

    def json(self) -> dict:
        return json.loads(self.text)


def request(port: int, method: str, path: str, payload: dict | None = None,
            headers: dict | None = None, raw_body: bytes | None = None) -> Response:
    body = raw_body if raw_body is not None else (
        json.dumps(payload).encode("utf-8") if payload is not None else b"")
    lines = [f"{method} {path} HTTP/1.1", f"Host: 127.0.0.1:{port}", "Connection: close"]
    extra = headers or {}
    has_length = any(k.lower() == "content-length" for k in extra)
    if body:
        lines.append("Content-Type: application/json")
        if not has_length:
            lines.append(f"Content-Length: {len(body)}")
    for k, v in extra.items():
        lines.append(f"{k}: {v}")
    head = ("\r\n".join(lines) + "\r\n\r\n").encode("utf-8")

    # 直接 socket.connect，绕过 create_connection 内部的 getaddrinfo（其依赖 idna 编解码）
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(10)
    buf = []
    try:
        sock.connect(("127.0.0.1", port))
        sock.sendall(head + body)
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                break
            buf.append(chunk)
    except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
        # 服务端拒绝大体积请求后可能直接关闭连接并触发 RST，已收到的字节仍然有效
        pass
    finally:
        sock.close()
    raw = b"".join(buf)
    if not raw:
        raise AssertionError("未收到任何响应字节")
    return Response(raw)


def parse_sse(text: str) -> list[tuple[str, dict]]:
    events = []
    event = None
    for block in text.split("\n\n"):
        for line in block.split("\n"):
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:"):
                events.append((event, json.loads(line[5:].strip())))
    return events


class ServerTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cfg = AppConfig(root=ROOT, origins=["*"], token=None, pace=0.0, quiet=True)
        cls.server = EnhancerServer(("127.0.0.1", 0), cfg)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    # ---------------------------------------------------------- cases
    def test_health(self):
        res = request(self.port, "GET", "/v1/health")
        self.assertEqual(res.status, 200)
        self.assertEqual(res.json()["service"], "promptgo-enhancer")
        self.assertTrue(res.json()["offline"])

    def test_meta(self):
        data = request(self.port, "GET", "/v1/meta").json()
        self.assertEqual(len(data["modes"]), 6)
        self.assertEqual(len(data["dims"]), 5)

    def test_meta_exposes_recognition_lists(self):
        """宿主应能直接枚举识别清单，而不是在客户端硬编码。"""
        data = request(self.port, "GET", "/v1/meta").json()
        self.assertEqual(len(data["intents"]), 12)
        self.assertEqual(len(data["domains"]), 23, "22 个领域 + general 兜底")
        self.assertGreaterEqual(len(data["channels"]), 30)
        self.assertGreaterEqual(len(data["tones"]), 35)
        self.assertEqual(data["domains"][-1]["id"], "general", "通用兜底应排最后")
        for key in ("intents", "domains", "channels", "tones"):
            first = data[key][0]
            self.assertIsInstance(first["id"], str)
            self.assertIsInstance(first["label"], str)

    def test_enhance_reports_truncated_constraints(self):
        """P2-10：多渠道投放超出保留上限时，analysis.truncated 要如实统计。"""
        text = "要在小红书、抖音、知乎、微博、B站、微信公众号同时投放，语气正式、严谨、专业、简洁、亲切"
        data = request(self.port, "POST", "/v1/enhance", {"text": text}).json()
        self.assertEqual(data["analysis"]["truncated"], {"tone": 1, "channel": 2})
        channels = [c["value"] for c in data["analysis"]["constraints"] if c["kind"] == "channel"]
        self.assertEqual(len(channels), 4, "保留 4 条，其余计入 truncated")

    def test_enhance(self):
        data = request(self.port, "POST", "/v1/enhance", {"text": "帮我写个新能源汽车文案"}).json()
        self.assertTrue(data["ok"])
        self.assertIn("## 角色", data["enhanced"])
        self.assertGreater(data["score"]["after"], data["score"]["before"])

    def test_enhance_new_domain_and_skeleton(self):
        """新增领域与成品骨架必须走通完整 HTTP 链路，而不只是引擎内可测。"""
        data = request(self.port, "POST", "/v1/enhance",
                       {"text": "写一份内网渗透测试报告，标注漏洞影响面"}).json()
        self.assertEqual(data["analysis"]["domain"], "security")
        self.assertEqual(data["analysis"]["domain_label"], "安全与合规")
        self.assertIn("输出骨架", data["enhanced"])

    def test_stream_analysis_carries_channel_and_tone(self):
        res = request(self.port, "POST", "/v1/enhance/stream",
                      {"text": "发到企业微信，语气冷幽默"})
        events = parse_sse(res.text)
        analysis = next(d for e, d in events if e == "analysis")
        channels = [c["value"] for c in analysis["constraints"] if c["kind"] == "channel"]
        tones = [c["value"] for c in analysis["constraints"] if c["kind"] == "tone"]
        self.assertIn("企业微信", channels)
        self.assertIn("冷幽默", tones)

    def test_stream_sse(self):
        res = request(self.port, "POST", "/v1/enhance/stream", {"text": "写个周报"})
        self.assertEqual(res.status, 200)
        self.assertIn("text/event-stream", res.headers["content-type"])
        events = parse_sse(res.text)
        names = [e for e, _ in events]
        self.assertEqual(names[0], "stage")
        self.assertIn("analysis", names)
        self.assertIn("chunk", names)
        self.assertIn("result", names)
        self.assertEqual(names[-1], "done")
        chunks = "".join(d["delta"] for e, d in events if e == "chunk")
        self.assertIn("## 角色", chunks)
        result = next(d for e, d in events if e == "result")
        self.assertGreater(result["score"]["after"], 0)

    def test_cors_preflight(self):
        res = request(self.port, "OPTIONS", "/v1/enhance", headers={"Origin": "https://example.com"})
        self.assertEqual(res.status, 204)
        self.assertEqual(res.headers["access-control-allow-origin"], "*")
        self.assertIn("x-pe-token", res.headers["access-control-allow-headers"].lower())

    def test_static_component(self):
        res = request(self.port, "GET", "/prompt-enhancer.js")
        self.assertEqual(res.status, 200)
        self.assertIn("customElements.define", res.text)
        self.assertIn("javascript", res.headers["content-type"])

    def test_demo_page(self):
        res = request(self.port, "GET", "/demo/")
        self.assertEqual(res.status, 200)
        self.assertIn("<prompt-enhancer", res.text)

    def test_404(self):
        self.assertEqual(request(self.port, "GET", "/nope").status, 404)

    def test_path_traversal_blocked(self):
        res = request(self.port, "GET", "/../server/app.py")
        self.assertIn(res.status, (400, 404))

    def test_traversal_with_allowed_suffix_blocked(self):
        """后缀白名单不能替代目录约束：.js/.html 也必须留在 web/ 内。"""
        for path in ("/../server/http_layer.js", "/../server/engine/pipeline.js",
                     "/../README.html"):
            res = request(self.port, "GET", path)
            self.assertEqual(res.status, 404, f"{path} 竟返回 {res.status}")

    def test_bad_content_length(self):
        res = request(self.port, "POST", "/v1/enhance", raw_body=b"{}",
                      headers={"Content-Length": "abc"})
        self.assertEqual(res.status, 400)
        self.assertEqual(res.json()["error"]["code"], "BAD_LENGTH")

    def test_body_too_large(self):
        res = request(self.port, "POST", "/v1/enhance", raw_body=b"x" * (65 * 1024))
        self.assertEqual(res.status, 413)
        self.assertEqual(res.json()["error"]["code"], "BODY_TOO_LARGE")

    def test_empty_text_422(self):
        res = request(self.port, "POST", "/v1/enhance", {"text": "   "})
        self.assertEqual(res.status, 422)
        self.assertEqual(res.json()["error"]["code"], "EMPTY_INPUT")

    def test_invalid_json(self):
        res = request(self.port, "POST", "/v1/enhance", raw_body=b"{not json")
        self.assertEqual(res.status, 400)
        self.assertEqual(res.json()["error"]["code"], "BAD_JSON")

    def test_rate_limit_headers_free(self):
        for _ in range(3):
            self.assertEqual(request(self.port, "POST", "/v1/enhance", {"text": "测试"}).status, 200)


class TokenAuthTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cfg = AppConfig(root=ROOT, origins=["*"], token="secret-token", pace=0.0, quiet=True)
        cls.server = EnhancerServer(("127.0.0.1", 0), cfg)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_missing_token_rejected(self):
        res = request(self.port, "POST", "/v1/enhance", {"text": "写个方案"})
        self.assertEqual(res.status, 401)
        self.assertEqual(res.json()["error"]["code"], "UNAUTHORIZED")

    def test_valid_token_accepted(self):
        res = request(self.port, "POST", "/v1/enhance", {"text": "写个方案"},
                      headers={"X-PE-Token": "secret-token"})
        self.assertEqual(res.status, 200)

    def test_health_reports_auth_required(self):
        self.assertTrue(request(self.port, "GET", "/v1/health").json()["auth_required"])


class CorsWhitelistTestCase(unittest.TestCase):
    """白名单模式下不得回显任意来源。"""

    @classmethod
    def setUpClass(cls):
        cfg = AppConfig(root=ROOT, origins=["https://ok.example.com"], token=None,
                        pace=0.0, quiet=True)
        cls.server = EnhancerServer(("127.0.0.1", 0), cfg)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_allowed_origin_echoed(self):
        res = request(self.port, "GET", "/v1/health",
                      headers={"Origin": "https://ok.example.com"})
        self.assertEqual(res.headers.get("access-control-allow-origin"),
                         "https://ok.example.com")

    def test_unknown_origin_not_echoed(self):
        res = request(self.port, "GET", "/v1/health",
                      headers={"Origin": "https://evil.example.com"})
        self.assertNotIn("access-control-allow-origin", res.headers)
        self.assertEqual(res.headers.get("vary"), "Origin")


class RateLimiterTestCase(unittest.TestCase):
    def test_limit_enforced(self):
        from http_layer import RateLimiter
        limiter = RateLimiter(limit=2, window=60)
        self.assertTrue(limiter.allow("a"))
        self.assertTrue(limiter.allow("a"))
        self.assertFalse(limiter.allow("a"))

    def test_expired_sources_are_pruned(self):
        from http_layer import RateLimiter
        limiter = RateLimiter(limit=2, window=0.05)
        for i in range(300):
            limiter.allow("10.0.0.%d" % i)
        time.sleep(0.08)
        limiter.allow("10.9.9.9")
        self.assertLess(len(limiter._hits), 300)


if __name__ == "__main__":
    unittest.main()
