"""启动入口（CLI）测试：令牌解析、启动文案、--open 行为、main() 退出码。

这些分支此前只有手工冒烟，回归风险集中在三处：
1. `--token` 不带值时随机生成、带值时沿用；
2. 启动摘要必须是 GBK 可编码的（中文 Windows 控制台默认 cp936，
   历史实现里的 U+26A0「⚠」会让 `--host 0.0.0.0` 直接抛 UnicodeEncodeError）；
3. `main()` 在 Ctrl+C 与正常返回两种路径下都应返回 0 并关闭 server。
"""

from __future__ import annotations

import argparse
import contextlib
import io
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))

import app  # noqa: E402
from http_layer import VERSION  # noqa: E402

URL = "http://127.0.0.1:7417"


def make_args(port: int = 7417, **overrides) -> argparse.Namespace:
    base = {"host": "127.0.0.1", "port": port, "no_fallback": False,
            "allow_origin": None, "token": None, "pace": 6, "quiet": True, "open": False,
            "rate_limit": app.RATE_LIMIT, "max_body": app.MAX_BODY // 1024,
            "max_chars": app.MAX_CHARS, "enable_image": "on", "image_platform": "generic",
            "feedback_log": None, "no_feedback_log": True}
    base.update(overrides)
    return argparse.Namespace(**base)


class FakeCfg:
    """镜像 AppConfig 里启动摘要会读到的字段（新增字段要同步，否则 main() 会 AttributeError）。"""

    def __init__(self, token=None, enable_image=True, image_platform="generic", feedback_log=None):
        self.token = token
        self.enable_image = enable_image
        self.image_platform = image_platform
        self.feedback_log = feedback_log


class FakeServer:
    """serve_forever 按需返回（正常退出）或抛 KeyboardInterrupt（模拟 Ctrl+C）。"""

    def __init__(self, cfg=None, interrupt=False):
        self.cfg = cfg or FakeCfg()
        self.interrupt = interrupt
        self.closed = False
        self.served = False

    def serve_forever(self):
        self.served = True
        if self.interrupt:
            raise KeyboardInterrupt

    def server_close(self):
        self.closed = True


class TokenResolveTestCase(unittest.TestCase):
    def test_disabled_returns_none(self):
        self.assertIsNone(app._resolve_token(None))
        self.assertIsNone(app._resolve_token(False))

    def test_flag_only_generates_random_token(self):
        first, second = app._resolve_token(True), app._resolve_token(True)
        self.assertIsInstance(first, str)
        self.assertTrue(first)
        self.assertNotEqual(first, second, "两次生成不应相同")
        self.assertRegex(first, r"^[A-Za-z0-9_-]{16}$")   # token_urlsafe(12) → 16 字符

    def test_custom_token_preserved(self):
        self.assertEqual(app._resolve_token("s3cret"), "s3cret")

    def test_token_wired_into_config(self):
        server, _ = app.build_server(make_args(token=True))
        try:
            self.assertIsInstance(server.cfg.token, str)
            self.assertTrue(server.cfg.token)
        finally:
            server.server_close()


class StartupTextTestCase(unittest.TestCase):
    def test_banner_mentions_version_and_engine(self):
        text = app.banner()
        self.assertIn(VERSION, text)
        self.assertIn("offline prompt enhancer", text)
        self.assertIn("____", text)          # ASCII 图形没被转义坏

    def test_banner_accepts_override_version(self):
        self.assertIn("v9.9.9", app.banner("9.9.9"))

    def test_lines_contain_endpoints_and_snippet(self):
        text = "\n".join(app.startup_lines(URL, None, "127.0.0.1"))
        self.assertIn(URL, text)
        self.assertIn(f"{URL}/demo/", text)
        self.assertIn(f"{URL}/prompt-enhancer.js", text)
        self.assertIn('<script src="' + URL + '/prompt-enhancer.js" defer></script>', text)
        self.assertIn("Ctrl+C 停止", text)

    def test_token_hint_only_when_enabled(self):
        without = "\n".join(app.startup_lines(URL, None, "127.0.0.1"))
        self.assertNotIn("访问令牌", without)
        with_token = "\n".join(app.startup_lines(URL, "abc123", "127.0.0.1"))
        self.assertIn("访问令牌   abc123", with_token)
        self.assertIn('<prompt-enhancer token="...">', with_token)

    def test_non_loopback_warning(self):
        self.assertIn("【警告】", "\n".join(app.startup_lines(URL, None, "0.0.0.0")))
        self.assertNotIn("【警告】", "\n".join(app.startup_lines(URL, None, "127.0.0.1")))
        self.assertNotIn("【警告】", "\n".join(app.startup_lines(URL, None, "localhost")))

    def test_startup_text_is_gbk_encodable(self):
        """中文 Windows 控制台是 cp936：任何非 GBK 字符都会在启动时炸掉。"""
        for host in ("127.0.0.1", "0.0.0.0"):
            text = "\n".join(app.startup_lines(URL, "abc123", host))
            text.encode("gbk")   # 不可编码会直接失败
        self.assertFalse(re.search(r"[\u2600-\u27bf\U0001F300-\U0001FAFF]", app.banner()))


class ScheduleOpenTestCase(unittest.TestCase):
    def test_schedules_browser_once_with_demo_url(self):
        calls = []

        class RecordingTimer:
            def __init__(self, delay, func):
                calls.append(("timer", delay, func))

            def start(self):
                calls.append(("start",))

        opened = []
        with mock.patch.object(app.webbrowser, "open", side_effect=opened.append):
            app._schedule_open(URL, timer=RecordingTimer)
            self.assertEqual(calls[0][0], "timer")
            self.assertEqual(calls[0][1], 0.6)
            self.assertEqual(calls[1], ("start",))
            calls[0][2]()          # 触发回调，确认浏览器地址
        self.assertEqual(opened, [f"{URL}/demo/"])

    def test_custom_delay_passed_through(self):
        calls = []

        class RecordingTimer:
            def __init__(self, delay, func):
                calls.append(delay)

            def start(self):
                pass

        app._schedule_open(URL, delay=0.01, timer=RecordingTimer)
        self.assertEqual(calls, [0.01])


class MainExitCodeTestCase(unittest.TestCase):
    def _run(self, argv, server):
        out = io.StringIO()
        with mock.patch.object(app, "build_server", return_value=(server, 7417)), \
                contextlib.redirect_stdout(out):
            code = app.main(argv)
        return code, out.getvalue()

    def test_returns_zero_and_closes_on_interrupt(self):
        server = FakeServer(interrupt=True)
        code, out = self._run(["--port", "7417"], server)
        self.assertEqual(code, 0)
        self.assertTrue(server.served)
        self.assertTrue(server.closed, "Ctrl+C 后必须关闭 server")
        self.assertIn("已停止。", out)

    def test_returns_zero_on_clean_exit(self):
        server = FakeServer()
        code, _ = self._run(["--port", "7417"], server)
        self.assertEqual(code, 0)
        self.assertTrue(server.closed)

    def test_prints_startup_block(self):
        server = FakeServer()
        _, out = self._run(["--port", "7417"], server)
        self.assertIn("本地服务", out)
        self.assertIn("http://127.0.0.1:7417", out)

    def test_open_flag_schedules_browser(self):
        server = FakeServer()
        with mock.patch.object(app, "_schedule_open") as scheduled:
            code, _ = self._run(["--port", "7417", "--open"], server)
        self.assertEqual(code, 0)
        scheduled.assert_called_once_with("http://127.0.0.1:7417")

    def test_without_open_flag_no_browser(self):
        server = FakeServer()
        with mock.patch.object(app, "_schedule_open") as scheduled:
            self._run(["--port", "7417"], server)
        scheduled.assert_not_called()

    def test_token_shown_in_startup_output(self):
        server = FakeServer(FakeCfg(token="abc123"))
        _, out = self._run(["--port", "7417", "--token"], server)
        self.assertIn("访问令牌   abc123", out)


class LimitsAndVersionTestCase(unittest.TestCase):
    """P2-12：--version 与三个上限参数。"""

    def test_version_prints_and_exits_zero(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            with self.assertRaises(SystemExit) as ctx:
                app.main(["--version"])
        self.assertEqual(ctx.exception.code, 0)
        self.assertIn(VERSION, buf.getvalue())

    def test_parser_defaults_match_constants(self):
        args = app.build_parser().parse_args([])
        self.assertEqual(args.rate_limit, app.RATE_LIMIT)
        self.assertEqual(args.max_body, app.MAX_BODY // 1024)
        self.assertEqual(args.max_chars, app.MAX_CHARS)

    def test_parser_reads_overrides(self):
        args = app.build_parser().parse_args(
            ["--rate-limit", "5", "--max-body", "8", "--max-chars", "1200"])
        self.assertEqual((args.rate_limit, args.max_body, args.max_chars), (5, 8, 1200))

    def test_non_positive_rejected(self):
        for flag in ("--rate-limit", "--max-body", "--max-chars"):
            with self.assertRaises(SystemExit):
                with contextlib.redirect_stderr(io.StringIO()):
                    app.build_parser().parse_args([flag, "0"])

    def test_build_server_passes_limits_through(self):
        args = app.build_parser().parse_args(
            ["--port", "0", "--rate-limit", "7", "--max-body", "9", "--max-chars", "1500"])
        server, _port = app.build_server(args)
        try:
            self.assertEqual(server.cfg.max_body, 9 * 1024)
            self.assertEqual(server.cfg.max_chars, 1500)
            self.assertEqual(server.cfg.limiter.limit, 7)
        finally:
            server.server_close()


class ImageGrayFlagTestCase(unittest.TestCase):
    """灰度开关的默认值与透传：默认开启图像、默认方言 generic、反馈默认落 logs/。"""

    def test_defaults_are_on(self):
        args = app.build_parser().parse_args([])
        self.assertEqual(args.enable_image, "on")
        self.assertEqual(args.image_platform, "generic")
        self.assertEqual(args.feedback_log, app.DEFAULT_FEEDBACK_LOG)
        self.assertFalse(args.no_feedback_log)

    def test_off_and_platform_parsed(self):
        args = app.build_parser().parse_args(["--enable-image", "off", "--image-platform", "mj"])
        self.assertEqual((args.enable_image, args.image_platform), ("off", "mj"))

    def test_unknown_platform_rejected(self):
        with self.assertRaises(SystemExit):
            with contextlib.redirect_stderr(io.StringIO()):
                app.build_parser().parse_args(["--image-platform", "midjourney"])

    def test_feedback_path_resolves_against_program_dir(self):
        self.assertEqual(app.feedback_path("logs/a.log"), app.ROOT_DIR / "logs" / "a.log")
        self.assertIsNone(app.feedback_path(None))

    def test_build_server_wires_gray_state(self):
        server, _port = app.build_server(make_args(enable_image="off", image_platform="flux"))
        try:
            self.assertFalse(server.cfg.enable_image)
            self.assertEqual(server.cfg.image_platform, "flux")
            self.assertIsNone(server.cfg.feedback_log, "--no-feedback-log 应为 None")
        finally:
            server.server_close()

    def test_feedback_log_default_path_wired(self):
        server, _port = app.build_server(
            make_args(no_feedback_log=False, feedback_log=app.DEFAULT_FEEDBACK_LOG))
        try:
            self.assertEqual(server.cfg.feedback_log, app.feedback_path(app.DEFAULT_FEEDBACK_LOG))
        finally:
            server.server_close()

    def test_startup_lines_show_gray_state(self):
        lines = "\n".join(app.startup_lines(
            URL, None, "127.0.0.1",
            image={"enabled": False, "platform": "mj"}, feedback="logs/feedback.log"))
        self.assertIn("图像灰度", lines)
        self.assertIn("回滚态", lines)
        self.assertIn("反馈日志", lines)


class ConsoleEncodingTestCase(unittest.TestCase):
    """en-US 的 Windows 控制台（含 GitHub Actions runner）默认 cp1252。

    CI 首跑时 ubuntu 全绿、windows 两个组合都红，根因就是中文摘要打印抛
    UnicodeEncodeError：用例全过，但进程以非零码退出。这里用子进程复现该环境。
    """

    def _run(self, args: list[str]) -> subprocess.CompletedProcess:
        env = dict(os.environ, PYTHONIOENCODING="cp1252")
        # 子进程会强制 UTF-8 输出，父进程必须按 UTF-8 解码（用 text=True 会按本机 gbk 解）
        return subprocess.run([sys.executable, *args], cwd=str(ROOT), env=env,
                              capture_output=True, encoding="utf-8",
                              errors="replace", timeout=120)

    def test_run_entry_forces_utf8_stdout(self):
        done = self._run(["-c", "import sys; sys.path.insert(0, 'tests'); import run; "
                                "print('运行 1 个用例')"])
        self.assertEqual(done.returncode, 0, done.stderr[-300:])
        self.assertIn("运行 1 个用例", done.stdout)

    def test_app_help_prints_on_cp1252(self):
        done = self._run(["server/app.py", "--help"])
        self.assertEqual(done.returncode, 0, done.stderr[-300:])


if __name__ == "__main__":
    unittest.main()
