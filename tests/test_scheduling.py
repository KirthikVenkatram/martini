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
