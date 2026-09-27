"""File locations under %LocalAppData%\\StopGoon (PRD §6)."""

import os
from pathlib import Path


def base_dir() -> Path:
    return Path(os.environ["LOCALAPPDATA"]) / "StopGoon"


def config_file(base: Path) -> Path:
    return base / "config.json"


def stats_file(base: Path) -> Path:
    return base / "stats.json"
