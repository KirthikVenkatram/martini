from __future__ import annotations

import json
from datetime import date

from agent.tools.quota import check_and_increment


def test_allows_calls_under_the_limit(tmp_path):
    path = tmp_path / "quota.json"
    today = date(2026, 9, 8)

    for _ in range(3):
        assert check_and_increment(path, limit=3, today=today) in (True, False)

    assert json.loads(path.read_text())["count"] == 3


def test_blocks_once_the_limit_is_reached(tmp_path):
    path = tmp_path / "quota.json"
    today = date(2026, 9, 8)

    for _ in range(3):
        assert check_and_increment(path, limit=3, today=today) is True

    assert check_and_increment(path, limit=3, today=today) is False
    assert json.loads(path.read_text())["count"] == 3


def test_resets_on_a_new_day(tmp_path):
    path = tmp_path / "quota.json"
    path.write_text(json.dumps({"date": "2026-09-07", "count": 20}))

    assert check_and_increment(path, limit=20, today=date(2026, 9, 8)) is True
    assert json.loads(path.read_text()) == {"date": "2026-09-08", "count": 1}


def test_tolerates_a_missing_or_corrupt_file(tmp_path):
    path = tmp_path / "quota.json"
    path.write_text("not json")

    assert check_and_increment(path, limit=20, today=date(2026, 9, 8)) is True
