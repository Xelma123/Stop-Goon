import json

import pytest

from stopgoon import config as config_mod
from stopgoon.config import DEFAULT_CONFIG, LoadError, Store, read_config


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@pytest.fixture
def base(tmp_path):
    (tmp_path / "blocklist.txt").write_text("reddit.com\n", encoding="utf-8")
    (tmp_path / "lists").mkdir()
    (tmp_path / "lists" / "porn-only.txt").write_text("0.0.0.0 porn.example\n", encoding="utf-8")
    return tmp_path


def write_config(base, **overrides):
    (base / "config.json").write_text(json.dumps({**DEFAULT_CONFIG, **overrides}), encoding="utf-8")


def test_missing_config_created_with_defaults(base):
    assert read_config(base / "config.json") == DEFAULT_CONFIG
    assert json.loads((base / "config.json").read_text(encoding="utf-8")) == DEFAULT_CONFIG


@pytest.mark.parametrize(
    "overrides",
    [
        {"redirectUrl": "http://www.youtube.com/watch?v=x"},
        {"redirectUrl": "https://"},
        {"redirectUrl": 5},
        {"blocklistFiles": "blocklist.txt"},
        {"proxyPort": "8899"},
        {"proxyPort": 70000},
        {"pacPort": True},
        {"pacPort": 8899},
    ],
)
def test_invalid_config_rejected(base, overrides):
    write_config(base, **overrides)
    with pytest.raises(LoadError):
        read_config(base / "config.json")


def test_store_loads_lists(base):
    store = Store(base)
    assert store.state.domain_count == 2
    assert store.state.domains == {"reddit.com", "porn.example"}
    assert store.errors == ()
    assert store.state.warnings == ()


def test_missing_list_file_skipped_with_warning(base):
    (base / "lists" / "porn-only.txt").unlink()
    store = Store(base)
    assert store.state.domains == {"reddit.com"}
    assert "Liste dosyası bulunamadı: porn-only.txt" in store.state.warnings


def test_broken_json_at_startup_uses_defaults(base):
    (base / "config.json").write_text("{broken", encoding="utf-8")
    store = Store(base)
    assert store.state.config == DEFAULT_CONFIG
    assert "reddit.com" in store.state.domains
    assert any("bozuk" in e for e in store.errors)


def test_broken_json_keeps_last_valid_config_and_blocks(base):
    write_config(base, redirectUrl="https://example.org/a")
    store = Store(base)
    (base / "config.json").write_text("{broken", encoding="utf-8")
    store.reload()
    assert store.state.config["redirectUrl"] == "https://example.org/a"
    assert "reddit.com" in store.state.domains
    assert any("bozuk" in e for e in store.errors)


def test_http_redirect_rejected_keeps_previous(base):
    store = Store(base)
    write_config(base, redirectUrl="http://example.org/")
    store.reload()
    assert store.state.config["redirectUrl"] == DEFAULT_CONFIG["redirectUrl"]
    assert any("https" in e for e in store.errors)


def test_redirect_loop_rejected_keeps_previous(base):
    store = Store(base)
    before = store.state
    (base / "blocklist.txt").write_text("reddit.com\nyoutube.com\n", encoding="utf-8")
    store.reload()
    assert store.state is before
    assert any("döngü" in e for e in store.errors)


def test_redirect_loop_at_startup_is_warning(base):
    (base / "blocklist.txt").write_text("youtube.com\n", encoding="utf-8")
    store = Store(base)
    assert "youtube.com" in store.state.domains
    assert any("döngü" in w for w in store.state.warnings)


def test_oversized_pac_rejected_keeps_previous(base, monkeypatch):
    store = Store(base)
    before = store.state
    monkeypatch.setattr(config_mod, "MAX_PAC_BYTES", len(before.pac) + 10)
    (base / "blocklist.txt").write_text("reddit.com\n" + "".join(f"d{i}.com\n" for i in range(50)), encoding="utf-8")
    store.reload()
    assert store.state is before
    assert any("çok büyük" in e for e in store.errors)


def test_lazy_reload_waits_two_seconds(base):
    clock = Clock()
    changes = []
    store = Store(base, on_change=changes.append, clock=clock)
    assert len(changes) == 1  # initial load
    (base / "blocklist.txt").write_text("reddit.com\nnew.example\n", encoding="utf-8")
    clock.now += 1.0
    store.maybe_reload()
    assert "new.example" not in store.state.domains
    clock.now += 1.5
    store.maybe_reload()
    assert "new.example" in store.state.domains
    assert len(changes) == 2
    assert changes[-1] is store.state


def test_unchanged_files_do_not_reload(base):
    clock = Clock()
    store = Store(base, clock=clock)
    before = store.state
    clock.now += 10
    store.maybe_reload()
    assert store.state is before


def test_rejected_change_is_not_retried_until_next_change(base, monkeypatch):
    clock = Clock()
    store = Store(base, clock=clock)
    (base / "blocklist.txt").write_text("reddit.com\nyoutube.com\n", encoding="utf-8")
    clock.now += 3
    store.maybe_reload()
    calls = []
    monkeypatch.setattr(store, "reload", lambda: calls.append(1))
    clock.now += 3
    store.maybe_reload()
    assert calls == []


def test_config_change_to_new_list_file_is_watched(base):
    clock = Clock()
    store = Store(base, clock=clock)
    (base / "extra.txt").write_text("extra.example\n", encoding="utf-8")
    write_config(base, blocklistFiles=["blocklist.txt", "extra.txt"])
    clock.now += 3
    store.maybe_reload()
    assert "extra.example" in store.state.domains
    (base / "extra.txt").write_text("extra.example\nmore.example\n", encoding="utf-8")
    clock.now += 3
    store.maybe_reload()
    assert "more.example" in store.state.domains
