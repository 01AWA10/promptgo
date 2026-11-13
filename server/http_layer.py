"""HTTP 传输层：路由、CORS、令牌鉴权、限流、SSE 编码与静态资源。

只使用标准库，确保离线机器无需 pip install 即可运行。
"""

from __future__ import annotations

import json
import socketserver
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from engine import META, EnhanceError, enhance, stream
from engine import __version__ as VERSION   # 版本唯一来源：engine.__version__

# 三个上限的默认值；实际取值由 app.py 的命令行参数经 AppConfig 注入
MAX_BODY = 64 * 1024     # 请求体上限（字节）
RATE_LIMIT = 90          # 每分钟请求数（本地单用户足够）

STATIC_ROUTES = {
    "/": "web/demo/index.html",
    "/demo": "web/demo/index.html",
    "/demo/": "web/demo/index.html",
    "/prompt-enhancer.js": "web/prompt-enhancer.js",
    "/demo/app.css": "web/demo/app.css",
    "/favicon.ico": None,
}

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".woff2": "font/woff2",
    ".woff": "font/woff",
}


class RateLimiter:
    def __init__(self, limit: int, window: float = 60.0):
        self.limit = limit
        self.window = window
        self._hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            # 长期运行时清理已过期的来源，避免字典随访问者数量无限增长
            if len(self._hits) > 256:
                self._hits = {k: v for k, v in self._hits.items()
                              if v and now - v[-1] < self.window}
            bucket = [t for t in self._hits.get(key, []) if now - t < self.window]
            if len(bucket) >= self.limit:
                self._hits[key] = bucket
                return False
            bucket.append(now)
            self._hits[key] = bucket
            return True


class AppConfig:
    def __init__(self, root: Path, origins: list[str] | None = None,
                 token: str | None = None, pace: float = 0.006, quiet: bool = False,
                 max_body: int = MAX_BODY, rate_limit: int = RATE_LIMIT,
                 max_chars: int | None = None):
        self.root = root
        self.origins = origins or ["*"]
        self.token = token
        self.pace = pace
        self.quiet = quiet
        self.max_body = max_body
        self.rate_limit = rate_limit
        self.max_chars = META["limits"]["max_chars"] if max_chars is None else max_chars
        self.limiter = RateLimiter(self.rate_limit)
        self.started_at = time.time()


class Handler(BaseHTTPRequestHandler):
    server_version = "PromptGo/" + VERSION
    protocol_version = "HTTP/1.1"

    # ------------------------------------------------------------ 基础设施
    @property
    def cfg(self) -> AppConfig:
        return self.server.cfg  # type: ignore[attr-defined]

    def log_message(self, fmt: str, *args) -> None:
        if self.cfg.quiet:
            return
        print("[%s] %s" % (self.log_date_time_string(), fmt % args))

    def handle_one_request(self) -> None:
        """客户端提前断开（关页、截图、中断请求）不是错误，静默关闭连接。

        否则 socketserver 会把 ConnectionResetError 的完整 traceback 打到 stderr，
        本地工具的日志会被无意义的噪声淹没。
        """
        try:
            super().handle_one_request()
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            self.close_connection = True

    def _cors(self) -> None:
        origin = self.headers.get("Origin")
        if self.cfg.origins == ["*"]:
            allow = "*"
        elif origin and origin in self.cfg.origins:
            allow = origin
        else:
            allow = ""          # 白名单外不回显任何来源，由浏览器拒绝
        if allow:
            self.send_header("Access-Control-Allow-Origin", allow)
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, X-PE-Token")
        self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Max-Age", "86400")

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self._cors()
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _error(self, status: int, code: str, message: str) -> None:
        self._send_json(status, {"ok": False, "error": {"code": code, "message": message}})

    def _discard_body(self, length: int) -> None:
        """排空客户端仍在发送的请求体。

        413 之前不读请求体就关闭连接时，接收缓冲区里残留数据会让内核发 RST，
        把刚写出的响应一起丢掉——Windows 上表现为客户端「未收到任何响应字节」。
        只排空有限量并加短超时，避免客户端虚报 Content-Length 拖住工作线程。
        """
        budget = min(length, 1 << 20)
        try:
            prev = self.connection.gettimeout()
        except OSError:
            return
        try:
            self.connection.settimeout(1.0)
            while budget > 0:
                chunk = self.rfile.read(min(65536, budget))
                if not chunk:
                    break
                budget -= len(chunk)
        except (OSError, ValueError):
            pass
        finally:
            try:
                self.connection.settimeout(prev)
            except OSError:
                pass

    def _read_json(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except (TypeError, ValueError):
            raise EnhanceError("BAD_LENGTH", "Content-Length 不是合法整数", 400)
        if length <= 0:
            raise EnhanceError("EMPTY_BODY", "请求体为空", 411)
        if length > self.cfg.max_body:
            self._discard_body(length)
            raise EnhanceError("BODY_TOO_LARGE",
                               f"请求体超过 {self.cfg.max_body // 1024}KB", 413)
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise EnhanceError("BAD_JSON", "请求体必须是 UTF-8 编码的 JSON", 400)
        if not isinstance(data, dict):
            raise EnhanceError("BAD_JSON", "请求体必须是 JSON 对象", 400)
        return data

    def _authorized(self) -> bool:
        if not self.cfg.token:
            return True
        return self.headers.get("X-PE-Token") == self.cfg.token

    # ------------------------------------------------------------ 路由
    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]

        if path == "/v1/health":
            self._send_json(200, {
                "ok": True,
                "service": "promptgo-enhancer",
                "version": VERSION,
                "engine": "rule-based",
                "offline": True,
                "auth_required": bool(self.cfg.token),
                "uptime_s": round(time.time() - self.cfg.started_at, 1),
                "max_chars": self.cfg.max_chars,
            })
            return

        if path == "/v1/meta":
            # 上限随启动参数变化，元数据必须如实反映，否则前端会按旧值截断
            self._send_json(200, {"ok": True, **META, "limits": {"max_chars": self.cfg.max_chars}})
            return

        if path in STATIC_ROUTES:
            target = STATIC_ROUTES[path]
            if target is None:
                self.send_response(204)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            self._serve_file(target)
            return

        # web/ 目录下的静态资源直出（限定后缀 + 强制限定在 web/ 内，见 _serve_file）
        if path.lower().endswith((".html", ".css", ".js", ".svg", ".png", ".woff2")):
            self._serve_file("web" + path, base="web")
            return

        self._error(404, "NOT_FOUND", f"未找到路径 {path}")

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path not in ("/v1/enhance", "/v1/enhance/stream"):
            self._error(404, "NOT_FOUND", f"未找到路径 {path}")
            return

        if not self._authorized():
            self._error(401, "UNAUTHORIZED", "缺少或错误的 X-PE-Token")
            return

        ip = self.client_address[0]
        if not self.cfg.limiter.allow(ip):
            self._error(429, "RATE_LIMITED", "请求过于频繁，请稍后再试")
            return

        try:
            payload = self._read_json()
        except EnhanceError as exc:
            self._error(exc.status, exc.code, exc.message)
            return

        if path == "/v1/enhance":
            self._handle_json(payload)
        else:
            self._handle_stream(payload)

    # ------------------------------------------------------------ 处理器
    def _handle_json(self, payload: dict) -> None:
        try:
            result = enhance(payload, max_chars=self.cfg.max_chars)
        except EnhanceError as exc:
            self._error(exc.status, exc.code, exc.message)
            return
        except Exception as exc:  # noqa: BLE001
            self._error(500, "ENGINE_ERROR", f"引擎内部错误：{exc}")
            return
        self._send_json(200, {"ok": True, **result})

    def _handle_stream(self, payload: dict) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store, no-transform")
        self.send_header("Connection", "close")
        self.send_header("X-Accel-Buffering", "no")
        self._cors()
        self.end_headers()
        self.close_connection = True

        def write_event(event: str, data: dict) -> None:
            frame = f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
            self.wfile.write(frame.encode("utf-8"))
            self.wfile.flush()

        try:
            for event, data in stream(payload, pace=self.cfg.pace,
                                      max_chars=self.cfg.max_chars):
                write_event(event, data)
        except EnhanceError as exc:
            write_event("error", {"code": exc.code, "message": exc.message})
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception as exc:  # noqa: BLE001
            try:
                write_event("error", {"code": "ENGINE_ERROR", "message": str(exc)})
            except Exception:  # noqa: BLE001
                pass

    def _serve_file(self, relative: str, base: str = "") -> None:
        """只允许读取 base 子目录内的文件，杜绝 `../` 越界。

        直出分支必须传 base="web"，否则 `/../server/app.py` 这类请求
        在 resolve() 之后会落回项目根目录，仅靠后缀白名单兜底并不可靠。
        """
        root = self.cfg.root.resolve()
        base_dir = (root / base).resolve() if base else root
        file_path = (root / relative).resolve()
        if base_dir not in file_path.parents or not file_path.is_file():
            self._error(404, "NOT_FOUND", "资源不存在")
            return
        data = file_path.read_bytes()
        ctype = CONTENT_TYPES.get(file_path.suffix.lower(), "application/octet-stream")
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self._cors()
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass


class EnhancerServer(ThreadingHTTPServer):
    daemon_threads = True
    # 保留 reuse_address 以便「停止后立刻重启」不撞 TIME_WAIT。
    # 注意：Windows 上它会让同端口重复 bind 成功，因此端口占用判定
    # 必须走 app._port_in_use() 的连接探测，不能用 bind 试探。
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], cfg: AppConfig):
        self.cfg = cfg
        super().__init__(address, Handler)

    def server_bind(self) -> None:
        """跳过 HTTPServer 的 socket.getfqdn()。

        精简版 Python 可能缺失 encodings.idna，导致 getfqdn 抛 LookupError；
        本地服务只需要回环地址，直接使用 host 作为 server_name 即可。
        """
        socketserver.TCPServer.server_bind(self)
        host, port = self.server_address[:2]
        self.server_name = str(host)
        self.server_port = int(port)

    def handle_error(self, request, client_address) -> None:  # noqa: ANN001
        """兜底：断开类异常不打印 traceback，其余照常转交。"""
        exc = sys.exc_info()[1]
        if isinstance(exc, (ConnectionResetError, ConnectionAbortedError, BrokenPipeError)):
            return
        super().handle_error(request, client_address)
