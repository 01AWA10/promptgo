"""PromptGo 本地增强服务 · 启动入口。

用法：
    python server/app.py                       # 默认 127.0.0.1:7317
    python server/app.py --port 7400           # 指定端口
    python server/app.py --token               # 随机软令牌（跨机器访问时建议开启）
    python server/app.py --allow-origin https://a.com --allow-origin https://b.com

零第三方依赖：仅使用 Python 标准库，离线机器拷贝即可运行。
"""

from __future__ import annotations

import argparse
import secrets
import socket
import sys
import threading
import webbrowser
from pathlib import Path

def bundle_root() -> Path:
    """静态资源根目录，兼容三种运行形态。

    1. 源码运行：项目根（`server/app.py` 的上一级）
    2. PyInstaller onefile：`sys._MEIPASS` 解包目录（`--add-data web;web` 落在其下）
    3. zipapp (.pyz)：归档文件所在目录
    """
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    entry = Path(sys.argv[0]).resolve()
    if entry.suffix.lower() == ".pyz":
        return entry.parent
    return Path(__file__).resolve().parent.parent


SERVER_DIR = Path(__file__).resolve().parent
ROOT_DIR = bundle_root()
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from engine import MAX_CHARS  # noqa: E402
from http_layer import MAX_BODY, RATE_LIMIT, VERSION, AppConfig, EnhancerServer  # noqa: E402

DEFAULT_PORT = 7317
PORT_ATTEMPTS = 6
BANNER = """
  ____                       _    ____
 |  _ \\ _ __ ___  _ __ ___  | |_ / ___| ___
 | |_) | '__/ _ \\| '_ ` _ \\ | __| |  _ / _ \\
 |  __/| | | (_) | | | | | || |_| |_| | (_) |
 |_|   |_|  \\___/|_| |_| |_| \\__|\\____|\\___/   offline prompt enhancer v{version}
"""


def _probe_host(host: str) -> str:
    """监听在通配地址时，用回环地址做探测。"""
    return "127.0.0.1" if host in ("", "0.0.0.0", "::") else host


def _port_in_use(host: str, port: int) -> bool:
    """端口上是否真的有人在监听。

    Windows 允许对同一端口重复 bind（SO_REUSEADDR），而本服务自身为了快速重启
    也开着 reuse_address，因此「能不能 bind」不能当作空闲判据：用旧实现判断时，
    第二个 PromptGo 实例会直接抢占 7317 而不是顺延到 7318。
    这里改为实际发起一次连接——只有「连接被拒绝」才算空闲。
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(0.25)
    try:
        sock.connect((_probe_host(host), port))
        return True
    except ConnectionRefusedError:
        return False
    except OSError:
        # 超时/不可达等情况无法确证：按空闲处理，随后的真实 bind 会兜底
        return False
    finally:
        sock.close()


def pick_port(host: str, preferred: int, attempts: int = PORT_ATTEMPTS) -> int:
    for offset in range(attempts):
        candidate = preferred + offset
        if not _port_in_use(host, candidate):
            return candidate
    raise SystemExit(f"端口 {preferred}–{preferred + attempts - 1} 均被占用，请用 --port 指定其他端口")


def _resolve_token(value) -> str | None:
    """`--token` 未给值时（const=True）随机生成，给值时沿用用户值。"""
    if not value:
        return None
    return value if isinstance(value, str) else secrets.token_urlsafe(12)


def _positive_int(text: str) -> int:
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"不是整数：{text}")
    if value <= 0:
        raise argparse.ArgumentTypeError("必须是正整数")
    return value


def build_parser() -> argparse.ArgumentParser:
    """命令行定义单独抽出：测试可直接解析参数，不必真的启动服务。"""
    parser = argparse.ArgumentParser(description="PromptGo 离线提示词增强服务")
    parser.add_argument("--version", action="version", version=f"PromptGo {VERSION}")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址，默认仅本机回环")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"监听端口，默认 {DEFAULT_PORT}")
    parser.add_argument("--no-fallback", action="store_true", help="端口被占用时直接失败，不自动顺延")
    parser.add_argument("--allow-origin", action="append", metavar="ORIGIN",
                        help="允许的跨域来源，可重复；缺省为 *")
    parser.add_argument("--token", nargs="?", const=True, default=None,
                        help="开启软令牌鉴权，可自定义值，缺省随机生成")
    parser.add_argument("--pace", type=float, default=6, help="流式吐字间隔（毫秒），0 表示关闭")
    parser.add_argument("--quiet", action="store_true", help="不打印访问日志")
    parser.add_argument("--open", action="store_true", help="启动后打开演示页")
    parser.add_argument("--rate-limit", type=_positive_int, default=RATE_LIMIT, metavar="N",
                        help=f"每分钟请求上限，默认 {RATE_LIMIT}")
    parser.add_argument("--max-body", type=_positive_int, default=MAX_BODY // 1024, metavar="KB",
                        help=f"请求体上限（KB），默认 {MAX_BODY // 1024}")
    parser.add_argument("--max-chars", type=_positive_int, default=MAX_CHARS, metavar="N",
                        help=f"单次输入字符上限，默认 {MAX_CHARS}")
    return parser


def build_server(args: argparse.Namespace) -> tuple[EnhancerServer, int]:
    host = args.host
    token = _resolve_token(args.token)
    cfg = AppConfig(
        root=ROOT_DIR,
        origins=args.allow_origin or ["*"],
        token=token,
        pace=args.pace / 1000.0,
        quiet=args.quiet,
        rate_limit=args.rate_limit,
        max_body=args.max_body * 1024,
        max_chars=args.max_chars,
    )

    if args.no_fallback:
        if _port_in_use(host, args.port):
            raise SystemExit(f"端口 {args.port} 已被占用（--no-fallback 已关闭顺延）")
        return EnhancerServer((host, args.port), cfg), args.port

    last_error: OSError | None = None
    for offset in range(PORT_ATTEMPTS):
        port = args.port + offset
        if _port_in_use(host, port):
            continue
        try:
            return EnhancerServer((host, port), cfg), port
        except OSError as exc:      # 探测与绑定之间的竞态：换下一个端口
            last_error = exc
    message = f"端口 {args.port}–{args.port + PORT_ATTEMPTS - 1} 均被占用，请用 --port 指定其他端口"
    if last_error is not None:
        message += f"（最后一次绑定错误：{last_error}）"
    raise SystemExit(message)


def banner(version: str = VERSION) -> str:
    """启动横幅（纯函数，便于断言文案）。"""
    return BANNER.format(version=version)


def startup_lines(url: str, token: str | None, host: str) -> list[str]:
    """启动摘要的每一行（纯函数：不读全局、不打印、不打开浏览器）。

    注意：这里只能用 GBK 可编码的字符——中文 Windows 控制台默认 cp936，
    历史实现里的 U+26A0「⚠」会在 `--host 0.0.0.0` 时直接抛 UnicodeEncodeError。
    """
    lines = [
        banner(),
        f"  本地服务   {url}",
        f"  演示页     {url}/demo/",
        f"  组件地址   {url}/prompt-enhancer.js",
    ]
    if token:
        lines.append(f"  访问令牌   {token}")
        lines.append('            嵌入时写为 <prompt-enhancer token="...">')
    if host not in ("127.0.0.1", "localhost"):
        lines.append("  【警告】已监听非回环地址，请确认网络环境可信")
    lines.extend([
        "",
        "  嵌入代码：",
        f'  <script src="{url}/prompt-enhancer.js" defer></script>',
        '  <prompt-enhancer target="#your-input" mode="bubble"></prompt-enhancer>',
        "",
        "  Ctrl+C 停止",
        "",
    ])
    return lines


def _schedule_open(url: str, delay: float = 0.6, timer=threading.Timer):
    """延迟打开演示页。timer 可注入，测试时无需真的等 0.6 秒。"""
    handle = timer(delay, lambda: webbrowser.open(f"{url}/demo/"))
    handle.start()
    return handle


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    server, port = build_server(args)
    url = f"http://{args.host}:{port}"

    print("\n".join(startup_lines(url, server.cfg.token, args.host)))

    if args.open:
        _schedule_open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
