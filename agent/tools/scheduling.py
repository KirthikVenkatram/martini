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

from agent.tools.breakdown import slugify_character_name
from emitter.models import Performer, Scene, ShootingDay, Setup
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
