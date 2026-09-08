from __future__ import annotations

from datetime import date, datetime

import pytest

from agent.subagents.planner import MonitoringPlan
from agent.tools.scheduling import CastEntry, build_shooting_day
from emitter.models import PageEighths, Scene
from server.projects import storage


@pytest.fixture(autouse=True)
def _isolated_data_root(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "data_root", lambda: tmp_path / "projects")
    yield


def _scene() -> Scene:
    return Scene(
        number="1",
        synopsis="A.",
        page_eighths=PageEighths.from_string("1"),
        int_ext="INT",
        day_night="DAY",
        location="Set",
        cast_ids=[],
        estimated_setups=1,
    )


def test_slugify_title_is_url_safe_and_lowercase():
    assert storage.slugify_title("The Quarry, Part Two!") == "the-quarry-part-two"


def test_create_project_round_trips():
    record = storage.create_project(title="The Quarry", total_days=12, crew_size=40)

    loaded = storage.load_project(record.slug)

    assert loaded.title == "The Quarry"
    assert loaded.total_days == 12
    assert loaded.crew_size == 40


def test_load_project_raises_a_named_error_when_missing():
    with pytest.raises(storage.ProjectNotFoundError):
        storage.load_project("does-not-exist")


def test_list_projects_returns_every_created_project():
    storage.create_project(title="Alpha", total_days=1, crew_size=1)
    storage.create_project(title="Beta", total_days=1, crew_size=1)

    titles = {p.title for p in storage.list_projects()}

    assert titles == {"Alpha", "Beta"}


def test_scenes_round_trip_and_are_none_before_saving():
    record = storage.create_project(title="The Quarry", total_days=1, crew_size=1)

    assert storage.load_scenes(record.slug) is None

    storage.save_scenes(record.slug, [_scene()])

    loaded = storage.load_scenes(record.slug)
    assert loaded is not None
    assert loaded[0].number == "1"


def test_cast_round_trips():
    record = storage.create_project(title="The Quarry", total_days=1, crew_size=1)
    cast = [CastEntry(character_name="MARCUS", previous_night_wrap=datetime(2026, 9, 2, 20, 0))]

    storage.save_cast(record.slug, cast)

    loaded = storage.load_cast(record.slug)
    assert loaded is not None
    assert loaded[0].character_name == "MARCUS"


def test_day_round_trips():
    record = storage.create_project(title="The Quarry", total_days=1, crew_size=1)
    day = build_shooting_day([_scene()], [], day_number=1, shoot_date=date(2026, 9, 8), production_title="The Quarry")

    storage.save_day(record.slug, day)

    loaded = storage.load_day(record.slug)
    assert loaded is not None
    assert loaded.production_title == "The Quarry"
    assert loaded.day_number == 1


def test_provisioning_plan_round_trips_and_is_none_before_saving():
    record = storage.create_project(title="The Quarry", total_days=1, crew_size=1)

    assert storage.load_provisioning_plan(record.slug) is None

    plan = MonitoringPlan(burn_rate_threshold=1.4, evaluation_window_minutes=10, annotation="Watch it.")
    storage.save_provisioning_plan(record.slug, plan)

    loaded = storage.load_provisioning_plan(record.slug)
    assert loaded is not None
    assert loaded.burn_rate_threshold == 1.4
