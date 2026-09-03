from datetime import datetime, timedelta
from pathlib import Path

import pytest
import yaml

from emitter.models import PageEighths, Performer, Scene, ShootingDay, Setup
from emitter.schedule import (
    _completed_eighths_trace,
    burn_rate,
    error_budget_consumed,
    error_budget_remaining,
    error_budget_total,
    meal_penalty_due,
    minutes_to_golden_hour,
    projected_recovery,
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
        scheduled_wrap=datetime(2026, 9, 3, 18, 0),
        overtime_threshold=datetime(2026, 9, 3, 19, 0),
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
        scheduled_wrap=datetime(2026, 9, 3, 18, 0),
        overtime_threshold=datetime(2026, 9, 3, 19, 0),
        golden_hour_start=datetime(2026, 9, 3, 18, 30),
        meal_due_by=datetime(2026, 9, 3, 13, 0),
        scenes=[scene_done, scene_remaining],
        setups=setups,
        performers=[],
    )


def test_error_budget_total_is_overtime_buffer_past_scheduled_wrap():
    day = _make_day_with_progress(completed_eighths=4, total_eighths=8)
    assert error_budget_total(day) == timedelta(hours=1)


def test_error_budget_consumed_is_zero_with_no_slippage():
    day = _make_day_with_progress(completed_eighths=4, total_eighths=8)
    now = day.general_call + timedelta(hours=5, minutes=30)
    assert projected_wrap(day, now) == day.scheduled_wrap
    assert error_budget_consumed(day, now) == pytest.approx(0.0)


def test_error_budget_consumed_is_one_when_slippage_equals_full_budget():
    day = _make_day_with_progress(completed_eighths=4, total_eighths=8)
    now = day.general_call + timedelta(hours=6)
    assert projected_wrap(day, now) == day.overtime_threshold
    assert error_budget_consumed(day, now) == pytest.approx(1.0)


def test_error_budget_consumed_clamps_to_one_beyond_full_budget():
    day = _make_day_with_progress(completed_eighths=4, total_eighths=8)
    now = day.general_call + timedelta(hours=7)
    assert error_budget_consumed(day, now) == pytest.approx(1.0)


def test_error_budget_consumed_is_zero_ahead_of_schedule_with_positive_remaining():
    day = _make_day_with_progress(completed_eighths=6, total_eighths=8)
    now = day.general_call + timedelta(hours=4)
    assert error_budget_consumed(day, now) == pytest.approx(0.0)
    assert error_budget_remaining(day, now) > timedelta()


def _make_windowed_day(scene_a_eighths: int, scene_a_minutes: int | None, total_eighths: int = 66) -> ShootingDay:
    scene_a = Scene(
        number="A",
        synopsis="Scene A",
        page_eighths=PageEighths(eighths=scene_a_eighths),
        int_ext="INT",
        day_night="DAY",
        location="Set",
        cast_ids=[],
        estimated_setups=1,
    )
    scene_b = Scene(
        number="B",
        synopsis="Scene B",
        page_eighths=PageEighths(eighths=total_eighths - scene_a_eighths),
        int_ext="INT",
        day_night="DAY",
        location="Set",
        cast_ids=[],
        estimated_setups=1,
    )
    setups = [
        Setup(id="Aa", scene_number="A", description="setup", estimated_minutes=20, actual_minutes=scene_a_minutes),
        Setup(id="Ba", scene_number="B", description="setup", estimated_minutes=20, actual_minutes=None),
    ]
    return ShootingDay(
        day_number=14,
        production_title="Invented Production",
        shoot_date=datetime(2026, 9, 3).date(),
        general_call=datetime(2026, 9, 3, 7, 0),
        scheduled_wrap=datetime(2026, 9, 3, 18, 0),
        overtime_threshold=datetime(2026, 9, 3, 19, 0),
        golden_hour_start=datetime(2026, 9, 3, 18, 30),
        meal_due_by=datetime(2026, 9, 3, 13, 0),
        scenes=[scene_a, scene_b],
        setups=setups,
        performers=[],
    )


def test_burn_rate_on_pace_is_one():
    day = _make_windowed_day(scene_a_eighths=6, scene_a_minutes=60)
    assert burn_rate(day, day.general_call + timedelta(minutes=60)) == pytest.approx(1.0)


def test_burn_rate_above_one_when_burning_faster_than_sustainable():
    day = _make_windowed_day(scene_a_eighths=3, scene_a_minutes=60)
    assert burn_rate(day, day.general_call + timedelta(minutes=60)) == pytest.approx(2.0)


def test_burn_rate_below_one_when_recovering():
    day = _make_windowed_day(scene_a_eighths=12, scene_a_minutes=60)
    assert burn_rate(day, day.general_call + timedelta(minutes=60)) == pytest.approx(0.5)


def test_burn_rate_at_day_start_defaults_to_one():
    day = _make_windowed_day(scene_a_eighths=6, scene_a_minutes=None)
    assert burn_rate(day, day.general_call) == pytest.approx(1.0)


def test_burn_rate_falls_back_to_previous_window_when_current_is_empty():
    # Scene A wraps at minute 30. At now=130 the trailing window (70,130]
    # is empty, so this must step back to (10,70], which does contain it.
    day = _make_windowed_day(scene_a_eighths=3, scene_a_minutes=30)
    assert burn_rate(day, day.general_call + timedelta(minutes=130)) == pytest.approx(2.0)


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
    assert scene_42_avg > other_avg * 1.8


# The scene breakdown below (which scenes exist, their page count) is
# invented purely for these tests — the real breakdown is Module 1b's
# job (data/day_14.json), not built yet. Only the per-setup actual
# timings come from the committed slipping.yaml, so the two stay in
# sync. All setups here are shot in day.setups list order, which is
# how burn_rate infers when each scene wrapped.
#
# Scene 42's three setups are modeled as three separate script scenes
# (42, 42B, 42C) rather than one scene with three setups. This matters:
# ShootingDay only credits a scene's page count once every one of its
# setups has wrapped, so one 10-eighth scene would dump its whole page
# count on burn_rate's trailing window in a single instant — reading as
# a burst of *good* progress, not the slow grind the takes/minutes
# actually describe. Splitting the coverage into three scenes credits
# it incrementally instead, matching the story the yaml numbers tell.
_DAY_14_GENERAL_CALL = datetime(2026, 9, 3, 7, 0)
_DAY_14_SCHEDULED_WRAP = datetime(2026, 9, 3, 18, 0)
_DAY_14_OVERTIME_THRESHOLD = datetime(2026, 9, 3, 19, 0)

# The day's total page count. Bumped from an earlier, smaller value so
# the hour before Scene 42 reads as "quietly behind" (burn_rate ~1.1-1.3)
# rather than implausibly ahead of pace.
_DAY_14_TOTAL_EIGHTHS = 52

# setup id -> scene_number
_DAY_14_SCENE_EIGHTHS = {
    "1": 4, "2": 4, "3": 4, "4": 4, "5": 4, "42": 4, "42B": 4, "42C": 2,
}
_DAY_14_SETUP_SCENES = {
    "1a": "1", "1b": "1",
    "2a": "2",
    "3a": "3", "3b": "3",
    "4a": "4",
    "5a": "5", "5b": "5", "5c": "5",
    "42a": "42", "42b": "42B", "42c": "42C",
}
_DAY_14_PADDING_SCENE_EIGHTHS = _DAY_14_TOTAL_EIGHTHS - sum(_DAY_14_SCENE_EIGHTHS.values())  # 22

_DAY_14_HOUR_BEFORE_SCENE_42 = timedelta(minutes=259)  # Scene 5 has just wrapped
_DAY_14_END_OF_SCENE_42 = timedelta(minutes=259 + 36 + 51 + 62)  # 42c has just wrapped

_RECOVERY_SCENE_NUMBER = "42D"  # a quick insert pickup shot right after Scene 42C
_RECOVERY_SCENE_EIGHTHS = 5
_RECOVERY_SETUP_ID = "42Da"


def _make_scene_for_day_14(number: str, eighths: int) -> Scene:
    return Scene(
        number=number,
        synopsis=f"Scene {number}",
        page_eighths=PageEighths(eighths=eighths),
        int_ext="INT",
        day_night="DAY",
        location="Set",
        cast_ids=[],
        estimated_setups=1,
    )


def _make_slipping_day(
    padding_scene_eighths: int = _DAY_14_PADDING_SCENE_EIGHTHS,
    through_scene_42: bool = True,
    include_recovery_scene: bool = False,
    shoot_recovery_pickup: bool = False,
) -> ShootingDay:
    """The slipping scenario applied to an invented Day 14 plan.

    Scenes 1-5 and 42/42B/42C come straight from slipping.yaml's
    actual_minutes. A padding scene ("43", never shot in this fixture)
    makes up the rest of the day's page count, so total_page_eighths
    reflects a whole day rather than just the setups exercised here.

    ShootingDay is a static snapshot of "what's been shot so far", not
    a replay — completed_page_eighths doesn't know about the "now"
    passed to schedule functions, only what actual_minutes is set on
    each Setup. through_scene_42=False stops the snapshot at the end
    of Scene 5, for checkpoints that need Scene 42 to not have
    happened yet.

    include_recovery_scene carves Scene 42D's page count out of that
    padding (total_page_eighths stays _DAY_14_TOTAL_EIGHTHS either
    way); shoot_recovery_pickup (only meaningful alongside it) marks
    that scene's setup as actually shot. Splitting the two lets the
    recovery test hold total_page_eighths constant across a before/
    after pair while only the "has it been shot yet" bit changes.
    """
    scenario_setups = _load_scenario("slipping.yaml")["setups"]

    scene_eighths = dict(_DAY_14_SCENE_EIGHTHS)
    scene_eighths["43"] = padding_scene_eighths
    if include_recovery_scene:
        scene_eighths["43"] -= _RECOVERY_SCENE_EIGHTHS
        scene_eighths[_RECOVERY_SCENE_NUMBER] = _RECOVERY_SCENE_EIGHTHS

    scenes = [_make_scene_for_day_14(number, eighths) for number, eighths in scene_eighths.items()]

    setups = [
        Setup(
            id=setup_id,
            scene_number=scene_number,
            description="setup",
            estimated_minutes=scenario_setups[setup_id]["actual_minutes"],
            actual_minutes=(
                scenario_setups[setup_id]["actual_minutes"]
                if (through_scene_42 or scene_number in ("1", "2", "3", "4", "5"))
                else None
            ),
        )
        for setup_id, scene_number in _DAY_14_SETUP_SCENES.items()
    ]
    if include_recovery_scene:
        actual_minutes = scenario_setups[_RECOVERY_SETUP_ID]["actual_minutes"]
        setups.append(
            Setup(
                id=_RECOVERY_SETUP_ID,
                scene_number=_RECOVERY_SCENE_NUMBER,
                description="setup",
                estimated_minutes=actual_minutes,
                actual_minutes=actual_minutes if shoot_recovery_pickup else None,
            )
        )

    return ShootingDay(
        day_number=14,
        production_title="Invented Production",
        shoot_date=_DAY_14_GENERAL_CALL.date(),
        general_call=_DAY_14_GENERAL_CALL,
        scheduled_wrap=_DAY_14_SCHEDULED_WRAP,
        overtime_threshold=_DAY_14_OVERTIME_THRESHOLD,
        golden_hour_start=datetime(2026, 9, 3, 18, 30),
        meal_due_by=datetime(2026, 9, 3, 13, 0),
        scenes=scenes,
        setups=setups,
        performers=[],
    )


def test_slipping_scenario_burn_rate_is_quietly_behind_the_hour_before_scene_42():
    day = _make_slipping_day()
    now = day.general_call + _DAY_14_HOUR_BEFORE_SCENE_42
    assert 1.1 <= burn_rate(day, now) <= 1.3


def test_slipping_scenario_consumed_is_modest_at_start_of_scene_42():
    day = _make_slipping_day(through_scene_42=False)
    now = day.general_call + _DAY_14_HOUR_BEFORE_SCENE_42
    assert 0.2 <= error_budget_consumed(day, now) <= 0.3


def test_slipping_scenario_burn_rate_spikes_during_scene_42():
    day = _make_slipping_day()
    now = day.general_call + _DAY_14_END_OF_SCENE_42
    assert burn_rate(day, now) > 2.0


def test_slipping_scenario_consumed_is_meaningfully_high_by_end_of_scene_42():
    day = _make_slipping_day()
    now = day.general_call + _DAY_14_END_OF_SCENE_42
    assert 0.75 <= error_budget_consumed(day, now) <= 0.85


def test_slipping_scenario_burn_rate_recovers_but_consumed_holds_its_high_water_mark():
    # burn_rate only looks at the trailing window, so the quick pickup
    # (Scene 42D) immediately pulls it back under 1.0. error_budget_consumed
    # is a high-water mark — a schedule slip is spent time, and that
    # slack doesn't come back just because the crew sped up afterward.
    # The recovery instead shows up in projected_recovery: the current
    # forecast improves (projects earlier than the worst-case wrap that
    # set the high-water mark), even though the budget already spent
    # stays spent. That's the real independence: a fast window improves
    # the rate and the forecast, but never refunds the budget.
    before = _make_slipping_day(include_recovery_scene=True)
    after = _make_slipping_day(include_recovery_scene=True, shoot_recovery_pickup=True)

    now_before = before.general_call + _DAY_14_END_OF_SCENE_42
    now_after = now_before + timedelta(minutes=10)  # 42Da (quick pickup) has just wrapped

    assert burn_rate(before, now_before) > 2.0
    assert burn_rate(after, now_after) < 1.0
    assert 0.75 <= error_budget_consumed(before, now_before) <= 0.85
    assert error_budget_consumed(after, now_after) == pytest.approx(error_budget_consumed(before, now_before))
    assert projected_recovery(after, now_after) > timedelta()


def test_error_budget_consumed_is_monotonically_non_decreasing_across_slipping_scenario():
    day = _make_slipping_day(include_recovery_scene=True, shoot_recovery_pickup=True)
    sample_points = sorted({elapsed for elapsed, _ in _completed_eighths_trace(day)})

    values = [error_budget_consumed(day, day.general_call + elapsed) for elapsed in sample_points]

    assert values == sorted(values)
