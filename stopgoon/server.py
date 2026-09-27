"""PAC + status HTTP server on 127.0.0.1 (PRD §7.4)."""

import html
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable

log = logging.getLogger("stopgoon")

PAC_CONTENT_TYPE = "application/x-ns-proxy-autoconfig"


class _Handler(BaseHTTPRequestHandler):
    server_version = "StopGoon"
    sys_version = ""

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/stopgoon.pac":
            self._send(200, PAC_CONTENT_TYPE, self.server.get_pac())
        elif path == "/":
            self._send(200, "text/html; charset=utf-8", self._status_page())
        else:
            self._send(404, "text/plain; charset=utf-8", "Bulunamadı".encode())

    def _status_page(self) -> bytes:
        lines = [html.escape(x) for x in self.server.get_status()]
        body = "<br>\n".join(lines)
        return (
            '<!doctype html><html lang="tr"><head><meta charset="utf-8">'
            "<title>Stop Goon</title></head><body>"
            f"{body}</body></html>"
        ).encode("utf-8")

    def _send(self, code: int, ctype: str, body: bytes):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        # Request lines contain paths; only hostnames and times may be logged.
        pass


class PacServer:
    def __init__(
        self,
        port: int,
        get_pac: Callable[[], bytes],
        get_status: Callable[[], list[str]],
    ):
        self.httpd = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
        self.httpd.daemon_threads = True
        self.httpd.get_pac = get_pac
        self.httpd.get_status = get_status
        self.thread = threading.Thread(
            target=self.httpd.serve_forever, name="stopgoon-pac", daemon=True
        )

    def start(self):
        self.thread.start()

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()
