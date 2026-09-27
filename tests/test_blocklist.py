import random
import string
import time

import pytest

from stopgoon.blocklist import collapse, is_blocked, load_files, normalize, parse_lines
from vectors import DOMAINS, VECTORS


@pytest.mark.parametrize("host,expected", VECTORS)
def test_vectors(host, expected):
    assert is_blocked(host, DOMAINS) is expected


def test_normalize_idn():
    assert normalize("Bücher.Example.") == "xn--bcher-kva.example"
    assert is_blocked("www.bücher.example", DOMAINS)


def test_parse_formats():
    lines = [
        "# comment",
        "",
        "   ",
        "plain.com",
        "Upper.COM.",
        "0.0.0.0 hosts-zero.com",
        "127.0.0.1 hosts-loop.com  # trailing comment",
        "tail.com # comment",
        "*.wild.com",
        ".dot.com",
        "bücher.de",
        "127.0.0.1 localhost",
        "::1 localhost",
        "255.255.255.255 broadcasthost",
        "0.0.0.0 0.0.0.0",
        "fe80::1%lo0 localhost",
    ]
    domains, invalid = parse_lines(lines)
    assert domains == {
        "plain.com",
        "upper.com",
        "hosts-zero.com",
        "hosts-loop.com",
        "tail.com",
        "wild.com",
        "dot.com",
        "xn--bcher-kva.de",
    }
    assert invalid == []


def test_invalid_lines_reported_with_numbers():
    lines = ["ok.com", "two words", "nodot", "bad!char.com", "0.0.0.0", "a..b.com", "x" * 64 + ".com"]
    domains, invalid = parse_lines(lines)
    assert domains == {"ok.com"}
    assert invalid == [2, 3, 4, 5, 6, 7]


def test_load_files_missing_and_invalid(tmp_path):
    (tmp_path / "a.txt").write_text("a.com\nbad line here\n", encoding="utf-8")
    domains, warnings = load_files([tmp_path / "a.txt", tmp_path / "missing.txt"])
    assert domains == {"a.com"}
    assert "a.txt: 1 geçersiz satır atlandı" in warnings
    assert "Liste dosyası bulunamadı: missing.txt" in warnings


def test_load_files_utf8_bom(tmp_path):
    (tmp_path / "a.txt").write_bytes("﻿a.com\n".encode("utf-8"))
    assert load_files([tmp_path / "a.txt"])[0] == {"a.com"}


def test_collapse_keeps_matches():
    domains = {"site.com", "www.site.com", "a.b.site.com", "other.org", "x.y.other.net", "y.other.net"}
    collapsed = collapse(domains)
    assert collapsed == {"site.com", "other.org", "y.other.net"}
    random.seed(0)
    hosts = [
        ".".join(random.choice(["a", "b", "www", "site", "other", "y", "x"]) for _ in range(random.randint(1, 4)))
        + random.choice([".com", ".org", ".net"])
        for _ in range(5000)
    ] + sorted(domains)
    for h in hosts:
        assert is_blocked(h, domains) == is_blocked(h, collapsed), h


def test_load_100k_lines_under_one_second(tmp_path):
    random.seed(1)
    names = {
        "".join(random.choices(string.ascii_lowercase + string.digits, k=random.randint(5, 20))) + ".com"
        for _ in range(100_000)
    }
    path = tmp_path / "big.txt"
    path.write_text("".join(f"0.0.0.0 {n}\n" for n in names), encoding="utf-8")
    start = time.perf_counter()
    domains, _ = load_files([path])
    elapsed = time.perf_counter() - start
    assert len(domains) == len(names)
    assert elapsed < 1.0, elapsed
