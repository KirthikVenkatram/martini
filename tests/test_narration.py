"""Tests for server/narration.py -- the console's plain-English copy.

These are pure functions of a ShootingDay (+ a datetime for the tick
variants), so they're tested directly rather than through a running
server, same as the other server/replay.py pure helpers.
schedule.projected_wrap is monkeypatched where a test needs a specific
projection -- narration.py's own job is the wording around that
number, not schedule.py's math, which already has its own tests.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from emitter.simulator import GENERAL_CALL, OVERTIME_THRESHOLD, SCHEDULED_WRAP, build_day
from server import narration

DAY = build_day("nominal")


def test_idle_narration_states_the_general_call_and_a_full_cushion():
    result = narration.idle_narration(DAY)

    assert result["verdict_headline"] == "STANDING BY FOR CALL"
    assert "07:00" in result["verdict_subline"]
    assert "cushion is untouched" in result["budget_sentence"].lower()
    assert "42-person crew" in result["cost_of_delay_sentence"]


def test_verdict_is_making_the_day_when_projected_wrap_is_on_schedule(monkeypatch):
    monkeypatch.setattr(narration.schedule, "projected_wrap", lambda day, now: SCHEDULED_WRAP)

    headline, subline = narration._verdict_headline_and_subline(DAY, GENERAL_CALL, "running")

    assert headline == "MAKING THE DAY"
    assert "on schedule" in subline


def test_verdict_is_running_behind_with_exact_minutes_inside_the_overtime_buffer(monkeypatch):
    late_but_inside_overtime = SCHEDULED_WRAP + timedelta(minutes=25)
    monkeypatch.setattr(narration.schedule, "projected_wrap", lambda day, now: late_but_inside_overtime)

    headline, subline = narration._verdict_headline_and_subline(DAY, GENERAL_CALL, "running")

    assert headline == "RUNNING 25 MINUTES BEHIND"
    assert "inside the overtime buffer" in subline


def test_verdict_states_minutes_into_overtime_once_projected_wrap_passes_the_threshold(monkeypatch):
    past_overtime = OVERTIME_THRESHOLD + timedelta(minutes=15)
    monkeypatch.setattr(narration.schedule, "projected_wrap", lambda day, now: past_overtime)

    headline, subline = narration._verdict_headline_and_subline(DAY, GENERAL_CALL, "running")

    assert headline.startswith("RUNNING")
    assert "15 minutes into overtime" in subline


def test_verdict_headline_is_at_risk_once_status_flips_regardless_of_pace(monkeypatch):
    monkeypatch.setattr(narration.schedule, "projected_wrap", lambda day, now: SCHEDULED_WRAP)

    headline, _ = narration._verdict_headline_and_subline(DAY, GENERAL_CALL, "at_risk")

    assert headline == "THE DAY IS AT RISK"


def test_burn_sentence_wording_matches_the_rate():
    assert "losing about 2.0 minutes" in narration._burn_sentence(2.0)
    assert "gaining time back" in narration._burn_sentence(0.5)
    assert "holding pace" in narration._burn_sentence(1.0)


def test_pages_sentence_uses_eighths_display_and_setups_remaining():
    sentence = narration._pages_sentence(pages_remaining_eighths=20, setups_remaining=4)

    assert sentence == "2 4/8 pages still to shoot, 4 setups left."


def test_budget_sentence_is_untouched_at_zero_percent():
    assert narration._budget_sentence(DAY, GENERAL_CALL) == (
        "Cushion is untouched -- the full overtime buffer is still there."
    )


def test_budget_sentence_reports_minutes_of_slack_left(monkeypatch):
    monkeypatch.setattr(narration.schedule, "error_budget_consumed", lambda day, now: 0.6)
    monkeypatch.setattr(narration.schedule, "error_budget_remaining", lambda day, now: timedelta(minutes=13))

    sentence = narration._budget_sentence(DAY, GENERAL_CALL)

    assert sentence == "60% of your cushion is gone -- about 13 minutes of slack left."


def test_budget_sentence_reports_already_into_overtime_once_remaining_goes_negative(monkeypatch):
    monkeypatch.setattr(narration.schedule, "error_budget_consumed", lambda day, now: 1.0)
    monkeypatch.setattr(narration.schedule, "error_budget_remaining", lambda day, now: timedelta(minutes=-8))

    sentence = narration._budget_sentence(DAY, GENERAL_CALL)

    assert sentence == "100% of your cushion is gone -- you're already 8 minutes into overtime."


def test_tick_narration_returns_every_expected_key():
    result = narration.tick_narration(
        DAY,
        GENERAL_CALL,
        "running",
        pages_remaining_eighths=52,
        setups_completed=0,
        setups_total=13,
        burn_rate=1.0,
    )

    assert set(result) == {
        "verdict_headline",
        "verdict_subline",
        "budget_sentence",
        "burn_sentence",
        "pages_sentence",
        "cost_of_delay_sentence",
    }
