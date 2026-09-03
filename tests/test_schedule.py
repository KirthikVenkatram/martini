from datetime import datetime, timedelta
from pathlib import Path

import pytest
import yaml

from emitter.models import PageEighths, Performer, Scene, ShootingDay, Setup
from emitter.schedule import (
    error_budget_consumed,
    meal_penalty_due,
    minutes_to_golden_hour,
    projected_wrap,
    turnaround_violation,
)

SCENARIOS_DIR = Path(__file__).parent.parent / "emitter" / "scenarios"


def _make_shooting_day() -> ShootingDay:
    scene_one = Scene(
        number="1",
        synopsis="Scene one",
        page_eighths=PageEighths.from_string("1"),
        int_ext="INT",
        day_night="DAY",
        location="Kitchen",
        cast_ids=[],
        estimated_setups=1,
    )
    scene_two = Scene(
        number="2",
        synopsis="Scene two",
        page_eighths=PageEighths.from_string("2"),
        int_ext="EXT",
        day_night="DAY",
        location="Yard",
        cast_ids=[],
        estimated_setups=2,
    )
    setups = [
        Setup(id="1a", scene_number="1", description="wide", estimated_minutes=20, actual_minutes=20),
        Setup(id="2a", scene_number="2", description="wide", estimated_minutes=20, actual_minutes=20),
        Setup(id="2b", scene_number="2", description="close", estimated_minutes=20, actual_minutes=None),
    ]
    return ShootingDay(
        day_number=14,
        production_title="Invented Production",
        shoot_date=datetime(2026, 9, 3).date(),
        general_call=datetime(2026, 9, 3, 7, 0),
        scheduled_wrap=datetime(2026, 9, 3, 19, 0),
        overtime_threshold=datetime(2026, 9, 3, 20, 0),
        golden_hour_start=datetime(2026, 9, 3, 18, 30),
        meal_due_by=datetime(2026, 9, 3, 13, 0),
        scenes=[scene_one, scene_two],
        setups=setups,
        performers=[],
    )


def test_shooting_day_total_page_eighths():
    assert _make_shooting_day().total_page_eighths == PageEighths(eighths=24)


def test_shooting_day_completed_page_eighths_only_counts_fully_wrapped_scenes():
    assert _make_shooting_day().completed_page_eighths == PageEighths(eighths=8)


def test_shooting_day_remaining_page_eighths():
    assert _make_shooting_day().remaining_page_eighths == PageEighths(eighths=16)


def test_shooting_day_total_setups():
    assert _make_shooting_day().total_setups == 3


def test_shooting_day_completed_setups():
    assert _make_shooting_day().completed_setups == 2


def _make_scene(int_ext: str, day_night: str) -> Scene:
    return Scene(
        number="1",
        synopsis="Test scene",
        page_eighths=PageEighths.from_string("1"),
        int_ext=int_ext,
        day_night=day_night,
        location="Test location",
        cast_ids=[],
        estimated_setups=1,
    )


@pytest.mark.parametrize(
    "int_ext, day_night, expected",
    [
        ("INT", "DAY", "day-int"),
        ("EXT", "DAY", "day-ext"),
        ("INT", "NIGHT", "night-int"),
        ("EXT", "NIGHT", "night-ext"),
    ],
)
def test_scene_strip_color(int_ext, day_night, expected):
    assert _make_scene(int_ext, day_night).strip_color == expected


def test_setup_is_complete_when_actual_minutes_recorded():
    setup = Setup(id="1a", scene_number="1", description="wide", estimated_minutes=20, actual_minutes=25)
    assert setup.is_complete is True


def test_setup_is_not_complete_when_actual_minutes_missing():
    setup = Setup(id="1a", scene_number="1", description="wide", estimated_minutes=20, actual_minutes=None)
    assert setup.is_complete is False


def test_page_eighths_parses_whole_and_fraction():
    assert PageEighths.from_string("2 3/8").eighths == 19


def test_page_eighths_parses_fraction_only():
    assert PageEighths.from_string("3/8").eighths == 3


def test_page_eighths_parses_whole_only():
    assert PageEighths.from_string("2").eighths == 16


def test_page_eighths_str_round_trips_whole_and_fraction():
    assert str(PageEighths.from_string("2 3/8")) == "2 3/8"


def test_page_eighths_str_round_trips_fraction_only():
    assert str(PageEighths.from_string("3/8")) == "3/8"


def test_page_eighths_str_round_trips_whole_only():
    assert str(PageEighths.from_string("2")) == "2"


def test_page_eighths_str_zero():
    assert str(PageEighths(eighths=0)) == "0"


def test_page_eighths_addition():
    result = PageEighths.from_string("1 4/8") + PageEighths.from_string("3/8")
    assert result == PageEighths(eighths=15)


def test_page_eighths_subtraction():
    result = PageEighths.from_string("2") - PageEighths.from_string("3/8")
    assert result == PageEighths(eighths=13)


def test_page_eighths_ordering():
    small = PageEighths.from_string("3/8")
    large = PageEighths.from_string("1")
    assert small < large
    assert large > small
    assert small <= PageEighths.from_string("3/8")
    assert small >= PageEighths.from_string("3/8")


def _make_day_with_progress(completed_eighths: int, total_eighths: int) -> ShootingDay:
    remaining_eighths = total_eighths - completed_eighths
    scene_done = Scene(
        number="1",
        synopsis="Completed portion",
        page_eighths=PageEighths(eighths=completed_eighths),
        int_ext="INT",
        day_night="DAY",
        location="Kitchen",
        cast_ids=[],
        estimated_setups=1,
    )
    scene_remaining = Scene(
        number="2",
        synopsis="Remaining portion",
        page_eighths=PageEighths(eighths=remaining_eighths),
        int_ext="EXT",
        day_night="DAY",
        location="Yard",
        cast_ids=[],
        estimated_setups=1,
    )
    setups = [
        Setup(id="1a", scene_number="1", description="wide", estimated_minutes=20, actual_minutes=20),
        Setup(id="2a", scene_number="2", description="wide", estimated_minutes=20, actual_minutes=None),
    ]
    return ShootingDay(
        day_number=14,
        production_title="Invented Production",
        shoot_date=datetime(2026, 9, 3).date(),
        general_call=datetime(2026, 9, 3, 7, 0),
        scheduled_wrap=datetime(2026, 9, 3, 19, 0),
        overtime_threshold=datetime(2026, 9, 3, 20, 0),
        golden_hour_start=datetime(2026, 9, 3, 18, 30),
        meal_due_by=datetime(2026, 9, 3, 13, 0),
        scenes=[scene_done, scene_remaining],
        setups=setups,
        performers=[],
    )


def test_error_budget_consumed_at_day_start_is_zero():
    day = _make_day_with_progress(completed_eighths=0, total_eighths=8)
    assert error_budget_consumed(day, day.general_call) == pytest.approx(0.0)


def test_error_budget_consumed_on_pace_midday_is_fully_allocated():
    day = _make_day_with_progress(completed_eighths=4, total_eighths=8)
    midday = day.general_call + (day.overtime_threshold - day.general_call) / 2
    assert error_budget_consumed(day, midday) == pytest.approx(1.0)


def test_error_budget_consumed_behind_pace_clamps_to_one():
    day = _make_day_with_progress(completed_eighths=2, total_eighths=8)
    midday = day.general_call + (day.overtime_threshold - day.general_call) / 2
    assert error_budget_consumed(day, midday) == pytest.approx(1.0)


def test_projected_wrap_with_no_progress_falls_back_to_scheduled_wrap():
    day = _make_day_with_progress(completed_eighths=0, total_eighths=8)
    assert projected_wrap(day, day.general_call) == day.scheduled_wrap


def test_projected_wrap_extrapolates_from_observed_pace():
    day = _make_day_with_progress(completed_eighths=4, total_eighths=8)
    now = day.general_call + timedelta(hours=4)
    result = projected_wrap(day, now)
    # 4 hours to complete half the pages -> 4 more hours for the rest.
    assert result == now + timedelta(hours=4)


def test_minutes_to_golden_hour_before_golden_hour():
    day = _make_day_with_progress(completed_eighths=0, total_eighths=8)
    now = day.golden_hour_start - timedelta(minutes=30)
    assert minutes_to_golden_hour(day, now) == 30


def test_minutes_to_golden_hour_after_golden_hour_is_negative():
    day = _make_day_with_progress(completed_eighths=0, total_eighths=8)
    now = day.golden_hour_start + timedelta(minutes=15)
    assert minutes_to_golden_hour(day, now) == -15


def test_turnaround_violation_returns_none_when_rest_is_sufficient():
    performer = Performer(
        id="p1",
        name="Test Performer",
        character_name="Lead",
        call_time=datetime(2026, 9, 3, 7, 0),
        previous_night_wrap=datetime(2026, 9, 2, 20, 0),
        minimum_turnaround_hours=11.0,
    )
    proposed_call_time = datetime(2026, 9, 3, 7, 0)
    assert turnaround_violation(performer, proposed_call_time) is None


def test_turnaround_violation_returns_shortfall_when_rest_is_insufficient():
    performer = Performer(
        id="p1",
        name="Test Performer",
        character_name="Lead",
        call_time=datetime(2026, 9, 3, 7, 0),
        previous_night_wrap=datetime(2026, 9, 2, 22, 0),
        minimum_turnaround_hours=11.0,
    )
    proposed_call_time = datetime(2026, 9, 3, 7, 0)
    assert turnaround_violation(performer, proposed_call_time) == timedelta(hours=2)


def test_meal_penalty_due_once_past_meal_due_by_with_no_meal_taken():
    day = _make_day_with_progress(completed_eighths=0, total_eighths=8)
    last_meal_break = day.general_call
    now = day.meal_due_by + timedelta(minutes=1)
    assert meal_penalty_due(day, now, last_meal_break) is True


def test_meal_penalty_not_due_before_meal_due_by():
    day = _make_day_with_progress(completed_eighths=0, total_eighths=8)
    last_meal_break = day.general_call
    now = day.meal_due_by - timedelta(minutes=1)
    assert meal_penalty_due(day, now, last_meal_break) is False


def _load_scenario(name: str) -> dict:
    with open(SCENARIOS_DIR / name) as f:
        return yaml.safe_load(f)


def test_nominal_scenario_holds_pace_through_scene_42():
    setups = _load_scenario("nominal.yaml")["setups"]
    scene_42_avg = sum(setups[s]["actual_minutes"] for s in ("42a", "42b", "42c")) / 3
    other_avg = sum(
        v["actual_minutes"] for k, v in setups.items() if k not in ("42a", "42b", "42c")
    ) / (len(setups) - 3)
    assert abs(scene_42_avg - other_avg) < 10


def test_slipping_scenario_collapses_at_scene_42():
    setups = _load_scenario("slipping.yaml")["setups"]
    scene_42_avg = sum(setups[s]["actual_minutes"] for s in ("42a", "42b", "42c")) / 3
    other_avg = sum(
        v["actual_minutes"] for k, v in setups.items() if k not in ("42a", "42b", "42c")
    ) / (len(setups) - 3)
    assert scene_42_avg > other_avg * 2
