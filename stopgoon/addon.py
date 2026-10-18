"""mitmproxy addon: TLS safety layer + block decision (PRD §7.3).

Phase 1 proof of concept: fixed blocklist, no counter, no config.
Run: mitmdump --listen-host 127.0.0.1 --listen-port 8899 -s stopgoon/addon.py
"""

import logging
import sys
from pathlib import Path

# `mitmdump -s` only puts this file's directory on sys.path.
_ROOT = str(Path(__file__).resolve().parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from mitmproxy import ctx, http, tls  # noqa: E402

from stopgoon.blocklist import is_blocked, normalize  # noqa: E402
from stopgoon.pac import build_pac  # noqa: E402
from stopgoon.server import PacServer  # noqa: E402

log = logging.getLogger("stopgoon")

REDIRECT_URL = "https://www.youtube.com/watch?v=jkpBEwzAxPo&t=0s"
PAC_PORT = 8898
BLOCKED = frozenset({"reddit.com"})


class StopGoon:
    def __init__(self, blocked=BLOCKED, redirect_url=REDIRECT_URL, pac_port=PAC_PORT):
        self.blocked = blocked
        self.redirect_url = redirect_url
        self.pac_port = pac_port
        self.pac = b""
        self.server = None

    def load(self, loader):
        loader.add_option(
            "stopgoon_pac_padding",
            int,
            0,
            "Phase 1 only: add N dummy .invalid entries to the PAC to measure "
            "browser load/eval time of a large PAC. Never proxied in practice.",
        )

    def running(self):
        # Never contact a blocked server just because the browser sent CONNECT.
        ctx.options.connection_strategy = "lazy"
        # Without this, non-HTTP data inside an intercepted (blocked) tunnel is
        # relayed as raw TCP, which opens a connection to the blocked server.
        ctx.options.rawtcp = False
        # mitmdump's flow dump prints full URLs; only hostnames may be logged.
        if "flow_detail" in ctx.options:
            ctx.options.flow_detail = 0
        padding = [
            f"p{i:06d}.sgpad.invalid"
            for i in range(ctx.options.stopgoon_pac_padding)
        ]
        self.pac = build_pac(
            [*self.blocked, *padding], "127.0.0.1", ctx.options.listen_port
        ).encode("ascii")
        log.info("PAC size: %d bytes", len(self.pac))
        try:
            self.server = PacServer(self.pac_port, lambda: self.pac, self.status_lines)
        except OSError as e:
            log.error("Cannot bind PAC server on 127.0.0.1:%d: %s", self.pac_port, e)
            return
        self.server.start()

    def done(self):
        if self.server:
            self.server.stop()
            self.server = None

    def status_lines(self) -> list[str]:
        return ["Stop Goon — Aktif", f"Engellenen domain: {len(self.blocked)}"]

    def _host_blocked(self, host) -> bool:
        try:
            return bool(host) and is_blocked(host, self.blocked)
        except Exception:
            # Unparseable host name: treat as not blocked here; the TLS layer
            # then leaves the connection encrypted.
            return False

    def tls_clienthello(self, data: tls.ClientHelloData):
        # Use the CONNECT target, not SNI (SNI may be an ECH outer name).
        address = data.context.server.address
        if not (address and self._host_blocked(address[0])):
            data.ignore_connection = True

    def requestheaders(self, flow: http.HTTPFlow):
        server_host = flow.server_conn.address[0] if flow.server_conn.address else None
        if not (self._host_blocked(flow.request.host) or self._host_blocked(server_host)):
            return
        try:
            self._decide(flow)
        except Exception:
            log.exception("Decision error")
            flow.response = _forbidden()

    def _decide(self, flow: http.HTTPFlow):
        req = flow.request
        host = normalize(req.host)
        purpose = req.headers.get("Sec-Purpose", "").lower()
        dest = req.headers.get("Sec-Fetch-Dest")
        if "prefetch" in purpose or "prerender" in purpose:
            flow.response = _forbidden()
            log.info("blocked %s (prefetch)", host)
        elif dest == "document" or (
            dest is None
            and req.method == "GET"
            and "text/html" in req.headers.get("Accept", "")
        ):
            flow.response = http.Response.make(
                302,
                b"",
                {
                    "Location": self.redirect_url,
                    "Cache-Control": "no-store",
                    "Referrer-Policy": "no-referrer",
                },
            )
            log.info("redirected %s", host)
        else:
            flow.response = _forbidden()
            log.info("blocked %s (subresource)", host)


def _forbidden() -> http.Response:
    return http.Response.make(403, b"", {"Cache-Control": "no-store"})


addons = [StopGoon()]
