"""mitmproxy addon: TLS safety layer + block decision (PRD §7.3).

Run: mitmdump --listen-host 127.0.0.1 --listen-port 8899 -s stopgoon/addon.py
"""

import logging
import sys
from datetime import datetime
from pathlib import Path

# `mitmdump -s` only puts this file's directory on sys.path.
_ROOT = str(Path(__file__).resolve().parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from mitmproxy import ctx, http, tls  # noqa: E402

from stopgoon import paths  # noqa: E402
from stopgoon.blocklist import is_blocked, normalize  # noqa: E402
from stopgoon.config import State, Store  # noqa: E402
from stopgoon.server import PacServer  # noqa: E402
from stopgoon.stats import Stats  # noqa: E402

log = logging.getLogger("stopgoon")


def _num(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def _when(dt: datetime) -> str:
    return dt.strftime("%d.%m.%Y %H:%M")


class StopGoon:
    def __init__(self):
        self.store: Store | None = None
        self.stats: Stats | None = None
        self.server: PacServer | None = None
        self.notices: list[str] = []

    def load(self, loader):
        base = paths.base_dir()
        base.mkdir(parents=True, exist_ok=True)
        # Loaded here, before the proxy accepts connections.
        self.store = Store(base, on_change=self._sync_pac_url)
        self.stats = Stats(paths.stats_file(base))

    def running(self):
        # Never contact a blocked server just because the browser sent CONNECT.
        ctx.options.connection_strategy = "lazy"
        # Without this, non-HTTP data inside an intercepted (blocked) tunnel is
        # relayed as raw TCP, which opens a connection to the blocked server.
        ctx.options.rawtcp = False
        # mitmdump's flow dump prints full URLs; only hostnames may be logged.
        if "flow_detail" in ctx.options:
            ctx.options.flow_detail = 0

        config = self.store.state.config
        if ctx.options.listen_port != config["proxyPort"]:
            log.error(
                "Proxy listens on %d but config.json proxyPort is %d",
                ctx.options.listen_port,
                config["proxyPort"],
            )
            self.notices.append(
                f"Proxy {ctx.options.listen_port} portunda çalışıyor ama "
                f"config.json proxyPort {config['proxyPort']}; engel çalışmaz"
            )
        try:
            self.server = PacServer(config["pacPort"], self)
        except OSError as e:
            log.error("Cannot bind PAC server on 127.0.0.1:%d: %s", config["pacPort"], e)
            ctx.master.shutdown()
            return
        self.server.start()

    def done(self):
        if self.server:
            self.server.stop()
            self.server = None

    # --- PAC server callbacks (run on server threads) ---

    def pac(self) -> bytes:
        self.store.maybe_reload()
        return self.store.state.pac

    def reload(self) -> None:
        self.store.reload()

    def status(self) -> tuple[list[str], list[str]]:
        self.store.maybe_reload()
        state = self.store.state
        today, total, last = self.stats.summary()
        lines = [
            "Stop Goon — Aktif",
            f"Engellenen domain: {_num(state.domain_count)}",
            f"Bugün: {_num(today)} deneme · Toplam: {_num(total)}",
            f"Son deneme: {_when(last) if last else '—'}",
            f"Liste güncellendi: {_when(datetime.fromtimestamp(state.loaded_at))}",
        ]
        warnings = [*self.notices, *self.store.errors, *state.warnings]
        if sys.platform == "win32":
            from stopgoon import winsys

            try:
                if not winsys.is_ours(winsys.get_autoconfig_url()):
                    warnings.append(
                        "Windows proxy ayarında (AutoConfigURL) Stop Goon yok; "
                        "tarayıcılar engeli kullanmıyor"
                    )
            except OSError:
                log.exception("Cannot read AutoConfigURL")
        return lines, warnings

    def _sync_pac_url(self, state: State) -> None:
        """Point AutoConfigURL at the new PAC version so browsers re-fetch it.
        Only an AutoConfigURL that already belongs to Stop Goon is changed."""
        if sys.platform != "win32":
            return
        from stopgoon import winsys

        port = self.server.port if self.server else state.config["pacPort"]
        url = winsys.pac_url(port, state.version)
        try:
            current = winsys.get_autoconfig_url()
            if current == url:
                return
            if not winsys.is_ours(current):
                log.warning("AutoConfigURL is not set to Stop Goon; leaving it unchanged")
                return
            winsys.set_autoconfig_url(url)
            log.info("AutoConfigURL updated to PAC version %s", state.version)
        except OSError:
            log.exception("Cannot update AutoConfigURL")

    # --- proxy hooks ---

    def _host_blocked(self, host) -> bool:
        try:
            return bool(host) and is_blocked(host, self.store.state.domains)
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
        self.store.maybe_reload(background=True)
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
                    "Location": self.store.state.config["redirectUrl"],
                    "Cache-Control": "no-store",
                    "Referrer-Policy": "no-referrer",
                },
            )
            log.info("redirected %s", host)
            try:
                self.stats.record(host)
            except Exception:
                log.exception("Cannot record attempt")
        else:
            flow.response = _forbidden()
            log.info("blocked %s (subresource)", host)


def _forbidden() -> http.Response:
    return http.Response.make(403, b"", {"Cache-Control": "no-store"})


addons = [StopGoon()]
