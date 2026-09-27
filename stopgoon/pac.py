"""PAC file generation (PRD §7.1, with the hashed table chosen in phase 1).

Chromium refuses PAC files over 1 MiB, so the PAC holds 32-bit FNV-1a hashes
of the (collapsed) blocked domains instead of the names. A hash collision only
sends an unrelated host to the proxy, whose exact check then passes it through
without opening TLS. The hash is written with shifts instead of Math.imul so
it runs on older PAC engines too.
"""

import hashlib
import json

# Stay clearly below Chromium's 1 MiB limit (pac_file_fetcher_impl.cc).
MAX_PAC_BYTES = 1_000_000

PAC_TEMPLATE = """var B = %s;
var P = "PROXY %s";

function H(s) {
  var h = 0x811c9dc5;
  for (var i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = (h + (h << 1) + (h << 4) + (h << 7) + (h << 8) + (h << 24)) >>> 0;
  }
  return h.toString(36);
}

function FindProxyForURL(url, host) {
  host = host.toLowerCase();
  if (host.charAt(host.length - 1) == ".") host = host.substring(0, host.length - 1);
  var h = host;
  while (true) {
    if (B.hasOwnProperty(H(h))) return P;
    var i = h.indexOf(".");
    if (i < 0) return "DIRECT";
    h = h.substring(i + 1);
    if (h.indexOf(".") < 0) return "DIRECT";
  }
}
"""

_B36 = "0123456789abcdefghijklmnopqrstuvwxyz"


def pac_hash(name: str) -> str:
    """32-bit FNV-1a of the ASCII name, base 36. Must match H() above."""
    h = 0x811C9DC5
    for b in name.encode("ascii"):
        h = ((h ^ b) * 0x01000193) & 0xFFFFFFFF
    out = ""
    while True:
        h, r = divmod(h, 36)
        out = _B36[r] + out
        if not h:
            return out


def build_pac(domains, proxy_port: int = 8899) -> bytes:
    table = json.dumps(
        {k: 1 for k in sorted({pac_hash(d) for d in domains})}, separators=(",", ":")
    )
    return (PAC_TEMPLATE % (table, f"127.0.0.1:{proxy_port}")).encode("ascii")


def pac_version(pac: bytes) -> str:
    return hashlib.sha256(pac).hexdigest()[:12]
