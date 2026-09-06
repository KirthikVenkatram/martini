"""Tests for the pure snapshot-building helpers in server/replay.py.

The thread-orchestration half of this module (run_replay,
start_replay) needs a live Grafana/Gemini stack to exercise
meaningfully and is covered by manual browser verification instead
(Task 11) -- these tests cover the parts that are pure functions of a
ShootingDay.
"""

from __future__ import annotations

from emitter.simulator import build_day
from server.replay import incident_url, scene_snapshots, shot_scene_numbers


def test_scene_snapshots_are_in_shooting_order_with_cast_names():
    day = build_day("nominal")

    snapshots = scene_snapshots(day)

    numbers = [s.number for s in snapshots]
    assert numbers[0] == "1"
    scene_1 = next(s for s in snapshots if s.number == "1")
    assert scene_1.cast_names == ["MARCUS", "ELENA"]
    assert scene_1.strip_color == "day-int"
    assert scene_1.page_eighths_display == "4/8"


def test_shot_scene_numbers_empty_before_any_setup_completes():
    day = build_day("nominal")

    assert shot_scene_numbers(day) == []


def test_shot_scene_numbers_reports_a_scene_once_all_its_setups_complete():
    day = build_day("nominal")
    for setup in day.setups:
        if setup.scene_number == "1":
            setup.actual_minutes = 20
            setup.takes = 2

    assert shot_scene_numbers(day) == ["1"]


def test_incident_url_links_the_dashboard_for_the_annotation_fallback():
    assert (
        incident_url("http://localhost:3000/d/martini-day-14", "annotation:42")
        == "http://localhost:3000/d/martini-day-14"
    )


def test_incident_url_links_the_incident_app_for_a_real_incident():
    # The incident-app link is built from agent.config.GRAFANA_URL (the
    # configured stack, "http://localhost:3000" under tests/conftest.py's
    # fake env), not from the dashboard_url argument -- that argument
    # only matters for the annotation fallback above.
    url = incident_url("http://localhost:3000/d/martini-day-14", "IID-1")
    assert url == "http://localhost:3000/a/grafana-incident-app/incidents/IID-1"


def test_incident_url_is_none_without_an_incident():
    assert incident_url("http://localhost:3000/d/martini-day-14", None) is None
