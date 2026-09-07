"""Tests for the concurrency guards in server/state.py (Module 6).

These are the guards the corrections called out explicitly: a second
POST /api/day/start (or a race with a page refresh) must never start a
second replay thread, and a recovery cycle must never fire twice for
the same run.
"""

from __future__ import annotations

from server.state import AppState, DaySnapshot, PaceSnapshot, TimelineSnapshot

_TIMELINE = TimelineSnapshot(
    call_label="07:00",
    overtime_label="19:00",
    elapsed_fraction=0.0,
    meal_fraction=0.5,
    golden_hour_fraction=0.95,
    projected_wrap_fraction=0.0,
    projected_wrap_label="Projected wrap 18:00",
)
_PACE = PaceSnapshot(actual_points=[(0.0, 0.0)])


def test_try_start_returns_run_id_then_blocks_while_running():
    state = AppState()

    first = state.try_start()
    assert first == 1
    assert state.status == "running"

    assert state.try_start() is None

    state.status = "wrapped"
    second = state.try_start()
    assert second == 2


def test_try_claim_recovery_only_succeeds_once_per_run():
    state = AppState()
    run_id = state.try_start()

    assert state.try_claim_recovery(run_id) is True
    assert state.try_claim_recovery(run_id) is False


def test_try_claim_recovery_rejects_a_superseded_run_id():
    state = AppState()
    old_run_id = state.try_start()
    state.status = "wrapped"
    new_run_id = state.try_start()

    assert new_run_id != old_run_id
    assert state.try_claim_recovery(old_run_id) is False
    assert state.try_claim_recovery(new_run_id) is True


def test_publish_delivers_to_subscribers_and_records_last_snapshot():
    state = AppState()
    q = state.subscribe()
    snapshot = DaySnapshot(
        run_id=1,
        event_type="connected",
        status="idle",
        day_number=14,
        production_title="Invented Production",
        scenes=[],
        timeline=_TIMELINE,
        pace=_PACE,
        cast_clocks=[],
    )

    state.publish(snapshot)

    assert q.get_nowait() is snapshot
    assert state.last_snapshot is snapshot


def test_unsubscribe_stops_delivery():
    state = AppState()
    q = state.subscribe()
    state.unsubscribe(q)

    state.publish(
        DaySnapshot(
            run_id=1, event_type="connected", status="idle",
            day_number=14, production_title="Invented Production", scenes=[],
            timeline=_TIMELINE, pace=_PACE, cast_clocks=[],
        )
    )

    assert q.empty()
