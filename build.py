"""打包为可分发产物（两种形态）。

用法：
    python build.py             # 形态 B：生成 dist/promptgo(.exe)，内置 web/，目标机无需 Python
    python build.py --zipapp    # 形态 C：生成 dist/promptgo.pyz + dist/web/，仅需目标机有 Python
    python build.py --clean     # 先清理 build/ 与 dist/

为什么要 zipapp：exe 在启用 WDAC/AppLocker 的机器上会被拦截，而 .pyz 只是压缩后的
Python 字节码包，产物约几百 KB、无签名问题，适合「目标机已有 Python」的场景。

前置：形态 B 需 `pip install pyinstaller`（仅打包机）；形态 C 只用标准库。
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NAME = "promptgo"
PYZ_MAIN = '''"""zipapp 入口：归档根已展开 server/ 下的模块，直接调用 app.main()。"""
import app

raise SystemExit(app.main())
'''


def build(clean: bool = False) -> int:
    if clean:
        for path in (ROOT / "build", ROOT / "dist"):
            if path.exists():
                shutil.rmtree(path, ignore_errors=True)

    # PyInstaller 的 --add-data 分隔符在 Windows 是 ;，其他平台是 :
    # 源路径必须用绝对路径：--specpath 会把相对路径解析到 spec 所在目录
    sep = ";" if sys.platform.startswith("win") else ":"
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--noconfirm",
        "--name", NAME,
        "--add-data", f"{ROOT / 'web'}{sep}web",
        "--distpath", str(ROOT / "dist"),
        "--workpath", str(ROOT / "build"),
        "--specpath", str(ROOT / "build"),
        str(ROOT / "server" / "app.py"),
    ]
    print("$ " + " ".join(cmd))
    return subprocess.call(cmd, cwd=str(ROOT))


def build_zipapp(clean: bool = False, out_dir: Path | None = None) -> Path:
    """把 server/ 打成 .pyz，并把 web/ 复制到同级目录。

    静态资源不进归档：`bundle_root()` 对 `.pyz` 取归档所在目录，放在同级即可被服务。
    """
    dist = Path(out_dir) if out_dir else (ROOT / "dist")
    if clean and dist.exists():
        for name in (f"{NAME}.pyz", "web"):
            target = dist / name
            if target.is_dir():
                shutil.rmtree(target, ignore_errors=True)
            elif target.exists():
                target.unlink()

    dist.mkdir(parents=True, exist_ok=True)
    pyz = dist / f"{NAME}.pyz"
    sources = sorted(p for p in (ROOT / "server").rglob("*.py") if "__pycache__" not in p.parts)
    with zipfile.ZipFile(pyz, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("__main__.py", PYZ_MAIN)
        for path in sources:
            archive.write(path, path.relative_to(ROOT / "server").as_posix())

    web_dst = dist / "web"
    if web_dst.exists():
        shutil.rmtree(web_dst)
    shutil.copytree(ROOT / "web", web_dst, ignore=shutil.ignore_patterns("__pycache__"))
    return pyz


def main() -> int:
    if "--zipapp" in sys.argv:
        pyz = build_zipapp(clean="--clean" in sys.argv)
        size = pyz.stat().st_size / 1024
        print(f"\n打包完成：{pyz}（{size:.0f} KB，需目标机安装 Python 3.11+）")
        print("运行：python dist/promptgo.pyz --port 7317 --open")
        print("静态资源在 dist/web/，须与 .pyz 保持同级")
        return 0

    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("未安装 PyInstaller，请先执行：pip install pyinstaller（或用 --zipapp 走免依赖形态）",
              file=sys.stderr)
        return 1

    code = build(clean="--clean" in sys.argv)
    if code == 0:
        exe = ROOT / "dist" / (NAME + (".exe" if sys.platform.startswith("win") else ""))
        size = exe.stat().st_size / (1024 * 1024) if exe.exists() else 0
        print(f"\n打包完成：{exe}（{size:.1f} MB）")
        print("运行：dist/promptgo --port 7317 --open")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
