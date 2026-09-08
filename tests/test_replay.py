"""Tests for the pure snapshot-building helpers in server/replay.py.

The thread-orchestration half of this module (run_replay,
start_replay) needs a live Grafana/Gemini stack to exercise
meaningfully and is covered by manual browser verification instead
(Task 11) -- these tests cover the parts that are pure functions of a
ShootingDay.
"""

from __future__ import annotations

from emitter.simulator import build_day
from server.replay import _base_snapshot, _carry_forward_snapshot, incident_url, scene_snapshots, shot_scene_numbers
from server.state import STATE, DaySnapshot, PaceSnapshot, TimelineSnapshot

_TIMELINE = TimelineSnapshot(
    call_label="07:00",
    overtime_label="19:00",
    elapsed_fraction=0.5,
    meal_fraction=0.5,
    golden_hour_fraction=0.95,
    projected_wrap_fraction=0.9,
    projected_wrap_label="Projected wrap 18:00",
)
_PACE = PaceSnapshot(actual_points=[(0.0, 0.0)])


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


def test_carry_forward_snapshot_preserves_progress_fields_from_the_last_tick(monkeypatch):
    # The wrapped/error transition must not flash the clock, budget bar,
    # and page counts back to their zero defaults -- the day still
    # finished at a specific time with a specific budget consumed.
    day = build_day("nominal")
    last_tick = DaySnapshot(
        run_id=1,
        event_type="setup_wrapped",
        status="running",
        day_number=14,
        production_title="Invented Production",
        scenes=[],
        current_scene="5",
        clock="14:02",
        pages_completed_eighths=30,
        pages_remaining_eighths=22,
        total_page_eighths=52,
        setups_completed=9,
        setups_total=13,
        error_budget_consumed=0.62,
        burn_rate=1.4,
        projected_wrap="19:40",
        timeline=_TIMELINE,
        pace=_PACE,
        cast_clocks=[],
    )
    monkeypatch.setattr(STATE, "last_snapshot", last_tick)

    snapshot = _carry_forward_snapshot(day, run_id=1, status="wrapped", event_type="wrapped")

    assert snapshot.clock == "14:02"
    assert snapshot.error_budget_consumed == 0.62
    assert snapshot.pages_remaining_eighths == 22
    assert snapshot.projected_wrap == "19:40"
    assert snapshot.status == "wrapped"
    assert snapshot.event_type == "wrapped"
    assert snapshot.current_scene is None


def test_carry_forward_snapshot_falls_back_to_zeroed_defaults_for_a_stale_run_id(monkeypatch):
    day = build_day("nominal")
    stale_tick = DaySnapshot(
        run_id=1,
        event_type="setup_wrapped",
        status="running",
        day_number=14,
        production_title="Invented Production",
        scenes=[],
        clock="14:02",
        error_budget_consumed=0.62,
        timeline=_TIMELINE,
        pace=_PACE,
        cast_clocks=[],
    )
    monkeypatch.setattr(STATE, "last_snapshot", stale_tick)

    snapshot = _carry_forward_snapshot(day, run_id=2, status="wrapped", event_type="wrapped")

    assert snapshot.clock is None
    assert snapshot.error_budget_consumed == 0.0


def test_base_snapshot_reports_the_active_project_total_days(monkeypatch):
    day = build_day("nominal")

    with STATE.lock:
        STATE.active_total_days = 3

    snapshot = _base_snapshot(day, run_id=1, status="running", event_type="setup_wrapped")

    assert snapshot.total_days == 3

    with STATE.lock:
        STATE.active_total_days = 32  # restore the default for other tests


def test_active_day_and_scenario_falls_back_to_the_named_scenario_when_no_project_is_active(monkeypatch):
    from server import replay as replay_module

    with STATE.lock:
        STATE.active_project_slug = None

    day, scenario = replay_module._active_day_and_scenario("nominal")

    assert day.day_number == 14
    assert "1a" in scenario


def test_active_day_and_scenario_loads_the_active_project(monkeypatch):
    from server import replay as replay_module
    from server.projects import storage as storage_module

    fake_day = build_day("nominal")

    with STATE.lock:
        STATE.active_project_slug = "the-quarry"

    monkeypatch.setattr(storage_module, "load_day", lambda slug: fake_day if slug == "the-quarry" else None)

    day, scenario = replay_module._active_day_and_scenario("nominal")

    assert day is fake_day
    assert set(scenario.keys()) == {s.id for s in fake_day.setups}

    with STATE.lock:
        STATE.active_project_slug = None
