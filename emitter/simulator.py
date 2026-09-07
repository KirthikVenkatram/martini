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

from emitter.models import PageEighths, Performer, Scene, ShootingDay, Setup
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

SCENE_EIGHTHS = {"1": 4, "2": 4, "3": 4, "4": 4, "5": 2, "5B": 1, "5C": 1, "42": 4, "42B": 4, "42C": 2}
SETUP_SCENES = {
    "1a": "1", "1b": "1",
    "2a": "2",
    "3a": "3", "3b": "3",
    "4a": "4",
    "5a": "5", "5b": "5B", "5c": "5C",
    "42a": "42", "42b": "42B", "42c": "42C",
    "42Da": RECOVERY_SCENE_NUMBER,
}

# Invented cast (no real people). PRIYA is the lead and only appears in
# the padding scene (43) -- the one scene with no fixed position in the
# shooting order, and so the one a reorder/pickup option is most likely
# to touch. Her previous_night_wrap is set close enough to this day's
# general call that any proposed call earlier than mid-morning breaches
# her 11-hour turnaround -- the gate rejection this demo is built
# around. JUNO is a minor whose ordinary 09:00 call already sits close
# to the 9-hour/19:00 wrap limit, so pushing her into an evening slot
# breaches it. ELENA's and DESMOND's previous_night_wrap are set to give
# them a comfortable turnaround margin (~76% of the required minimum
# used) -- PRIYA is the only performer this day's cast clocks read as
# tight against her limit, so the eventual rejection doesn't have to
# compete with two other performers who already looked just as close.
PRIYA = Performer(
    id="priya",
    name="Priya Osei",
    character_name="PRIYA",
    call_time=datetime(2026, 9, 3, 11, 0),
    previous_night_wrap=datetime(2026, 9, 2, 23, 30),
    minimum_turnaround_hours=11.0,
    is_minor=False,
)
MARCUS = Performer(
    id="marcus",
    name="Marcus Feld",
    character_name="MARCUS",
    call_time=datetime(2026, 9, 3, 7, 0),
    previous_night_wrap=datetime(2026, 9, 2, 19, 0),
    minimum_turnaround_hours=11.0,
    is_minor=False,
)
ELENA = Performer(
    id="elena",
    name="Elena Cho",
    character_name="ELENA",
    call_time=datetime(2026, 9, 3, 7, 30),
    previous_night_wrap=datetime(2026, 9, 2, 17, 0),
    minimum_turnaround_hours=11.0,
    is_minor=False,
)
DESMOND = Performer(
    id="desmond",
    name="Desmond Ruiz",
    character_name="DESMOND",
    call_time=datetime(2026, 9, 3, 8, 0),
    previous_night_wrap=datetime(2026, 9, 2, 17, 30),
    minimum_turnaround_hours=11.0,
    is_minor=False,
)
JUNO = Performer(
    id="juno",
    name="Juno Ahn",
    character_name="JUNO",
    call_time=datetime(2026, 9, 3, 9, 0),
    previous_night_wrap=datetime(2026, 9, 2, 20, 0),
    minimum_turnaround_hours=12.0,
    is_minor=True,
)
PERFORMERS = [PRIYA, MARCUS, ELENA, DESMOND, JUNO]

SCENE_CAST = {
    "1": ["marcus", "elena"],
    "2": ["marcus", "desmond"],
    "3": ["elena", "juno"],
    "4": ["desmond", "juno"],
    "5": ["marcus", "elena", "desmond"],
    "5B": ["marcus", "elena", "desmond"],
    "5C": ["marcus", "elena", "desmond"],
    "42": ["elena", "desmond"],
    "42B": ["marcus", "juno"],
    "42C": ["elena"],
    PADDING_SCENE_NUMBER: ["priya", "marcus"],
    RECOVERY_SCENE_NUMBER: ["elena", "desmond"],
}

# Invented story content -- an invented quarry-town drama, no real film,
# studio, or person. Spans a believable mix of all four strip colours
# (the strip board's core visual idea) rather than defaulting every
# scene to the same slot. Scene 43 (PADDING_SCENE_NUMBER) is PRIYA's
# only scene on this day and the one gate/rules/production_rules.yaml's
# turnaround rule ends up rejecting a reorder into -- it needs a real
# stake, not a placeholder, since it's what the rejection card argues
# over.
SCENE_CONTENT = {
    "1": ("MARCUS and ELENA argue over the household accounts before the crew arrives.", "INT", "DAY"),
    "2": ("MARCUS presses DESMOND for the truck keys he's been avoiding handing over.", "INT", "DAY"),
    "3": ("ELENA waits with JUNO at the crossing, dodging her questions about last night.", "EXT", "DAY"),
    "4": ("DESMOND warns JUNO off the quarry road before the blasting crew arrives.", "EXT", "DAY"),
    "5": ("The three of them corner each other in the site office over the missing ledger.", "INT", "NIGHT"),
    "5B": ("MARCUS slides the ledger across the desk and dares ELENA to explain the numbers.", "INT", "NIGHT"),
    "5C": ("DESMOND admits the missing pages were his doing, not ELENA's.", "INT", "NIGHT"),
    "42": ("ELENA and DESMOND finally say what's been unsaid at the reservoir's edge.", "EXT", "NIGHT"),
    "42B": ("MARCUS drives JUNO home in silence, the radio the only thing talking.", "INT", "NIGHT"),
    "42C": ("ELENA walks the reservoir path alone, turning the night over in her head.", "EXT", "NIGHT"),
    RECOVERY_SCENE_NUMBER: ("One last look back at the water before DESMOND cuts the engine.", "EXT", "NIGHT"),
    PADDING_SCENE_NUMBER: ("PRIYA returns to the quarry gate and tells MARCUS she's selling her share.", "EXT", "DAY"),
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

    scenes = []
    for number, eighths in scene_eighths.items():
        synopsis, int_ext, day_night = SCENE_CONTENT.get(number, (f"Scene {number}", "INT", "DAY"))
        scenes.append(
            Scene(
                number=number,
                synopsis=synopsis,
                page_eighths=PageEighths(eighths=eighths),
                int_ext=int_ext,
                day_night=day_night,
                location="Set",
                cast_ids=SCENE_CAST.get(number, []),
                estimated_setups=1,
            )
        )

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
        performers=PERFORMERS,
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
