import json
from datetime import datetime

from stopgoon.stats import Stats


class Clock:
    def __init__(self, dt):
        self.now = dt.timestamp()

    def __call__(self):
        return self.now


def test_dedup_within_five_seconds(tmp_path):
    clock = Clock(datetime(2026, 9, 26, 22, 0, 0))
    stats = Stats(tmp_path / "stats.json", clock=clock)
    assert stats.record("reddit.com")
    clock.now += 4.9
    assert not stats.record("reddit.com")
    assert stats.record("other.example")  # different domain counts
    clock.now += 0.2
    assert stats.record("reddit.com")
    assert stats.data["total"] == 3


def test_day_change_uses_local_date(tmp_path):
    clock = Clock(datetime(2026, 9, 26, 23, 59, 58))
    stats = Stats(tmp_path / "stats.json", clock=clock)
    stats.record("reddit.com")
    clock.now += 10
    stats.record("reddit.com")
    assert stats.data["days"] == {"2026-09-26": 1, "2026-09-27": 1}
    today, total, last = stats.summary()
    assert (today, total) == (1, 2)
    assert last.astimezone().replace(tzinfo=None) == datetime(2026, 9, 27, 0, 0, 8)


def test_save_is_readable_and_reloads(tmp_path):
    path = tmp_path / "stats.json"
    clock = Clock(datetime(2026, 9, 26, 22, 12, 44))
    stats = Stats(path, clock=clock)
    stats.record("reddit.com")
    stats.save()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["total"] == 1
    assert data["days"] == {"2026-09-26": 1}
    assert data["lastAttemptUtc"].endswith("Z")
    assert not (tmp_path / "stats.json.tmp").exists()
    assert Stats(path, clock=clock).data == data


def test_corrupt_file_backed_up_and_reset(tmp_path):
    path = tmp_path / "stats.json"
    path.write_text("{not json", encoding="utf-8")
    stats = Stats(path)
    assert stats.data["total"] == 0
    assert (tmp_path / "stats.json.bak").read_text(encoding="utf-8") == "{not json"
    assert not path.exists()


def test_wrong_shape_backed_up(tmp_path):
    path = tmp_path / "stats.json"
    path.write_text(json.dumps({"total": "many"}), encoding="utf-8")
    assert Stats(path).data["total"] == 0
    assert (tmp_path / "stats.json.bak").exists()
