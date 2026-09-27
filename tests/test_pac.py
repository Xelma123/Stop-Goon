import json
import random
import shutil
import string
import subprocess

import pytest

from stopgoon.blocklist import is_blocked
from stopgoon.pac import MAX_PAC_BYTES, build_pac, pac_hash, pac_version
from vectors import DOMAINS, VECTORS

NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="Node.js not installed; PAC not executed")


def run_js(source: str):
    out = subprocess.run([NODE], input=source, capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def test_pac_shape():
    pac = build_pac(DOMAINS, 8899).decode()
    assert 'var P = "PROXY 127.0.0.1:8899";' in pac
    assert f'"{pac_hash("reddit.com")}":1' in pac
    assert "reddit.com" not in pac


def test_pac_hash_known_values():
    # FNV-1a 32-bit reference values.
    assert pac_hash("") == _b36(0x811C9DC5)
    assert pac_hash("a") == _b36(0xE40C292C)
    assert pac_hash("foobar") == _b36(0xBF9CF968)


def _b36(n: int) -> str:
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    out = ""
    while True:
        n, r = divmod(n, 36)
        out = digits[r] + out
        if not n:
            return out


def test_version_changes_with_content():
    assert pac_version(build_pac({"a.com"})) != pac_version(build_pac({"b.com"}))
    assert pac_version(build_pac({"a.com"})) == pac_version(build_pac({"a.com"}))


def test_realistic_list_fits_under_limit():
    # ~76.800 unrelated domains (the porn-only list before collapsing).
    random.seed(3)
    chars = string.ascii_lowercase + string.digits + "-"
    domains = {
        "".join(random.choices(chars, k=random.randint(8, 18))) + random.choice([".com", ".net", ".xxx"])
        for _ in range(76_800)
    }
    assert len(build_pac(domains)) < MAX_PAC_BYTES


@needs_node
def test_js_hash_matches_python():
    random.seed(4)
    chars = string.ascii_lowercase + string.digits + "-._"
    names = ["", "a", "reddit.com", "xn--bcher-kva.example"] + [
        "".join(random.choices(chars, k=random.randint(1, 60))) for _ in range(3000)
    ]
    pac = build_pac(DOMAINS).decode()
    results = run_js(pac + f"\nconsole.log(JSON.stringify({json.dumps(names)}.map(H)));")
    assert results == [pac_hash(n) for n in names]


@needs_node
def test_pac_matches_python():
    pac = build_pac(DOMAINS, 8899).decode()
    hosts = [h for h, _ in VECTORS]
    results = run_js(
        pac
        + f"\nconsole.log(JSON.stringify({json.dumps(hosts)}"
        + ".map(function (h) { return FindProxyForURL('https://' + h + '/', h); })));"
    )
    for (host, expected), result in zip(VECTORS, results):
        assert is_blocked(host, DOMAINS) is expected
        assert result == ("PROXY 127.0.0.1:8899" if expected else "DIRECT"), host
