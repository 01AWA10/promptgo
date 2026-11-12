"""前端最小冒烟测试（Node + node:vm，无需浏览器与 jsdom）。

覆盖三块最容易悄悄坏掉、又完全没被 Python 测试触达的逻辑：
1. SSE 手工分帧：跨块半帧、一包多帧、脏帧、逐字节喂入；
2. `target` 回填：写值 + 派发 input/change + 聚焦；
3. JSON 回退：无 `ReadableStream` 时改走一次性接口，以及错误消息映射。

本机没有 Node 时整组跳过（`skipUnless`），不会让 `py tests/run.py` 变红；
需要强制指定解释器时设置环境变量 `NODE=<path>`。
CI 用 `python tests/run.py --strict`：跳过会被升级为失败，确保这组用例真的跑过。
"""

from __future__ import annotations

import glob
import os
import re
import shutil
import subprocess
import sys
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))

from http_layer import AppConfig, EnhancerServer  # noqa: E402

COMPONENT = ROOT / "web" / "prompt-enhancer.js"
SMOKE = ROOT / "tests" / "frontend" / "smoke.mjs"
DEMO = ROOT / "web" / "demo" / "index.html"
SIZE_BUDGET = 44 * 1024   # 2026-11-12 由 40 KB 上调：导航与筛选维度落地后余量不足


def find_node() -> str | None:
    explicit = os.environ.get("NODE")
    if explicit and Path(explicit).is_file():
        return explicit
    found = shutil.which("node")
    if found:
        return found
    # IDE 托管的运行时：不在 PATH，但本机可用
    pattern = str(Path.home() / ".workbuddy" / "binaries" / "node" / "versions" / "*" / "node.exe")
    for candidate in sorted(glob.glob(pattern), reverse=True):
        if Path(candidate).is_file():
            return candidate
    return None


NODE = find_node()


class ComponentBudgetTestCase(unittest.TestCase):
    def test_component_within_size_budget(self):
        """44 KB 是硬约束：新增交互前先看余量，别等发版才发现超标。"""
        size = COMPONENT.stat().st_size
        self.assertLessEqual(size, SIZE_BUDGET, f"组件 {size} B 已超出 {SIZE_BUDGET} B")

    def test_component_has_section_nav(self):
        """P2-6：章节导航容器、选择器与 plan 事件驱动三者必须同时存在。"""
        src = COMPONENT.read_text(encoding="utf-8")
        self.assertIn('class="pg-nav"', src)
        self.assertIn('nav: q(".pg-nav")', src)
        self.assertIn(".pg-nav{", src)
        self.assertIn("_renderNav(ev.data.sections)", src)


class DemoPageTestCase(unittest.TestCase):
    def test_demo_shows_channels_and_tones(self):
        """P2-7：演示页需暴露渠道/语气/章节/待确认，并用 /v1/meta 渲染清单。"""
        html = DEMO.read_text(encoding="utf-8")
        for anchor in ('id="out-channel"', 'id="out-tone"',
                       'id="out-sections"', 'id="out-missing"'):
            self.assertIn(anchor, html)
        self.assertIn("/v1/meta", html)

    def test_demo_budget_tag_matches_budget(self):
        """页面标签与用例预算必须是同一个数，否则调预算时会留下过期文案。"""
        html = DEMO.read_text(encoding="utf-8")
        self.assertIn(f"&lt; {SIZE_BUDGET // 1024} KB", html)


@unittest.skipUnless(NODE, "未找到 Node（可设 NODE=<path> 或安装 node）")
class FrontendSmokeTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cfg = AppConfig(root=ROOT, origins=["*"], token=None, pace=0.0, quiet=True)
        cls.server = EnhancerServer(("127.0.0.1", 0), cfg)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

        cls.result = subprocess.run(
            [NODE, str(SMOKE), "--endpoint", f"http://127.0.0.1:{cls.port}"],
            cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", timeout=120,
        )

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_smoke_exits_zero(self):
        self.assertEqual(self.result.returncode, 0, self.result.stdout + self.result.stderr)

    def test_no_failed_check(self):
        self.assertIn("FAIL 0", self.result.stdout, self.result.stdout)

    def test_covers_framing_target_and_json_fallback(self):
        out = self.result.stdout
        self.assertGreaterEqual(len(re.findall(r"^ok   ", out, re.M)), 15, out)
        self.assertIn("drainFrames 逐字节喂入仍按序还原", out)
        self.assertIn("writeTarget 写值并派发 input/change", out)
        self.assertIn("sectionList 归一化 plan.sections", out)
        self.assertIn("端到端 JSON 回退（真实服务）", out)


if __name__ == "__main__":
    unittest.main()
