from __future__ import annotations

from datetime import date, datetime

from emitter.models import PageEighths, Scene
from agent.tools.scheduling import CastEntry, build_shooting_day


def _scene(number: str, eighths: str, cast_ids: list[str], setups: int) -> Scene:
    return Scene(
        number=number,
        synopsis=f"Scene {number}.",
        page_eighths=PageEighths.from_string(eighths),
        int_ext="INT",
        day_night="DAY",
        location="Set",
        cast_ids=cast_ids,
        estimated_setups=setups,
    )


def test_build_shooting_day_derives_setups_from_estimated_setups():
    scenes = [_scene("1", "2", ["marcus"], setups=3)]
    cast = [CastEntry(character_name="MARCUS", previous_night_wrap=datetime(2026, 9, 2, 20, 0))]

    day = build_shooting_day(scenes, cast, day_number=1, shoot_date=date(2026, 9, 8), production_title="Test Day")

    scene_setups = [s for s in day.setups if s.scene_number == "1"]
    assert len(scene_setups) == 3
    assert all(s.estimated_minutes > 0 for s in scene_setups)
    assert all(s.actual_minutes is None for s in scene_setups)


def test_build_shooting_day_assigns_call_and_wrap_times_in_order():
    scenes = [_scene("1", "1", [], setups=1)]
    cast: list[CastEntry] = []

    day = build_shooting_day(scenes, cast, day_number=1, shoot_date=date(2026, 9, 8), production_title="Test Day")

    assert day.general_call < day.scheduled_wrap < day.overtime_threshold
    assert day.general_call.date() == date(2026, 9, 8)


def test_build_shooting_day_defaults_turnaround_from_production_rules():
    scenes = [_scene("1", "1", ["priya", "juno"], setups=1)]
    cast = [
        CastEntry(character_name="PRIYA", is_minor=False, previous_night_wrap=datetime(2026, 9, 2, 20, 0)),
        CastEntry(character_name="JUNO", is_minor=True, previous_night_wrap=datetime(2026, 9, 2, 20, 0)),
    ]

    day = build_shooting_day(scenes, cast, day_number=1, shoot_date=date(2026, 9, 8), production_title="Test Day")

    priya = next(p for p in day.performers if p.character_name == "PRIYA")
    juno = next(p for p in day.performers if p.character_name == "JUNO")
    assert priya.minimum_turnaround_hours == 11.0
    assert juno.minimum_turnaround_hours == 12.0


def test_build_shooting_day_honors_an_explicit_turnaround_override():
    scenes = [_scene("1", "1", ["marcus"], setups=1)]
    cast = [
        CastEntry(
            character_name="MARCUS",
            previous_night_wrap=datetime(2026, 9, 2, 20, 0),
            minimum_turnaround_hours=13.0,
        )
    ]

    day = build_shooting_day(scenes, cast, day_number=1, shoot_date=date(2026, 9, 8), production_title="Test Day")

    assert day.performers[0].minimum_turnaround_hours == 13.0


def test_build_shooting_day_honors_an_explicit_zero_turnaround_override():
    scenes = [_scene("1", "1", ["marcus"], setups=1)]
    cast = [
        CastEntry(
            character_name="MARCUS",
            previous_night_wrap=datetime(2026, 9, 2, 20, 0),
            minimum_turnaround_hours=0.0,
        )
    ]

    day = build_shooting_day(scenes, cast, day_number=1, shoot_date=date(2026, 9, 8), production_title="Test Day")

    assert day.performers[0].minimum_turnaround_hours == 0.0


def test_build_shooting_day_joins_scene_cast_ids_to_performer_ids_by_slug():
    scenes = [_scene("1", "1", ["desmond-ruiz"], setups=1)]
    cast = [CastEntry(character_name="Desmond Ruiz", previous_night_wrap=datetime(2026, 9, 2, 20, 0))]

    day = build_shooting_day(scenes, cast, day_number=1, shoot_date=date(2026, 9, 8), production_title="Test Day")

    assert day.performers[0].id == "desmond-ruiz"
    assert day.scenes[0].cast_ids == ["desmond-ruiz"]


from datetime import timedelta

from agent.root import AT_RISK_ERROR_BUDGET_CONSUMED
from emitter.models import ShootingDay, Setup
from emitter.schedule import error_budget_consumed
from agent.tools.scheduling import generate_scenario


def _day_with_scenes(scene_eighths: dict[str, str], setups_per_scene: int = 1) -> ShootingDay:
    scenes = [_scene(number, eighths, [], setups=setups_per_scene) for number, eighths in scene_eighths.items()]
    return build_shooting_day(scenes, [], day_number=1, shoot_date=date(2026, 9, 8), production_title="Test Day")


def _tight_day() -> ShootingDay:
    """A hand-built day (bypassing build_shooting_day's fixed 11-hour
    template) with only a 30-minute error budget and setups whose
    baseline timing already finishes the day early -- so the AT_RISK
    crossing in the test below happens only once generate_scenario's
    inflation of the longest scene (scene "2", 3 setups) pushes the
    total elapsed time past it, not from the baseline alone."""
    general_call = datetime(2026, 9, 8, 7, 0)
    scheduled_wrap = general_call + timedelta(hours=2)
    overtime_threshold = scheduled_wrap + timedelta(minutes=30)
    scenes = [
        _scene("1", "1", [], setups=1),
        _scene("2", "6", [], setups=3),
    ]
    setups = [
        Setup(id="1-1", scene_number="1", description="setup", estimated_minutes=20),
        Setup(id="2-1", scene_number="2", description="setup", estimated_minutes=20),
        Setup(id="2-2", scene_number="2", description="setup", estimated_minutes=20),
        Setup(id="2-3", scene_number="2", description="setup", estimated_minutes=20),
    ]
    return ShootingDay(
        day_number=1,
        production_title="Test Day",
        shoot_date=general_call.date(),
        general_call=general_call,
        scheduled_wrap=scheduled_wrap,
        overtime_threshold=overtime_threshold,
        golden_hour_start=overtime_threshold - timedelta(minutes=15),
        meal_due_by=general_call + timedelta(hours=1),
        scenes=scenes,
        setups=setups,
        performers=[],
    )


def test_generate_scenario_is_deterministic():
    day = _day_with_scenes({"1": "4", "2": "4", "3": "6"}, setups_per_scene=2)

    first = generate_scenario(day)
    second = generate_scenario(day)

    assert first.scenario == second.scenario
    assert first.at_risk_reachable == second.at_risk_reachable


def test_generate_scenario_covers_every_setup():
    day = _day_with_scenes({"1": "4", "2": "6"}, setups_per_scene=2)

    result = generate_scenario(day)

    assert set(result.scenario.keys()) == {s.id for s in day.setups}
    assert all(t["actual_minutes"] > 0 and t["takes"] > 0 for t in result.scenario.values())


def test_generate_scenario_crosses_at_risk_on_a_tight_day():
    # scheduled_wrap is 2h after call, overtime_threshold only 30 more
    # minutes past that (error_budget_total = 30 min). Baseline timing
    # (4 setups, ~20 min each) finishes around the 80-minute mark --
    # comfortably inside the 2-hour scheduled length, consumed=0. Only
    # once scene "2"'s 3 setups (the longest scene, by page_eighths)
    # are inflated towards their cap does the day's total elapsed time
    # push past scheduled_wrap + 0.75 * 30min, crossing AT_RISK.
    day = _tight_day()

    result = generate_scenario(day)

    assert result.at_risk_reachable is True
    working = day.model_copy(deep=True)
    for setup in working.setups:
        timing = result.scenario[setup.id]
        setup.actual_minutes = timing["actual_minutes"]
        setup.takes = timing["takes"]
    elapsed = sum(t["actual_minutes"] for t in result.scenario.values())
    now = working.general_call + timedelta(minutes=elapsed)
    assert error_budget_consumed(working, now) >= AT_RISK_ERROR_BUDGET_CONSUMED

    # And it stayed within Correction 1's cap getting there.
    for setup in day.setups:
        if setup.scene_number == "2":
            timing = result.scenario[setup.id]
            assert timing["actual_minutes"] <= setup.estimated_minutes * 3
            assert timing["takes"] <= 15


def test_generate_scenario_reports_unreachable_on_a_generously_slacked_day():
    # A single tiny scene with a huge overtime buffer -- even inflated
    # to the cap (3x estimated_minutes, 15 takes), one small scene
    # cannot burn a day this generously budgeted past AT_RISK. Proves
    # the loop terminates on the cap rather than searching forever.
    scenes = [_scene("1", "1", [], setups=1)]
    day = build_shooting_day(scenes, [], day_number=1, shoot_date=date(2026, 9, 8), production_title="Test Day")
    day = day.model_copy(update={"overtime_threshold": day.overtime_threshold + timedelta(hours=48)})

    result = generate_scenario(day)

    assert result.at_risk_reachable is False
    timing = next(iter(result.scenario.values()))
    assert timing["actual_minutes"] <= _DEFAULT_SETUP_MINUTES_FOR_TEST * 3
    assert timing["takes"] <= 15


_DEFAULT_SETUP_MINUTES_FOR_TEST = 20
