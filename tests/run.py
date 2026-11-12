"""轻量测试入口：python tests/run.py [--strict]

与 `python -m unittest` 等价，但失败时只打印异常摘要，
避免个别环境（如缺少 unicodedata DLL 的精简 Python）在格式化 traceback 时二次报错。

`--strict` 供 CI 使用：没有被跳过的余地——缺 Node、找不到空闲端口等「环境性跳过」
一律升级为失败，避免流水线在没跑前端冒烟的情况下显示绿色。
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))
sys.path.insert(0, str(ROOT / "tests"))

# en-US 的 Windows（含 GitHub Actions runner）控制台默认 cp1252，打印中文摘要会抛
# UnicodeEncodeError，表现为「测试通过但步骤失败」。统一强制 UTF-8 输出。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass


class BriefResult(unittest.TextTestResult):
    def _exc_info_to_string(self, err, test):  # noqa: ARG002
        etype, evalue, _ = err
        return f"{etype.__name__}: {evalue}"


def main() -> int:
    strict = "--strict" in sys.argv[1:]
    if strict:
        os.environ["PG_REQUIRE_NODE"] = "1"   # 子进程（Node 冒烟调用）也继承

    loader = unittest.TestLoader()
    suite = loader.discover(str(ROOT / "tests"), pattern="test_*.py")
    runner = unittest.TextTestRunner(verbosity=2, resultclass=BriefResult)
    result = runner.run(suite)

    print("-" * 60)
    print(f"运行 {result.testsRun} 个用例 | 失败 {len(result.failures)} | "
          f"错误 {len(result.errors)} | 跳过 {len(result.skipped)}")

    ok = result.wasSuccessful()
    if strict and result.skipped:
        print(f"[strict] {len(result.skipped)} 个用例被跳过，按失败处理：")
        for case, reason in result.skipped:
            print(f"  - {case} :: {reason}")
        ok = False
    if strict and result.testsRun == 0:
        print("[strict] 没有执行任何用例")
        ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
