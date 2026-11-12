"""端口占用判定与自动顺延测试。

回归 P1-1：Windows 上 SO_REUSEADDR 允许对同一端口重复 bind，而本服务自身
也开着 reuse_address（为了快速重启）。旧实现用「能否 bind」判断占用，
导致第二个实例直接抢占同一端口而不是顺延。这里锁定新判据：只有真正有人
在监听（能建立连接）才算占用。
"""

from __future__ import annotations

import argparse
import socket
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))

import app  # noqa: E402


def make_listener(port: int = 0, reuse: bool = True) -> tuple[socket.socket, int]:
    """起一个真实监听，模拟「已被占用的端口」。"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if reuse:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", port))
    sock.listen(8)
    return sock, sock.getsockname()[1]


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def free_block(count: int, start: int = 7600, end: int = 7900) -> tuple[list[socket.socket], int]:
    """占用一段连续空闲端口；找不到就跳过用例（避免环境依赖导致的假失败）。"""
    for base in range(start, end - count):
        socks: list[socket.socket] = []
        try:
            for offset in range(count):
                sock, _ = make_listener(base + offset)
                socks.append(sock)
            return socks, base
        except OSError:
            for sock in socks:
                sock.close()
    raise unittest.SkipTest("本机找不到连续空闲端口")


def make_args(port: int, no_fallback: bool = False) -> argparse.Namespace:
    return argparse.Namespace(host="127.0.0.1", port=port, no_fallback=no_fallback,
                              allow_origin=None, token=None, pace=6, quiet=True,
                              rate_limit=app.RATE_LIMIT, max_body=app.MAX_BODY // 1024,
                              max_chars=app.MAX_CHARS)


class PortProbeTestCase(unittest.TestCase):
    def test_listening_port_detected_even_with_reuseaddr(self):
        """核心回归：同款实例（开着 reuse_address）占用端口时必须判定为占用。"""
        sock, port = make_listener(reuse=True)
        try:
            self.assertTrue(app._port_in_use("127.0.0.1", port))
        finally:
            sock.close()

    def test_listening_port_detected_without_reuseaddr(self):
        sock, port = make_listener(reuse=False)
        try:
            self.assertTrue(app._port_in_use("127.0.0.1", port))
        finally:
            sock.close()

    def test_closed_port_is_free(self):
        sock, port = make_listener()
        sock.close()
        self.assertFalse(app._port_in_use("127.0.0.1", port))

    def test_wildcard_host_probes_loopback(self):
        sock, port = make_listener()
        try:
            self.assertTrue(app._port_in_use("0.0.0.0", port))
        finally:
            sock.close()


class PickPortTestCase(unittest.TestCase):
    def test_pick_skips_occupied_neighbor(self):
        sock, port = make_listener()
        try:
            picked = app.pick_port("127.0.0.1", port, attempts=3)
        finally:
            sock.close()
        self.assertNotEqual(picked, port)
        self.assertIn(picked, range(port, port + 3))

    def test_pick_raises_when_all_occupied(self):
        socks, base = free_block(3)
        try:
            with self.assertRaises(SystemExit) as ctx:
                app.pick_port("127.0.0.1", base, attempts=3)
            self.assertIn("均被占用", str(ctx.exception))
        finally:
            for sock in socks:
                sock.close()


class BuildServerTestCase(unittest.TestCase):
    def test_falls_back_to_next_port(self):
        sock, port = make_listener()
        server = None
        try:
            server, actual = app.build_server(make_args(port))
            self.assertNotEqual(actual, port)
            self.assertIn(actual, range(port, port + app.PORT_ATTEMPTS))
        finally:
            if server is not None:
                server.server_close()
            sock.close()

    def test_no_fallback_rejects_occupied_port(self):
        sock, port = make_listener()
        try:
            with self.assertRaises(SystemExit) as ctx:
                app.build_server(make_args(port, no_fallback=True))
            self.assertIn("已被占用", str(ctx.exception))
        finally:
            sock.close()

    def test_restart_on_same_port_still_allowed(self):
        """顺延修好后不能反过来限制快速重启：关闭后应立即能重新绑定同一端口。"""
        port = free_port()
        first, bound = app.build_server(make_args(port))
        self.assertEqual(bound, port)
        first.server_close()
        second, bound_again = app.build_server(make_args(port))
        try:
            self.assertEqual(bound_again, port)
        finally:
            second.server_close()


if __name__ == "__main__":
    unittest.main()
