"""PAC + status HTTP server on 127.0.0.1 (PRD §7.4, §7.5)."""

import html
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

log = logging.getLogger("stopgoon")

PAC_CONTENT_TYPE = "application/x-ns-proxy-autoconfig"


class _Handler(BaseHTTPRequestHandler):
    server_version = "StopGoon"
    sys_version = ""

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/stopgoon.pac":
            self._send(200, PAC_CONTENT_TYPE, self.server.app.pac())
        elif path == "/":
            self._send(200, "text/html; charset=utf-8", self._status_page())
        else:
            self._not_found()

    def do_POST(self):
        if self.path == "/reload":
            self.server.app.reload()
            self.send_response(303)
            self.send_header("Location", "/")
            self.send_header("Content-Length", "0")
            self.end_headers()
        else:
            self._not_found()

    def _not_found(self):
        self._send(404, "text/plain; charset=utf-8", "Bulunamadı".encode())

    def _status_page(self) -> bytes:
        lines, warnings = self.server.app.status()
        body = "".join(f"<p>{html.escape(x)}</p>" for x in lines)
        if warnings:
            body += "<h2>Uyarılar</h2><ul>"
            body += "".join(f"<li>{html.escape(x)}</li>" for x in warnings)
            body += "</ul>"
        body += (
            '<form method="post" action="/reload">'
            '<button type="submit">Listeyi yeniden yükle</button></form>'
        )
        return (
            '<!doctype html><html lang="tr"><head><meta charset="utf-8">'
            "<title>Stop Goon</title>"
            "<style>body{font-family:sans-serif;margin:2em}"
            "p{margin:.3em 0}h2{font-size:1em;color:#b00}</style>"
            f"</head><body>{body}</body></html>"
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
    """app provides pac() -> bytes, status() -> (lines, warnings), reload()."""

    def __init__(self, port: int, app):
        self.httpd = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
        self.httpd.daemon_threads = True
        self.httpd.app = app
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(
            target=self.httpd.serve_forever, name="stopgoon-pac", daemon=True
        )

    def start(self):
        self.thread.start()

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()
