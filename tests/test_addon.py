import urllib.error
import urllib.request
from types import SimpleNamespace

import pytest
from mitmproxy import connection, tls
from mitmproxy.options import Options
from mitmproxy.proxy.context import Context
from mitmproxy.test import tflow

from stopgoon.addon import StopGoon
from stopgoon.config import DEFAULT_CONFIG, Store
from stopgoon.server import PacServer
from stopgoon.stats import Stats

REDIRECT_URL = DEFAULT_CONFIG["redirectUrl"]


def make_flow(host, headers=None, method="GET"):
    f = tflow.tflow()
    f.request.host = host
    f.request.method = method
    f.request.headers.clear()
    for k, v in (headers or {}).items():
        f.request.headers[k] = v
    f.server_conn.address = (host, 443)
    return f


@pytest.fixture
def sg(tmp_path):
    (tmp_path / "blocklist.txt").write_text("reddit.com\n", encoding="utf-8")
    addon = StopGoon()
    addon.store = Store(tmp_path)
    addon.stats = Stats(tmp_path / "stats.json")
    return addon


def test_document_redirects_and_counts(sg):
    f = make_flow("www.reddit.com", {"Sec-Fetch-Dest": "document"})
    sg.requestheaders(f)
    assert f.response.status_code == 302
    assert f.response.headers["Location"] == REDIRECT_URL
    assert f.response.headers["Cache-Control"] == "no-store"
    assert f.response.headers["Referrer-Policy"] == "no-referrer"
    assert sg.stats.data["total"] == 1


def test_accept_fallback_redirects(sg):
    f = make_flow("reddit.com", {"Accept": "text/html,application/xhtml+xml"})
    sg.requestheaders(f)
    assert f.response.status_code == 302


def test_post_without_fetch_metadata_is_forbidden(sg):
    f = make_flow("reddit.com", {"Accept": "text/html"}, method="POST")
    sg.requestheaders(f)
    assert f.response.status_code == 403


@pytest.mark.parametrize("dest", ["image", "iframe", "script", "empty", "video"])
def test_subresource_forbidden_not_counted(sg, dest):
    f = make_flow("i.reddit.com", {"Sec-Fetch-Dest": dest})
    sg.requestheaders(f)
    assert f.response.status_code == 403
    assert f.response.content == b""
    assert f.response.headers["Cache-Control"] == "no-store"
    assert sg.stats.data["total"] == 0


@pytest.mark.parametrize("purpose", ["prefetch", "prefetch;prerender", "prefetch;anonymous-client-ip"])
def test_prefetch_forbidden_not_counted(sg, purpose):
    f = make_flow("reddit.com", {"Sec-Fetch-Dest": "document", "Sec-Purpose": purpose})
    sg.requestheaders(f)
    assert f.response.status_code == 403
    assert sg.stats.data["total"] == 0


def test_unblocked_untouched(sg):
    f = make_flow("notreddit.com", {"Sec-Fetch-Dest": "document"})
    sg.requestheaders(f)
    assert f.response is None


def test_blocked_tunnel_with_other_host_header_is_blocked(sg):
    f = make_flow("example.org", {"Sec-Fetch-Dest": "document"})
    f.server_conn.address = ("www.reddit.com", 443)
    sg.requestheaders(f)
    assert f.response.status_code == 302


def test_decision_error_forbidden(sg, monkeypatch):
    def boom(flow):
        raise RuntimeError("boom")

    monkeypatch.setattr(sg, "_decide", boom)
    f = make_flow("reddit.com", {"Sec-Fetch-Dest": "document"})
    sg.requestheaders(f)
    assert f.response.status_code == 403


def test_stats_error_keeps_redirect(sg, monkeypatch):
    def boom(host):
        raise RuntimeError("boom")

    monkeypatch.setattr(sg.stats, "record", boom)
    f = make_flow("reddit.com", {"Sec-Fetch-Dest": "document"})
    sg.requestheaders(f)
    assert f.response.status_code == 302


def clienthello(connect_host, sni):
    context = Context(
        connection.Client(peername=("127.0.0.1", 1), sockname=("127.0.0.1", 8899)), Options()
    )
    context.server.address = (connect_host, 443) if connect_host else None
    return tls.ClientHelloData(context, SimpleNamespace(sni=sni))


def test_tls_blocked_connect_is_intercepted(sg):
    data = clienthello("www.reddit.com", "www.reddit.com")
    sg.tls_clienthello(data)
    assert data.ignore_connection is False


def test_tls_unblocked_connect_passes_through(sg):
    data = clienthello("bank.example", "bank.example")
    sg.tls_clienthello(data)
    assert data.ignore_connection is True


def test_tls_uses_connect_target_not_sni(sg):
    # ECH-style outer SNI naming a blocked host must not trigger interception.
    data = clienthello("bank.example", "reddit.com")
    sg.tls_clienthello(data)
    assert data.ignore_connection is True


def test_tls_no_address_passes_through(sg):
    data = clienthello(None, "reddit.com")
    sg.tls_clienthello(data)
    assert data.ignore_connection is True


def test_server_routes(sg, tmp_path):
    server = PacServer(0, sg)
    server.start()
    root = f"http://127.0.0.1:{server.port}"
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(root + "/stopgoon.pac?v=abc") as r:
            assert r.headers["Content-Type"] == "application/x-ns-proxy-autoconfig"
            assert r.headers["Cache-Control"] == "no-cache"
            assert r.read() == sg.store.state.pac
        with opener.open(root + "/") as r:
            page = r.read().decode("utf-8")
            assert "Stop Goon — Aktif" in page
            assert "Engellenen domain: 1" in page
            assert "Listeyi yeniden yükle" in page
        (tmp_path / "blocklist.txt").write_text("reddit.com\nnew.example\n", encoding="utf-8")
        with opener.open(urllib.request.Request(root + "/reload", data=b"", method="POST")) as r:
            assert r.url == root + "/"
            assert "Engellenen domain: 2" in r.read().decode("utf-8")
        with pytest.raises(urllib.error.HTTPError) as e:
            opener.open(root + "/other")
        assert e.value.code == 404
    finally:
        server.stop()
