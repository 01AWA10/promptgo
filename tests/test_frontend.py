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
DEMO = ROOT / "web" / "demo" / "index.html"        # 使用者入口：输入 → 增强 → 结果回填
DEV_PAGE = ROOT / "web" / "demo" / "dev.html"      # 开发者视图：字段表、事件总线、接入代码
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
    def test_dev_page_shows_channels_and_tones(self):
        """P2-7：开发者视图需暴露渠道/语气/章节/待确认，并用 /v1/meta 渲染清单。"""
        html = DEV_PAGE.read_text(encoding="utf-8")
        for anchor in ('id="out-channel"', 'id="out-tone"',
                       'id="out-sections"', 'id="out-missing"'):
            self.assertIn(anchor, html)
        self.assertIn("/v1/meta", html)

    def test_dev_page_budget_tag_matches_budget(self):
        """页面标签与用例预算必须是同一个数，否则调预算时会留下过期文案。"""
        html = DEV_PAGE.read_text(encoding="utf-8")
        self.assertIn(f"&lt; {SIZE_BUDGET // 1024} KB", html)

    def test_user_page_keeps_only_input_and_result(self):
        """使用者入口只保留「输入 → 增强 → 结果回填」，不出现字段表/事件总线。"""
        html = DEMO.read_text(encoding="utf-8")
        for anchor in ('id="prompt-input"', "<prompt-enhancer", 'id="out-text"'):
            self.assertIn(anchor, html)
        for leaked in ('id="out-intent"', 'id="out-sections"', 'id="log"', "事件总线"):
            self.assertNotIn(leaked, html)

    def test_user_page_links_to_dev_view(self):
        html = DEMO.read_text(encoding="utf-8")
        self.assertIn('href="/demo/dev"', html)

    def test_branch_defaults_to_plain_and_hides_platform(self):
        """默认「普通」分支：方案下拉必须收起，模式与深度可见（靠 syncPanel 切显隐）。"""
        html = DEMO.read_text(encoding="utf-8")
        self.assertEqual(html.count('class="branch-btn'), 2)
        self.assertIn('data-branch="text" aria-pressed="true"', html)
        self.assertIn('applyBranch("text");', html)
        self.assertIn("syncPanel", html)
        self.assertIn('BRANCH === "image" ? "none" : ""', html)

    def test_ten_examples_split_five_by_five(self):
        html = DEMO.read_text(encoding="utf-8")
        self.assertEqual(html.count('class="ex"'), 10, "应有 10 条组合示例")
        head, _, tail = html.partition('data-branch="image" hidden')
        self.assertEqual(head.count('class="ex"'), 5, "普通分支应 5 条")
        self.assertEqual(tail.count('class="ex"'), 5, "文生图分支应 5 条")
        for platform in ("generic", "mj", "sdxl", "flux", "dalle3"):
            self.assertIn(f'data-platform="{platform}"', html)

    def test_option_notes_cover_three_selects(self):
        html = DEMO.read_text(encoding="utf-8")
        for label in ("增强模式", "增强深度", "增强方案"):
            self.assertIn(label, html)
        self.assertIn('data-for="text"', html)
        self.assertIn('data-for="image"', html)

    def test_plain_branch_warns_on_image_intent(self):
        """普通分支下识别出出图意图：不阻断，只提示可切分支换平台参数。"""
        html = DEMO.read_text(encoding="utf-8")
        self.assertIn('id="intent-hint"', html)
        self.assertIn('a.intent === "image" && BRANCH === "text"', html)
        self.assertIn("/demo/dev", html)


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
