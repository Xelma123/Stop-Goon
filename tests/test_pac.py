import json
import shutil
import subprocess

import pytest

from stopgoon.blocklist import is_blocked
from stopgoon.pac import build_pac
from vectors import DOMAINS, VECTORS

NODE = shutil.which("node")


def test_pac_shape():
    pac = build_pac(DOMAINS, "127.0.0.1", 8899)
    assert 'var P = "PROXY 127.0.0.1:8899";' in pac
    assert '"reddit.com":1' in pac


@pytest.mark.skipif(NODE is None, reason="Node.js not installed; PAC not executed")
def test_pac_matches_python():
    pac = build_pac(DOMAINS, "127.0.0.1", 8899)
    hosts = [h for h, _ in VECTORS]
    script = (
        pac
        + "\nconsole.log(JSON.stringify("
        + json.dumps(hosts)
        + ".map(function (h) { return FindProxyForURL('https://' + h + '/', h); })));"
    )
    out = subprocess.run(
        [NODE, "-e", script], capture_output=True, text=True, check=True
    ).stdout
    results = json.loads(out)
    for (host, expected), result in zip(VECTORS, results):
        assert is_blocked(host, DOMAINS) is expected
        assert result == ("PROXY 127.0.0.1:8899" if expected else "DIRECT"), host
