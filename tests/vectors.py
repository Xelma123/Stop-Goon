"""Shared matcher vectors for the Python matcher and the generated PAC (§8.3)."""

DOMAINS = {"site.com", "reddit.com", "redd.it", "xn--bcher-kva.example"}

VECTORS = [
    ("site.com", True),
    ("www.site.com", True),
    ("a.b.site.com", True),
    ("SITE.COM", True),
    ("site.com.", True),
    ("notsite.com", False),
    ("site.com.evil.example", False),
    ("com", False),
    ("old.reddit.com", True),
    ("i.redd.it", True),
    ("reddit.co", False),
    ("xn--bcher-kva.example", True),
    ("www.xn--bcher-kva.example", True),
    ("youtube.com", False),
    ("localhost", False),
]
