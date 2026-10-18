"""PAC file generation (PRD §7.1)."""

import json

PAC_TEMPLATE = """var B = %s;
var P = "PROXY %s";

function FindProxyForURL(url, host) {
  host = host.toLowerCase();
  if (host.charAt(host.length - 1) == ".") host = host.substring(0, host.length - 1);
  var h = host;
  while (true) {
    if (B.hasOwnProperty(h)) return P;
    var i = h.indexOf(".");
    if (i < 0) return "DIRECT";
    h = h.substring(i + 1);
    if (h.indexOf(".") < 0) return "DIRECT";
  }
}
"""


def build_pac(domains, proxy_host: str = "127.0.0.1", proxy_port: int = 8899) -> str:
    table = json.dumps(
        {d: 1 for d in sorted(domains)}, separators=(",", ":"), ensure_ascii=True
    )
    return PAC_TEMPLATE % (table, f"{proxy_host}:{proxy_port}")
