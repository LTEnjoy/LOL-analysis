#!/usr/bin/env python3
"""Local 127.0.0.1 bridge between the static website and the League client.

Endpoints:
  GET  /               serve website/lol_stats.html
  GET  /api/status     detect client process / login session
  POST /api/sync       collect all available 5v5 Summoner's Rift custom games

Only binds 127.0.0.1. The LCU token is never written to a response or log.
"""

import argparse
import json
import os
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

try:
    import lcu_sync
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import lcu_sync

BASE = Path(__file__).resolve().parents[1]
SITE = BASE / "website" / "lol_stats.html"
DEFAULT_PORT = 8765
ALLOWED_HOSTS = {"127.0.0.1", "localhost"}
SYNC_LOCK = threading.Lock()


def origin_allowed(origin):
    if not origin or origin == "null":
        return True
    try:
        parts = urlsplit(origin)
    except ValueError:
        return False
    return parts.scheme in ("http", "https") and parts.hostname in ALLOWED_HOSTS


def build_status():
    running = lcu_sync.client_process_running()
    status = {
        "ok": True,
        "clientRunning": running,
        "loggedIn": False,
        "summoner": "",
    }
    if not running:
        status["message"] = lcu_sync.CLIENT_NOT_RUNNING_MESSAGE
        return status

    install = lcu_sync.find_install(None)
    if not install:
        status["message"] = "检测到客户端进程，但未找到安装目录，无法读取登录凭证。"
        return status

    found = lcu_sync.find_session(install)
    if not found:
        status["message"] = "客户端已启动，但未检测到有效登录会话，请确认已登录。"
        return status

    session, port, _ = found
    me, _err = lcu_sync.get_json(
        session, port, "/lol-summoner/v1/current-summoner", timeout=(3, 8),
    )
    if not isinstance(me, dict) or not me.get("puuid"):
        status["message"] = "客户端已启动，但当前账号未登录或无法读取。"
        return status

    status["loggedIn"] = True
    status["summoner"] = (
        me.get("displayName") or me.get("gameName") or me.get("summonerName") or ""
    )
    status["message"] = "已连接客户端，可以同步。"
    return status


class Handler(BaseHTTPRequestHandler):
    server_version = "LcuSyncBridge/1.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        # Keep the console clean; sync results are printed by run_sync().
        return

    def _cors_origin(self):
        origin = self.headers.get("Origin")
        if origin and origin_allowed(origin):
            return origin
        return ""

    def _send(self, status, body, content_type, extra_headers=None):
        self.send_response(status)
        origin = self._cors_origin()
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if body:
            self.wfile.write(body)

    def send_json(self, status, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8")

    def do_OPTIONS(self):
        origin = self.headers.get("Origin")
        if origin and not origin_allowed(origin):
            self.send_json(403, {"ok": False, "code": "origin-denied", "message": "来源不在白名单"})
            return
        headers = {
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, X-LCU-Sync",
            "Access-Control-Max-Age": "600",
        }
        if self.headers.get("Access-Control-Request-Private-Network") == "true":
            headers["Access-Control-Allow-Private-Network"] = "true"
        self._send(204, b"", "text/plain; charset=utf-8", headers)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/api/status":
            try:
                self.send_json(200, build_status())
            except Exception as exc:
                self.send_json(500, {
                    "ok": False,
                    "code": "status-failed",
                    "message": f"读取客户端状态失败：{type(exc).__name__}",
                })
            return

        if path == "/api/health":
            self.send_json(200, {"ok": True, "service": "lcu-sync-bridge"})
            return

        if path in ("/", "/index.html", "/lol_stats.html"):
            try:
                body = SITE.read_bytes()
            except OSError:
                self.send_json(500, {"ok": False, "code": "site-missing", "message": "找不到网站文件"})
                return
            self._send(200, body, "text/html; charset=utf-8")
            return

        self.send_json(404, {"ok": False, "code": "not-found", "message": "接口不存在"})

    def do_POST(self):
        path = urlsplit(self.path).path
        if path != "/api/sync":
            self.send_json(404, {"ok": False, "code": "not-found", "message": "接口不存在"})
            return
        if self.headers.get("X-LCU-Sync") != "1":
            self.send_json(403, {"ok": False, "code": "missing-header", "message": "缺少同步请求头"})
            return

        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length > 0:
            self.rfile.read(min(length, 1024 * 1024))

        if not SYNC_LOCK.acquire(blocking=False):
            self.send_json(409, {"ok": False, "code": "busy", "message": "已有同步任务正在进行，请稍后"})
            return
        try:
            self._run_sync()
        finally:
            SYNC_LOCK.release()

    def _run_sync(self):
        if not lcu_sync.client_process_running():
            self.send_json(503, {
                "ok": False,
                "code": "client-not-running",
                "message": lcu_sync.CLIENT_NOT_RUNNING_MESSAGE,
            })
            return
        try:
            result = lcu_sync.collect_games(use_rofl=True, include_positions=False, logger=None)
        except Exception as exc:
            self.send_json(500, {
                "ok": False,
                "code": "sync-failed",
                "message": f"同步失败：{type(exc).__name__}",
            })
            return

        if not result["ok"]:
            status = 503 if result["code"] in (
                "install-not-found", "auth-failed", "summoner-failed", "no-puuid",
            ) else 502
            self.send_json(status, {
                "ok": False,
                "code": result["code"],
                "message": result["message"],
            })
            return

        lcu_sync.safe_print(f"[sync] {result['message']}（账号 {result['summoner']}）")
        self.send_json(200, {"ok": True, **result["payload"]})


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="本机 LCU 同步桥：只监听 127.0.0.1，供网站自动同步使用。",
    )
    parser.add_argument(
        "--port", type=int,
        default=int(os.environ.get("LCU_SYNC_PORT", DEFAULT_PORT)),
        help=f"监听端口（默认 {DEFAULT_PORT}）",
    )
    parser.add_argument("--open", action="store_true", help="启动后打开浏览器")
    args = parser.parse_args(argv)

    if not SITE.is_file():
        print(f"找不到网站文件：{SITE}")
        return 1

    try:
        httpd = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    except OSError as exc:
        print(f"无法监听 127.0.0.1:{args.port}：{exc}")
        print("端口可能已被占用，可用 --port 指定其他端口。")
        return 1

    httpd.daemon_threads = True
    port = httpd.server_address[1]
    url = f"http://127.0.0.1:{port}/"
    print(f"LCU 同步服务已启动：{url}")
    print(f"网站也可直接打开 website/lol_stats.html；自动同步默认连接 127.0.0.1:{DEFAULT_PORT}。")
    print("只监听本机；不会输出 LCU token。按 Ctrl+C 停止。")
    if args.open:
        webbrowser.open(url)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
