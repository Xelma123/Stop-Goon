"""Blocklist parsing, normalization and suffix matching (PRD §8)."""

import ipaddress
import logging
import re
from pathlib import Path

log = logging.getLogger("stopgoon")

SPECIAL_NAMES = frozenset(
    {"localhost", "localhost.localdomain", "local", "broadcasthost", "0.0.0.0"}
)
_DOMAIN_RE = re.compile(r"^(?=.{1,253}$)([a-z0-9_-]{1,63}\.)+[a-z0-9_-]{1,63}$")
_MAX_LOGGED_INVALID = 20


def normalize(host: str) -> str:
    """Lowercase, strip one trailing dot, convert IDN to punycode."""
    host = host.strip().lower()
    if host.endswith("."):
        host = host[:-1]
    if not host.isascii():
        host = host.encode("idna").decode("ascii")
    return host


def _is_ip(token: str) -> bool:
    try:
        ipaddress.ip_address(token)
    except ValueError:
        return False
    return True


def parse_line(line: str) -> str | None:
    """Return the normalized domain on a line, None to skip it.

    Raises ValueError for an invalid line.
    """
    line = line.split("#", 1)[0]
    tokens = line.split()
    if not tokens:
        return None
    if _is_ip(tokens[0]):
        # hosts format: "0.0.0.0 example.com"
        if len(tokens) != 2:
            raise ValueError("bad hosts line")
        name = tokens[1]
    elif len(tokens) == 1:
        name = tokens[0]
    else:
        raise ValueError("unexpected tokens")
    if name.lower() in SPECIAL_NAMES:
        return None
    if name.startswith("*."):
        name = name[2:]
    elif name.startswith("."):
        name = name[1:]
    try:
        name = normalize(name)
    except UnicodeError:
        raise ValueError("bad IDN") from None
    if not _DOMAIN_RE.match(name):
        raise ValueError("not a domain")
    return name


def parse_lines(lines, source: str = "") -> tuple[set[str], list[int]]:
    """Return (domains, invalid line numbers)."""
    domains: set[str] = set()
    invalid: list[int] = []
    for number, line in enumerate(lines, 1):
        try:
            domain = parse_line(line)
        except ValueError:
            invalid.append(number)
            continue
        if domain:
            domains.add(domain)
    for number in invalid[:_MAX_LOGGED_INVALID]:
        log.warning("%s: invalid line %d skipped", source, number)
    if len(invalid) > _MAX_LOGGED_INVALID:
        log.warning(
            "%s: %d more invalid lines skipped", source, len(invalid) - _MAX_LOGGED_INVALID
        )
    return domains, invalid


def load_files(paths: list[Path]) -> tuple[set[str], list[str]]:
    """Load and merge blocklist files. Returns (domains, user-facing warnings)."""
    domains: set[str] = set()
    warnings: list[str] = []
    for path in paths:
        try:
            with open(path, encoding="utf-8-sig", errors="replace") as f:
                found, invalid = parse_lines(f, path.name)
        except FileNotFoundError:
            log.warning("Blocklist file not found: %s", path.name)
            warnings.append(f"Liste dosyası bulunamadı: {path.name}")
            continue
        except OSError as e:
            log.warning("Cannot read blocklist file %s: %s", path.name, e.strerror)
            warnings.append(f"Liste dosyası okunamadı: {path.name}")
            continue
        if invalid:
            warnings.append(f"{path.name}: {len(invalid)} geçersiz satır atlandı")
        domains |= found
    return domains, warnings


def _suffixes(host: str):
    """Yield host, then each parent suffix that has at least two labels."""
    h = host
    while True:
        yield h
        i = h.find(".")
        if i < 0:
            return
        h = h[i + 1 :]
        if "." not in h:
            return


def is_blocked(host: str, domains: set[str] | frozenset[str]) -> bool:
    """Label-by-label suffix walk; single-label suffixes are never checked.

    Must stay identical to FindProxyForURL in pac.py.
    """
    return any(s in domains for s in _suffixes(normalize(host)))


def collapse(domains: set[str]) -> frozenset[str]:
    """Drop entries already covered by a listed parent domain.

    Matching results are unchanged; the PAC gets smaller.
    """
    return frozenset(
        d
        for d in domains
        if not any(p in domains for p in list(_suffixes(d))[1:])
    )
