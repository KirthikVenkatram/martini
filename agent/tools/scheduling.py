"""Deterministic shooting-day construction (Module 7).

build_shooting_day never calls an LLM -- it turns a Gemini breakdown's
scenes and a cast form into the same ShootingDay every other part of
MARTINI already consumes (emitter/schedule.py, gate/checker.py, the
console). Turnaround defaults are read from
gate/rules/production_rules.yaml, the same file the gate itself checks
against, so a freshly-built day's displayed turnaround margin always
agrees with what the gate would later approve or reject.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from pydantic import BaseModel

from agent.root import AT_RISK_ERROR_BUDGET_CONSUMED
from agent.tools.breakdown import slugify_character_name
from emitter.models import Performer, Scene, ShootingDay, Setup
from emitter.schedule import error_budget_consumed
from gate.checker import load_rules

_GENERAL_CALL_TIME = time(7, 0)
_SCHEDULED_SHOOT_HOURS = 11
_OVERTIME_BUFFER_HOURS = 1
_GOLDEN_HOUR_LEAD_MINUTES = 30
_MEAL_DUE_AFTER_HOURS = 6
_DEFAULT_SETUP_MINUTES = 20


class CastEntry(BaseModel):
    character_name: str
    is_minor: bool = False
    previous_night_wrap: datetime
    minimum_turnaround_hours: float | None = None


def build_shooting_day(
    scenes: list[Scene],
    cast: list[CastEntry],
    day_number: int,
    shoot_date: date,
    production_title: str,
) -> ShootingDay:
    rules = load_rules()

    general_call = datetime.combine(shoot_date, _GENERAL_CALL_TIME)
    scheduled_wrap = general_call + timedelta(hours=_SCHEDULED_SHOOT_HOURS)
    overtime_threshold = scheduled_wrap + timedelta(hours=_OVERTIME_BUFFER_HOURS)
    golden_hour_start = overtime_threshold - timedelta(minutes=_GOLDEN_HOUR_LEAD_MINUTES)
    meal_due_by = general_call + timedelta(hours=_MEAL_DUE_AFTER_HOURS)

    setups: list[Setup] = []
    for scene in scenes:
        setup_count = max(1, scene.estimated_setups)
        for i in range(setup_count):
            setups.append(
                Setup(
                    id=f"{scene.number}-{i + 1}",
                    scene_number=scene.number,
                    description=f"Sc.{scene.number} setup {i + 1}",
                    estimated_minutes=_DEFAULT_SETUP_MINUTES,
                )
            )

    performers = [
        Performer(
            id=slugify_character_name(entry.character_name),
            name=entry.character_name.title(),
            character_name=entry.character_name.upper(),
            call_time=general_call,
            previous_night_wrap=entry.previous_night_wrap,
            minimum_turnaround_hours=(
                entry.minimum_turnaround_hours
                if entry.minimum_turnaround_hours is not None
                else (rules.turnaround.minor_minimum_hours if entry.is_minor else rules.turnaround.minimum_hours)
            ),
            is_minor=entry.is_minor,
        )
        for entry in cast
    ]

    return ShootingDay(
        day_number=day_number,
        production_title=production_title,
        shoot_date=shoot_date,
        general_call=general_call,
        scheduled_wrap=scheduled_wrap,
        overtime_threshold=overtime_threshold,
        golden_hour_start=golden_hour_start,
        meal_due_by=meal_due_by,
        scenes=scenes,
        setups=setups,
        performers=performers,
    )


_JITTER_PATTERN = [0, 2, -1, 3, -2, 1]
_BASE_TAKES = 2
_INFLATION_STEP_MINUTES = 2
_MAX_INFLATION_MULTIPLIER = 3.0
_MAX_TAKES = 15


class ScenarioResult(BaseModel):
    scenario: dict[str, dict[str, int]]
    at_risk_reachable: bool


def _elapsed_minutes(scenario: dict[str, dict[str, int]]) -> int:
    return sum(timing["actual_minutes"] for timing in scenario.values())


def _consumed_with_scenario(day: ShootingDay, scenario: dict[str, dict[str, int]]) -> float:
    working = day.model_copy(deep=True)
    for setup in working.setups:
        timing = scenario[setup.id]
        setup.actual_minutes = timing["actual_minutes"]
        setup.takes = timing["takes"]
    now = working.general_call + timedelta(minutes=_elapsed_minutes(scenario))
    return error_budget_consumed(working, now)


def generate_scenario(day: ShootingDay) -> ScenarioResult:
    """Deterministic per-setup actual_minutes/takes for replay_day.

    Nothing in a screenplay breakdown says how long a setup actually
    took -- something has to invent it. Every setup gets a fixed,
    reproducible jitter around its own estimate; the day's single
    longest scene (by page count) then has its setups' takes/minutes
    inflated, capped at 3x estimated_minutes and 15 takes per setup, up
    to the point error_budget_consumed crosses AT_RISK_ERROR_BUDGET_CONSUMED
    -- so the SLIP -> REPLAN -> GATE cycle fires on the user's own day,
    not only Day 14's canned scenario.

    Bounded, not a search: the inflation loop only ever moves every
    target setup towards its cap and stops the moment nothing moved,
    so a day with enough error budget that no reachable inflation
    would cross AT_RISK terminates with at_risk_reachable=False rather
    than looping.
    """
    scenario: dict[str, dict[str, int]] = {
        setup.id: {
            "actual_minutes": max(1, setup.estimated_minutes + _JITTER_PATTERN[i % len(_JITTER_PATTERN)]),
            "takes": _BASE_TAKES,
        }
        for i, setup in enumerate(day.setups)
    }

    if not day.scenes:
        return ScenarioResult(scenario=scenario, at_risk_reachable=False)

    longest_scene = max(day.scenes, key=lambda scene: scene.page_eighths.eighths)
    target_setups = [s for s in day.setups if s.scene_number == longest_scene.number]

    at_risk_reachable = _consumed_with_scenario(day, scenario) >= AT_RISK_ERROR_BUDGET_CONSUMED

    while target_setups and not at_risk_reachable:
        moved = False
        for setup in target_setups:
            timing = scenario[setup.id]
            cap_minutes = round(setup.estimated_minutes * _MAX_INFLATION_MULTIPLIER)
            if timing["actual_minutes"] < cap_minutes:
                timing["actual_minutes"] = min(timing["actual_minutes"] + _INFLATION_STEP_MINUTES, cap_minutes)
                moved = True
            if timing["takes"] < _MAX_TAKES:
                timing["takes"] += 1
                moved = True

        if _consumed_with_scenario(day, scenario) >= AT_RISK_ERROR_BUDGET_CONSUMED:
            at_risk_reachable = True
            break
        if not moved:
            break

    return ScenarioResult(scenario=scenario, at_risk_reachable=at_risk_reachable)
