from types import SimpleNamespace

import pytest
from mitmproxy import connection, tls
from mitmproxy.options import Options
from mitmproxy.proxy.context import Context
from mitmproxy.test import tflow

from stopgoon.addon import REDIRECT_URL, StopGoon


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
def sg():
    return StopGoon(blocked=frozenset({"reddit.com"}))


def test_document_redirects(sg):
    f = make_flow("www.reddit.com", {"Sec-Fetch-Dest": "document"})
    sg.requestheaders(f)
    assert f.response.status_code == 302
    assert f.response.headers["Location"] == REDIRECT_URL
    assert f.response.headers["Cache-Control"] == "no-store"
    assert f.response.headers["Referrer-Policy"] == "no-referrer"


def test_accept_fallback_redirects(sg):
    f = make_flow("reddit.com", {"Accept": "text/html,application/xhtml+xml"})
    sg.requestheaders(f)
    assert f.response.status_code == 302


@pytest.mark.parametrize("dest", ["image", "iframe", "script", "empty", "video"])
def test_subresource_forbidden(sg, dest):
    f = make_flow("i.reddit.com", {"Sec-Fetch-Dest": dest})
    sg.requestheaders(f)
    assert f.response.status_code == 403
    assert f.response.content == b""


@pytest.mark.parametrize("purpose", ["prefetch", "prefetch;prerender", "prefetch;anonymous-client-ip"])
def test_prefetch_forbidden(sg, purpose):
    f = make_flow("reddit.com", {"Sec-Fetch-Dest": "document", "Sec-Purpose": purpose})
    sg.requestheaders(f)
    assert f.response.status_code == 403


def test_unblocked_untouched(sg):
    f = make_flow("notreddit.com", {"Sec-Fetch-Dest": "document"})
    sg.requestheaders(f)
    assert f.response is None


def test_decision_error_forbidden(sg, monkeypatch):
    def boom(flow):
        raise RuntimeError("boom")

    monkeypatch.setattr(sg, "_decide", boom)
    f = make_flow("reddit.com", {"Sec-Fetch-Dest": "document"})
    sg.requestheaders(f)
    assert f.response.status_code == 403


def clienthello(connect_host, sni):
    context = Context(connection.Client(peername=("127.0.0.1", 1), sockname=("127.0.0.1", 8899)), Options())
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
