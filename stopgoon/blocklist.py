"""Domain normalization and suffix matching (PRD §8.3).

Phase 1 only needs the matcher; file parsing arrives in phase 2.
"""


def normalize(host: str) -> str:
    """Lowercase, strip one trailing dot, convert IDN to punycode."""
    host = host.strip().lower()
    if host.endswith("."):
        host = host[:-1]
    if not host.isascii():
        host = host.encode("idna").decode("ascii")
    return host


def is_blocked(host: str, domains: set[str] | frozenset[str]) -> bool:
    """Label-by-label suffix walk; single-label suffixes are never checked.

    Must stay identical to FindProxyForURL in pac.py.
    """
    h = normalize(host)
    while True:
        if h in domains:
            return True
        i = h.find(".")
        if i < 0:
            return False
        h = h[i + 1 :]
        if "." not in h:
            return False
