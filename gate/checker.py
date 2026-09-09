"""Deterministic legality gate for shooting-day recovery options (Module 5).

check(day, option) decides whether one RecoveryOption is legal against
gate/rules/production_rules.yaml -- turnaround, meal, minor, and
crew-rest rules, loaded as data so a production coordinator could edit
a threshold without a redeploy. This module never calls an LLM: the
replanner (agent/subagents/replanner.py) proposes options, this module
disposes of them. It reuses emitter/schedule.py's turnaround_violation
and meal_penalty_due rather than reimplementing that maths -- the only
new logic here is which threshold applies to whom, and turning the
result into a plain-English reason.

crew_rest governs rest between shooting days (wrap on one day to call
on the next). A RecoveryOption only ever reschedules performers within
the *current* day (ShootingDay has no next-day call time to compare
against), so the rule is loaded and validated like the other three but
has no path that can trigger it yet.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel

from emitter.models import Performer, ShootingDay
from emitter.schedule import meal_penalty_due, turnaround_violation

_RULES_PATH = Path(__file__).parent / "rules" / "production_rules.yaml"


class TurnaroundRule(BaseModel):
    minimum_hours: float
    minor_minimum_hours: float
    description: str


class MealRule(BaseModel):
    max_hours_between_breaks: float
    penalty_per_half_hour: bool
    description: str


class MinorsRule(BaseModel):
    max_working_hours: float
    must_wrap_by: str
    description: str


class CrewRestRule(BaseModel):
    minimum_hours_between_days: float
    description: str


class ProductionRules(BaseModel):
    turnaround: TurnaroundRule
    meal: MealRule
    minors: MinorsRule
    crew_rest: CrewRestRule


def load_rules() -> ProductionRules:
    """Loads production_rules.yaml fresh on every call.

    Not cached -- a coordinator editing the yaml should see the new
    threshold on the next check, not need to restart anything.
    """
    with open(_RULES_PATH) as f:
        return ProductionRules.model_validate(yaml.safe_load(f))


RecoveryOptionKind = Literal["reorder", "drop_coverage", "move_to_pickups", "flip_to_cover_set"]
ViolationRule = Literal["turnaround", "meal", "minors", "crew_rest"]


class RecoveryOption(BaseModel):
    id: str
    kind: RecoveryOptionKind
    description: str
    affected_scenes: list[str]
    minutes_recovered: int
    proposed_call_times: dict[str, datetime] | None = None


class Violation(BaseModel):
    rule: ViolationRule
    # Holds the performer's character name, not their internal id --
    # this is what explain.py and every downstream caller actually
    # needs to build a human-readable sentence, and checker.py is the
    # only place that still has `day` in scope to resolve one from the
    # other.
    performer_id: str | None = None
    shortfall: timedelta | None = None
    reason: str


class GateVerdict(BaseModel):
    option_id: str
    approved: bool
    violations: list[Violation]
    projected_recovery: timedelta


def _performer_by_id(day: ShootingDay, performer_id: str) -> Performer:
    for performer in day.performers:
        if performer.id == performer_id:
            return performer
    raise ValueError(f"no performer {performer_id!r} on day {day.day_number}")


def _format_timedelta(delta: timedelta) -> str:
    total_minutes = round(delta.total_seconds() / 60)
    hours, minutes = divmod(total_minutes, 60)
    if hours and minutes:
        return f"{hours} hour{'s' if hours != 1 else ''} {minutes} minutes"
    if hours:
        return f"{hours} hour{'s' if hours != 1 else ''}"
    return f"{minutes} minutes"


def _format_hours(hours: float) -> str:
    return _format_timedelta(timedelta(hours=hours))


def _format_clock(moment: datetime, *, on_pickup_day: bool) -> str:
    """A bare HH:MM reads as later-today. The replanner is instructed
    (prompts/replanner.md) to never write a date other than the shoot
    date -- it has no other day's calendar to draw from -- so a
    move_to_pickups option's call times land on that same date even
    though they mean a different, future day. Going by option.kind
    rather than comparing dates is what actually catches that case;
    comparing moment.date() to day.shoot_date never would."""
    clock = f"{moment:%H:%M}"
    if on_pickup_day:
        return f"{clock} on the pickup day"
    return clock


def _check_turnaround(day: ShootingDay, option: RecoveryOption, rules: ProductionRules) -> list[Violation]:
    violations = []
    for performer_id, proposed_call_time in (option.proposed_call_times or {}).items():
        performer = _performer_by_id(day, performer_id)
        required_hours = (
            rules.turnaround.minor_minimum_hours if performer.is_minor else rules.turnaround.minimum_hours
        )
        governed_performer = performer.model_copy(update={"minimum_turnaround_hours": required_hours})
        shortfall = turnaround_violation(governed_performer, proposed_call_time)
        if shortfall is None:
            continue

        given = timedelta(hours=required_hours) - shortfall
        reason = rules.turnaround.description.format(
            name=performer.character_name,
            shortfall=_format_timedelta(shortfall),
            required=_format_hours(required_hours),
            given=_format_timedelta(given),
        )
        violations.append(
            Violation(
                rule="turnaround",
                performer_id=performer.character_name,
                shortfall=shortfall,
                reason=reason,
            )
        )
    return violations


def _check_meal(day: ShootingDay, option: RecoveryOption, rules: ProductionRules) -> list[Violation]:
    if not option.proposed_call_times:
        return []

    latest = max(option.proposed_call_times.values())
    if not meal_penalty_due(day, latest, day.general_call):
        return []

    reason = rules.meal.description.format(
        meal_due_by=f"{day.meal_due_by:%H:%M}",
        latest=_format_clock(latest, on_pickup_day=option.kind == "move_to_pickups"),
    )
    return [Violation(rule="meal", performer_id=None, shortfall=latest - day.meal_due_by, reason=reason)]


def _check_minors(day: ShootingDay, option: RecoveryOption, rules: ProductionRules) -> list[Violation]:
    violations = []
    must_wrap_by = datetime.combine(day.shoot_date, time.fromisoformat(rules.minors.must_wrap_by))

    for performer_id, proposed_call_time in (option.proposed_call_times or {}).items():
        performer = _performer_by_id(day, performer_id)
        if not performer.is_minor:
            continue

        projected_wrap = proposed_call_time + timedelta(hours=rules.minors.max_working_hours)
        if projected_wrap <= must_wrap_by:
            continue

        shortfall = projected_wrap - must_wrap_by
        reason = rules.minors.description.format(
            name=performer.character_name,
            must_wrap_by=rules.minors.must_wrap_by,
            projected_wrap=_format_clock(projected_wrap, on_pickup_day=option.kind == "move_to_pickups"),
            shortfall=_format_timedelta(shortfall),
        )
        violations.append(
            Violation(rule="minors", performer_id=performer.character_name, shortfall=shortfall, reason=reason)
        )
    return violations


def _check_crew_rest(day: ShootingDay, option: RecoveryOption, rules: ProductionRules) -> list[Violation]:
    return []


def check(day: ShootingDay, option: RecoveryOption) -> GateVerdict:
    """Checks one RecoveryOption against production_rules.yaml.

    Pure and deterministic: never calls an LLM, never touches the
    network. Approved iff none of the four rule checks raise a
    violation.
    """
    rules = load_rules()
    violations = [
        *_check_turnaround(day, option, rules),
        *_check_meal(day, option, rules),
        *_check_minors(day, option, rules),
        *_check_crew_rest(day, option, rules),
    ]
    return GateVerdict(
        option_id=option.id,
        approved=not violations,
        violations=violations,
        projected_recovery=timedelta(minutes=option.minutes_recovered),
    )
