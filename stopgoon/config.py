"""Config loading, validation, last valid state and lazy reload (PRD §7.5, §10)."""

import copy
import json
import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from stopgoon import blocklist
from stopgoon.pac import MAX_PAC_BYTES, build_pac, pac_version
from stopgoon.paths import config_file

log = logging.getLogger("stopgoon")

DEFAULT_CONFIG = {
    "redirectUrl": "https://www.youtube.com/watch?v=jkpBEwzAxPo&t=0s",
    "blocklistFiles": ["blocklist.txt", "lists/porn-only.txt"],
    "proxyPort": 8899,
    "pacPort": 8898,
}
CHECK_INTERVAL = 2.0


class LoadError(Exception):
    """A rejected config or list; the message is shown to the user."""


@dataclass(frozen=True)
class State:
    config: dict
    domains: frozenset[str]  # collapsed; same matches as the full list
    domain_count: int  # unique domains before collapsing
    pac: bytes
    version: str
    loaded_at: float
    warnings: tuple[str, ...]


def default_config() -> dict:
    return copy.deepcopy(DEFAULT_CONFIG)


def read_config(path: Path) -> dict:
    """Read and validate config.json, creating it with defaults if missing."""
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(DEFAULT_CONFIG, indent=2) + "\n", encoding="utf-8")
        log.info("Created default config.json")
        return default_config()
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except OSError:
        raise LoadError("config.json okunamadı") from None
    except ValueError:
        raise LoadError("config.json bozuk (geçersiz JSON)") from None
    if not isinstance(raw, dict):
        raise LoadError("config.json bir JSON nesnesi olmalı")
    config = {key: raw.get(key, value) for key, value in default_config().items()}
    _validate(config)
    return config


def _validate(config: dict) -> None:
    url = config["redirectUrl"]
    try:
        parts = urlsplit(url) if isinstance(url, str) else None
    except ValueError:
        parts = None
    if not parts or parts.scheme != "https" or not parts.hostname:
        raise LoadError("redirectUrl bir https adresi olmalı")
    files = config["blocklistFiles"]
    if not isinstance(files, list) or not all(isinstance(f, str) and f for f in files):
        raise LoadError("blocklistFiles bir dosya adı listesi olmalı")
    for key in ("proxyPort", "pacPort"):
        value = config[key]
        if type(value) is not int or not 1 <= value <= 65535:
            raise LoadError(f"{key} 1 ile 65535 arasında bir sayı olmalı")
    if config["proxyPort"] == config["pacPort"]:
        raise LoadError("proxyPort ve pacPort farklı olmalı")


def list_paths(base: Path, config: dict) -> list[Path]:
    return [base / name for name in config["blocklistFiles"]]


def build_state(base: Path, config: dict, strict: bool = True) -> State:
    """Load the lists for config. With strict, a redirect loop or an oversized
    PAC raises LoadError; otherwise they only become warnings."""
    domains, warnings = blocklist.load_files(list_paths(base, config))
    problems = []
    redirect_host = urlsplit(config["redirectUrl"]).hostname
    if blocklist.is_blocked(redirect_host, domains):
        problems.append(
            f"Yönlendirme adresinin sitesi ({redirect_host}) engel listesinde; döngü oluşur"
        )
    collapsed = blocklist.collapse(domains)
    pac = build_pac(collapsed, config["proxyPort"])
    if len(pac) > MAX_PAC_BYTES:
        problems.append(
            f"PAC dosyası çok büyük ({len(pac):,} bayt); "
            "Chrome, Edge ve Brave 1 MB'ı aşan PAC dosyasını kullanmaz".replace(",", ".")
        )
    if problems and strict:
        raise LoadError("; ".join(problems))
    return State(
        config=config,
        domains=collapsed,
        domain_count=len(domains),
        pac=pac,
        version=pac_version(pac),
        loaded_at=time.time(),
        warnings=tuple(warnings + problems),
    )


def _stat(path: Path):
    try:
        st = path.stat()
    except OSError:
        return (str(path), None, None)
    return (str(path), st.st_mtime_ns, st.st_size)


class Store:
    """Holds the current State and reloads it when files change."""

    def __init__(self, base: Path, on_change=None, clock=time.monotonic):
        self.base = base
        self.on_change = on_change
        self._clock = clock
        self._lock = threading.Lock()
        self._reloading = False
        self._last_check = clock()
        self._sig = None
        self._sig_config = None
        self.state: State | None = None
        self.errors: tuple[str, ...] = ()
        self.reload()

    def _signature(self, config: dict):
        return (
            _stat(config_file(self.base)),
            tuple(_stat(p) for p in list_paths(self.base, config)),
        )

    def reload(self) -> None:
        with self._lock:
            try:
                previous, state = self._reload_locked()
            finally:
                self._reloading = False
        if state is not previous:
            log.info(
                "Blocklist loaded: %d domains, PAC %d bytes",
                state.domain_count,
                len(state.pac),
            )
            if self.on_change and (previous is None or previous.version != state.version):
                self.on_change(state)

    def _reload_locked(self):
        previous = self.state
        errors = []
        path = config_file(self.base)
        config_stat = _stat(path)
        try:
            config = read_config(path)
        except LoadError as e:
            log.error("config.json rejected: %s", e)
            errors.append(f"{e}. Son geçerli ayarlar kullanılıyor.")
            config = previous.config if previous else default_config()
        if config_stat[1] is None:  # read_config just created it
            config_stat = _stat(path)
        files_stat = tuple(_stat(p) for p in list_paths(self.base, config))
        try:
            # At startup there is nothing to fall back to, so load anyway.
            state = build_state(self.base, config, strict=previous is not None)
        except LoadError as e:
            log.error("New list rejected: %s", e)
            errors.append(f"Yeni liste reddedildi: {e}. Önceki liste kullanılıyor.")
            state = previous
        # Record what was attempted so a rejected file is not retried
        # until it changes again.
        self._sig = (config_stat, files_stat)
        self._sig_config = config
        self.state = state
        self.errors = tuple(errors)
        return previous, state

    def maybe_reload(self, background: bool = False) -> None:
        """Reload if a watched file changed; checks at most every 2 seconds."""
        now = self._clock()
        if now - self._last_check < CHECK_INTERVAL:
            return
        self._last_check = now
        if self._signature(self._sig_config) == self._sig:
            return
        if not background:
            self.reload()
        elif not self._reloading:
            # Keep the proxy's event loop free while the lists are parsed.
            self._reloading = True
            threading.Thread(target=self.reload, name="stopgoon-reload", daemon=True).start()
