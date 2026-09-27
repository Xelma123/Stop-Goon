import pytest

from stopgoon.blocklist import is_blocked, normalize
from vectors import DOMAINS, VECTORS


@pytest.mark.parametrize("host,expected", VECTORS)
def test_vectors(host, expected):
    assert is_blocked(host, DOMAINS) is expected


def test_normalize_idn():
    assert normalize("Bücher.Example.") == "xn--bcher-kva.example"
    assert is_blocked("www.bücher.example", DOMAINS)
