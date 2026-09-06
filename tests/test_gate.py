"""Gate tests -- the suite that matters most in this project.

gate/checker.py is the deterministic legality check that stands
between the replanner's (LLM) proposals and what the agent is allowed
to act on. If it is wrong on camera, the whole premise collapses, so
every rule path here is exercised against real computed shortfalls,
never a hardcoded one.
"""

from __future__ import annotations

import inspect
import socket
from datetime import datetime, timedelta

import pytest

from emitter.models import Performer, ShootingDay
from gate.checker import RecoveryOption, Violation, check
from gate.explain import explain

GENERAL_CALL = datetime(2026, 9, 3, 7, 0)
SHOOT_DATE = GENERAL_CALL.date()
MEAL_DUE_BY = datetime(2026, 9, 3, 13, 0)

PRIYA = Performer(
    id="priya",
    name="Priya Test",
    character_name="PRIYA",
    call_time=datetime(2026, 9, 3, 7, 0),
    previous_night_wrap=datetime(2026, 9, 2, 20, 0),
    minimum_turnaround_hours=11.0,
    is_minor=False,
)

JULIAN = Performer(
    id="julian",
    name="Julian Test",
    character_name="JULIAN",
    call_time=datetime(2026, 9, 3, 11, 0),
    previous_night_wrap=None,
    minimum_turnaround_hours=12.0,
    is_minor=True,
)

MARCUS = Performer(
    id="marcus",
    name="Marcus Test",
    character_name="MARCUS",
    call_time=datetime(2026, 9, 3, 9, 0),
    previous_night_wrap=datetime(2026, 9, 2, 20, 0),
    minimum_turnaround_hours=11.0,
    is_minor=False,
)


def _make_day() -> ShootingDay:
    return ShootingDay(
        day_number=14,
        production_title="Invented Production",
        shoot_date=SHOOT_DATE,
        general_call=GENERAL_CALL,
        scheduled_wrap=datetime(2026, 9, 3, 18, 0),
        overtime_threshold=datetime(2026, 9, 3, 19, 0),
        golden_hour_start=datetime(2026, 9, 3, 18, 30),
        meal_due_by=MEAL_DUE_BY,
        scenes=[],
        setups=[],
        performers=[PRIYA, JULIAN, MARCUS],
    )


def _option(option_id: str, proposed_call_times: dict[str, datetime] | None) -> RecoveryOption:
    return RecoveryOption(
        id=option_id,
        kind="reorder",
        description="Reorder to pull a scene forward.",
        affected_scenes=["1"],
        minutes_recovered=20,
        proposed_call_times=proposed_call_times,
    )


def test_turnaround_violation_is_rejected_with_correct_shortfall():
    day = _make_day()
    option = _option("opt-early", {"priya": datetime(2026, 9, 3, 6, 20)})

    verdict = check(day, option)

    assert verdict.approved is False
    assert len(verdict.violations) == 1
    violation = verdict.violations[0]
    assert violation.rule == "turnaround"
    assert violation.performer_id == "PRIYA"
    assert violation.shortfall == timedelta(minutes=40)
    assert "PRIYA" in violation.reason


def test_same_option_shifted_two_hours_later_is_approved():
    day = _make_day()
    option = _option("opt-early", {"priya": datetime(2026, 9, 3, 6, 20)})
    shifted = _option("opt-shifted", {"priya": datetime(2026, 9, 3, 6, 20) + timedelta(hours=2)})

    original_verdict = check(day, option)
    shifted_verdict = check(day, shifted)

    assert original_verdict.approved is False
    assert shifted_verdict.approved is True
    assert shifted_verdict.violations == []


def test_minor_working_past_wrap_limit_is_rejected():
    day = _make_day()
    # JULIAN is a minor: max_working_hours=9.0 from an 11:00 call
    # projects a 20:00 wrap, an hour past the 19:00 must_wrap_by.
    option = _option("opt-minor", {"julian": datetime(2026, 9, 3, 11, 0)})

    verdict = check(day, option)

    assert verdict.approved is False
    minors_violations = [v for v in verdict.violations if v.rule == "minors"]
    assert len(minors_violations) == 1
    assert minors_violations[0].shortfall == timedelta(hours=1)
    assert "JULIAN" in minors_violations[0].reason


def test_meal_window_breach_is_rejected():
    day = _make_day()
    # MARCUS's turnaround and minor status are both clean at 14:00 --
    # only the meal window (due by 13:00) is breached.
    option = _option("opt-meal", {"marcus": datetime(2026, 9, 3, 14, 0)})

    verdict = check(day, option)

    assert verdict.approved is False
    meal_violations = [v for v in verdict.violations if v.rule == "meal"]
    assert len(meal_violations) == 1
    assert meal_violations[0].performer_id is None
    assert meal_violations[0].shortfall == timedelta(hours=1)
    assert "13:00" in meal_violations[0].reason


def test_clean_option_is_approved_with_zero_violations():
    day = _make_day()
    option = _option("opt-clean", None)

    verdict = check(day, option)

    assert verdict.approved is True
    assert verdict.violations == []
    assert verdict.projected_recovery == timedelta(minutes=option.minutes_recovered)


def test_explain_contains_character_name_and_no_rule_codes():
    day = _make_day()
    option = _option("opt-early", {"priya": datetime(2026, 9, 3, 6, 20)})
    verdict = check(day, option)

    text = explain(verdict.violations[0])

    assert "PRIYA" in text
    assert "Violation" not in text
    assert "rule=" not in text
    assert "_" not in text


def test_gate_never_calls_llm_or_network(monkeypatch):
    def _boom(*args, **kwargs):
        raise AssertionError("gate.checker attempted a network connection")

    monkeypatch.setattr(socket.socket, "connect", _boom)

    day = _make_day()
    verdict = check(day, _option("opt-clean", None))
    assert verdict.approved is True

    import gate.checker as checker_module

    source = inspect.getsource(checker_module)
    assert "genai" not in source
    assert "google.adk" not in source
