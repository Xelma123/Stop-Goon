"""Attempt counter persisted in stats.json (PRD §9.4)."""

import json
import logging
import os
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

log = logging.getLogger("stopgoon")

DEDUP_SECONDS = 5.0


def _empty() -> dict:
    return {"total": 0, "days": {}, "lastAttemptUtc": None}


def _valid(data) -> bool:
    return (
        isinstance(data, dict)
        and type(data.get("total")) is int
        and data["total"] >= 0
        and isinstance(data.get("days"), dict)
        and all(isinstance(k, str) and type(v) is int for k, v in data["days"].items())
        and (data.get("lastAttemptUtc") is None or isinstance(data["lastAttemptUtc"], str))
    )


class Stats:
    def __init__(self, path: Path, clock=time.time):
        self.path = path
        self._clock = clock
        self._lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._recent: dict[str, float] = {}
        self.data = self._load()

    def _load(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return _empty()
        except (OSError, ValueError):
            data = None
        if _valid(data):
            return data
        log.warning("stats.json is corrupt; saved as stats.json.bak, counter reset")
        try:
            os.replace(self.path, self.path.with_name("stats.json.bak"))
        except OSError:
            log.exception("Cannot back up stats.json")
        return _empty()

    def record(self, host: str) -> bool:
        """Count one redirected attempt. Repeats for the same host within
        5 seconds of a counted attempt are ignored. Returns True if counted."""
        now = self._clock()
        with self._lock:
            last = self._recent.get(host)
            if last is not None and now - last < DEDUP_SECONDS:
                return False
            self._recent = {
                h: t for h, t in self._recent.items() if now - t < DEDUP_SECONDS
            }
            self._recent[host] = now
            day = datetime.fromtimestamp(now).date().isoformat()  # local day
            self.data["total"] += 1
            self.data["days"][day] = self.data["days"].get(day, 0) + 1
            self.data["lastAttemptUtc"] = datetime.fromtimestamp(now, UTC).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
        threading.Thread(target=self.save, name="stopgoon-stats", daemon=True).start()
        return True

    def save(self) -> None:
        """Atomically write the latest counts."""
        with self._write_lock:
            with self._lock:
                text = json.dumps(self.data, indent=2)
            tmp = self.path.with_name(self.path.name + ".tmp")
            try:
                tmp.write_text(text, encoding="utf-8")
                os.replace(tmp, self.path)
            except OSError:
                log.exception("Cannot write stats.json")

    def summary(self) -> tuple[int, int, datetime | None]:
        """(today, total, last attempt in local time)."""
        today = datetime.fromtimestamp(self._clock()).date().isoformat()
        with self._lock:
            last = self.data["lastAttemptUtc"]
            counts = self.data["days"].get(today, 0), self.data["total"]
        last_local = None
        if last:
            try:
                last_local = (
                    datetime.strptime(last, "%Y-%m-%dT%H:%M:%SZ")
                    .replace(tzinfo=UTC)
                    .astimezone()
                )
            except ValueError:
                pass
        return (*counts, last_local)
