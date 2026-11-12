"""打包形态测试：验证静态资源根目录在三种运行形态下都能正确解析。

exe 本体可能被企业策略（Application Control / WDAC）阻止执行，
因此把「路径解析」与「资源是否打进包」拆成可自动化的断言。
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))

import app  # noqa: E402
from engine import __version__ as ENGINE_VERSION  # noqa: E402
from http_layer import AppConfig, EnhancerServer  # noqa: E402
from http_layer import VERSION as HTTP_VERSION  # noqa: E402


class BundleRootTestCase(unittest.TestCase):
    def setUp(self):
        self._frozen = getattr(sys, "frozen", None)
        self._meipass = getattr(sys, "_MEIPASS", None)
        self._argv = sys.argv

    def tearDown(self):
        for name, value in (("frozen", self._frozen), ("_MEIPASS", self._meipass)):
            if value is None:
                if hasattr(sys, name):
                    delattr(sys, name)
            else:
                setattr(sys, name, value)
        sys.argv = self._argv

    def _clear_frozen(self):
        if hasattr(sys, "frozen"):
            del sys.frozen
        if hasattr(sys, "_MEIPASS"):
            del sys._MEIPASS

    def test_source_mode_uses_project_root(self):
        self._clear_frozen()
        sys.argv = [str(ROOT / "server" / "app.py")]
        self.assertEqual(app.bundle_root(), ROOT)

    def test_pyinstaller_mode_uses_meipass(self):
        sys.frozen = True
        fake = ROOT / "dist" / "_mei"
        sys._MEIPASS = str(fake)
        self.assertEqual(app.bundle_root(), fake)

    def test_pyinstaller_mode_falls_back_to_exe_dir(self):
        sys.frozen = True
        if hasattr(sys, "_MEIPASS"):
            del sys._MEIPASS
        self.assertEqual(app.bundle_root(), Path(sys.executable).parent)

    def test_zipapp_mode_uses_archive_dir(self):
        self._clear_frozen()
        sys.argv = [str(ROOT / "promptgo.pyz")]
        self.assertEqual(app.bundle_root(), ROOT)

    def test_web_assets_present_next_to_root(self):
        """源码形态下 web/ 必须与资源根同级存在，否则静态路由 404。"""
        self._clear_frozen()
        self.assertTrue((app.bundle_root() / "web" / "prompt-enhancer.js").is_file())
        self.assertTrue((app.bundle_root() / "web" / "demo" / "index.html").is_file())


class VersionConsistencyTestCase(unittest.TestCase):
    """版本号只维护一处（engine.__version__）：HTTP 层直接引用，前端由用例守护。"""

    def test_http_layer_reuses_engine_version(self):
        self.assertEqual(HTTP_VERSION, ENGINE_VERSION)

    def test_component_version_matches_engine(self):
        js = (ROOT / "web" / "prompt-enhancer.js").read_text(encoding="utf-8")
        found = re.search(r'var VERSION = "([^"]+)"', js)
        self.assertIsNotNone(found, "组件内找不到 VERSION 声明")
        self.assertEqual(found.group(1), ENGINE_VERSION, "组件版本与引擎版本不一致")

    def test_demo_version_filled_at_runtime(self):
        html = (ROOT / "web" / "demo" / "index.html").read_text(encoding="utf-8")
        self.assertIn('<span id="ver">', html)
        self.assertNotIn("PromptGo v1.0 ·", html, "页脚不应硬编码版本，应由 /v1/health 回填")


class StaticAssetMimeTestCase(unittest.TestCase):
    """图片/字体必须带正确 MIME，否则浏览器按 octet-stream 处理会拒绝渲染。"""

    def setUp(self):
        self.asset = ROOT / "web" / "_mime_probe.png"
        self.asset.write_bytes(b"\x89PNG\r\n\x1a\n")
        cfg = AppConfig(root=ROOT, origins=["*"], token=None, pace=0.0, quiet=True)
        self.server = EnhancerServer(("127.0.0.1", 0), cfg)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.addCleanup(self.asset.unlink, True)

    def test_png_served_as_image_png(self):
        with urllib.request.urlopen(self.base + "/_mime_probe.png", timeout=5) as res:
            self.assertEqual(res.headers["Content-Type"], "image/png")

    def test_font_suffix_mapped(self):
        from http_layer import CONTENT_TYPES
        self.assertEqual(CONTENT_TYPES[".woff2"], "font/woff2")


class ZipappPackagingTestCase(unittest.TestCase):
    """P2-8：zipapp 产物可独立运行，静态资源随包复制到同级目录。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="pg-zipapp-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def _build(self):
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        import build
        return build.build_zipapp(out_dir=self.tmp)

    def test_archive_layout(self):
        pyz = self._build()
        with zipfile.ZipFile(pyz) as archive:
            names = archive.namelist()
        for required in ("__main__.py", "app.py", "http_layer.py", "engine/pipeline.py"):
            self.assertIn(required, names)
        self.assertFalse([n for n in names if "__pycache__" in n], "不应把字节码缓存打进归档")
        self.assertLess(pyz.stat().st_size, 500 * 1024, "pyz 应远小于 7.7 MB 的 exe")

    def test_web_copied_next_to_pyz(self):
        pyz = self._build()
        self.assertTrue((pyz.parent / "web" / "prompt-enhancer.js").is_file())
        self.assertTrue((pyz.parent / "web" / "demo" / "index.html").is_file())

    def test_pyz_runs_version(self):
        """`--version` 会真正 import app → http_layer → engine，等价于归档完整性检查。"""
        pyz = self._build()
        done = subprocess.run([sys.executable, str(pyz), "--version"],
                              capture_output=True, text=True, timeout=120)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn(ENGINE_VERSION, done.stdout)


if __name__ == "__main__":
    unittest.main()
