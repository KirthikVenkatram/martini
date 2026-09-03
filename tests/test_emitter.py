from __future__ import annotations

import time

from emitter.simulator import build_day, load_scenario, replay_day

SPEED = 100_000
"""Fast enough that replaying either scenario is wall-clock instant in tests."""


def test_replay_produces_monotonically_advancing_virtual_time():
    day = build_day("nominal")
    scenario = load_scenario("nominal")
    events: list[dict] = []

    replay_day(day, scenario, speed_factor=SPEED, on_event=events.append, dry_run=True)

    times = [event["now"] for event in events]
    assert times == sorted(times)
    assert len(set(times)) > 1


def test_replay_marks_every_scenario_setup_complete():
    day = build_day("slipping")
    scenario = load_scenario("slipping")

    replay_day(day, scenario, speed_factor=SPEED, dry_run=True)

    for setup_id, timing in scenario.items():
        setup = next(s for s in day.setups if s.id == setup_id)
        assert setup.is_complete
        assert setup.actual_minutes == timing["actual_minutes"]
        assert setup.takes == timing["takes"]


def test_on_event_fires_once_per_setup():
    day = build_day("nominal")
    scenario = load_scenario("nominal")
    events: list[dict] = []

    replay_day(day, scenario, speed_factor=SPEED, on_event=events.append, dry_run=True)

    setup_wrapped = [e for e in events if e["type"] == "setup_wrapped"]
    assert [e["setup"] for e in setup_wrapped] == list(scenario.keys())


def test_dry_run_makes_no_network_calls():
    day = build_day("nominal")
    scenario = load_scenario("nominal")

    start = time.monotonic()
    replay_day(day, scenario, speed_factor=SPEED, dry_run=True)
    elapsed = time.monotonic() - start

    assert elapsed < 5.0
