"""Replays a shooting day as OTel metrics/logs from a scenario yaml.

Module 1b (the Gemini script breakdown -> data/day_14.json) hasn't run
yet, so the scene/setup structure below is invented for this demo --
only each setup's actual_minutes/takes come from the committed
scenario yaml in emitter/scenarios/. Kept in sync with the equivalent
fixture in tests/test_schedule.py.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

import yaml

from emitter.models import PageEighths, Scene, ShootingDay, Setup
from emitter.otel import Instruments

SCENARIOS_DIR = Path(__file__).parent / "scenarios"

GENERAL_CALL = datetime(2026, 9, 3, 7, 0)
SCHEDULED_WRAP = datetime(2026, 9, 3, 18, 0)
OVERTIME_THRESHOLD = datetime(2026, 9, 3, 19, 0)
GOLDEN_HOUR_START = datetime(2026, 9, 3, 18, 30)
MEAL_DUE_BY = datetime(2026, 9, 3, 13, 0)
MEAL_BREAK_MINUTES = 30

TOTAL_PAGE_EIGHTHS = 52
PADDING_SCENE_NUMBER = "43"
RECOVERY_SCENE_NUMBER = "42D"
RECOVERY_SCENE_EIGHTHS = 5

SCENE_EIGHTHS = {"1": 4, "2": 4, "3": 4, "4": 4, "5": 4, "42": 4, "42B": 4, "42C": 2}
SETUP_SCENES = {
    "1a": "1", "1b": "1",
    "2a": "2",
    "3a": "3", "3b": "3",
    "4a": "4",
    "5a": "5", "5b": "5", "5c": "5",
    "42a": "42", "42b": "42B", "42c": "42C",
    "42Da": RECOVERY_SCENE_NUMBER,
}


def load_scenario(name: str) -> dict[str, dict]:
    with open(SCENARIOS_DIR / f"{name}.yaml") as f:
        return yaml.safe_load(f)["setups"]


def build_day(scenario_name: str) -> ShootingDay:
    """Build the invented Day 14 shooting day plan for a named scenario.

    All setups start un-shot (actual_minutes=None) -- replay_day fills
    them in as it walks the scenario. estimated_minutes always comes
    from the nominal scenario (the plan), even when replaying slipping,
    so a slip actually reads as one against the schedule.
    """
    scenario_setups = load_scenario(scenario_name)
    nominal_setups = scenario_setups if scenario_name == "nominal" else load_scenario("nominal")

    present_scenes = {SETUP_SCENES[setup_id] for setup_id in scenario_setups}
    scene_eighths = dict(SCENE_EIGHTHS)
    if RECOVERY_SCENE_NUMBER in present_scenes:
        scene_eighths[RECOVERY_SCENE_NUMBER] = RECOVERY_SCENE_EIGHTHS
    scene_eighths[PADDING_SCENE_NUMBER] = TOTAL_PAGE_EIGHTHS - sum(scene_eighths.values())

    scenes = [
        Scene(
            number=number,
            synopsis=f"Scene {number}",
            page_eighths=PageEighths(eighths=eighths),
            int_ext="INT",
            day_night="DAY",
            location="Set",
            cast_ids=[],
            estimated_setups=1,
        )
        for number, eighths in scene_eighths.items()
    ]

    setups = [
        Setup(
            id=setup_id,
            scene_number=SETUP_SCENES[setup_id],
            description="setup",
            estimated_minutes=nominal_setups.get(setup_id, timing)["actual_minutes"],
        )
        for setup_id, timing in scenario_setups.items()
    ]

    return ShootingDay(
        day_number=14,
        production_title="Invented Production",
        shoot_date=GENERAL_CALL.date(),
        general_call=GENERAL_CALL,
        scheduled_wrap=SCHEDULED_WRAP,
        overtime_threshold=OVERTIME_THRESHOLD,
        golden_hour_start=GOLDEN_HOUR_START,
        meal_due_by=MEAL_DUE_BY,
        scenes=scenes,
        setups=setups,
        performers=[],
    )


def _snapshot(day: ShootingDay, now: datetime, event_type: str, **extra: object) -> dict:
    return {
        "type": event_type,
        "now": now,
        "pages_completed_eighths": day.completed_page_eighths.eighths,
        "pages_remaining_eighths": day.remaining_page_eighths.eighths,
        "setups_completed": day.completed_setups,
        "setups_total": day.total_setups,
        **extra,
    }


def replay_day(
    day: ShootingDay,
    scenario: dict[str, dict],
    speed_factor: float = 480,
    on_event: Callable[[dict], None] | None = None,
    dry_run: bool = False,
) -> None:
    """Walk day.setups in order, applying scenario timings.

    day.setups is assumed already in the order setups are actually
    shot. The virtual clock (now) is the only notion of time used here
    -- wall-clock sleeps only pace how fast it's replayed, they never
    feed back into day state. speed_factor compresses that pacing: 480
    means a 12-hour day replays in about 90 real seconds.
    """
    instruments = Instruments(day, dry_run=dry_run)
    scenes_by_number = {scene.number: scene for scene in day.scenes}
    setups_by_scene: dict[str, list[Setup]] = {}
    for setup in day.setups:
        setups_by_scene.setdefault(setup.scene_number, []).append(setup)

    def emit(event_type: str, **extra: object) -> None:
        instruments.flush()
        if on_event is not None:
            on_event(_snapshot(day, instruments.now, event_type, **extra))

    now = day.general_call
    instruments.advance(now)
    instruments.log_event("Day 14 - general call.")
    emit("day_start")

    meal_taken = False

    for setup_id, timing in scenario.items():
        setup = next(s for s in day.setups if s.id == setup_id)
        scene_number = setup.scene_number

        time.sleep((timing["actual_minutes"] * 60) / speed_factor)
        now = now + timedelta(minutes=timing["actual_minutes"])
        setup.actual_minutes = timing["actual_minutes"]
        setup.takes = timing["takes"]
        instruments.advance(now)

        instruments.record_takes(scene_number, setup.takes)
        instruments.record_setup_wrapped(scene_number)
        instruments.log_event(
            f"Sc.{scene_number} setup {setup.id} wrapped - {setup.takes} takes",
            scene=scene_number,
            setup=setup.id,
        )
        emit("setup_wrapped", scene=scene_number, setup=setup.id)

        if all(s.is_complete for s in setups_by_scene[scene_number]):
            scene = scenes_by_number[scene_number]
            instruments.log_event(
                f"Sc.{scene_number} wrapped - {scene.page_eighths} pages", scene=scene_number
            )
            emit("scene_wrapped", scene=scene_number)

        if not meal_taken and now > day.meal_due_by:
            meal_taken = True
            now = now + timedelta(minutes=MEAL_BREAK_MINUTES)
            instruments.advance(now)
            instruments.log_event("Meal break - crew breaks for lunch.")
            emit("meal_break")

    instruments.flush()
    instruments.shutdown()
