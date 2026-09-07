"""Derived, presentation-ready fields for the console's three inline-SVG
visuals (Module 6.3): the day timeline, the pace line, and the cast
clocks. Each function here turns emitter/schedule.py's raw numbers (or
the gate's own turnaround rule) into fields the React components can
render directly -- fractions, labels, booleans -- so no component has
to do date math or domain reasoning of its own.
"""

from __future__ import annotations

from datetime import datetime

from emitter import schedule
from emitter.models import ShootingDay
from gate.checker import load_rules
from server.state import CastClockSnapshot, PaceSnapshot, TimelineSnapshot

TURNAROUND_TIGHT_FRACTION = 0.95
"""Rest given as a fraction of the required minimum, at or above which a
cast clock renders as tight (burn-colored)."""

PACE_BEHIND_GAP_FRACTION = 0.02
"""Minimum gap between needed and actual cumulative pages, as a fraction
of the day's total pages, before the pace line calls it "behind" rather
than noise -- same reasoning as schedule.MIN_PROGRESS_FOR_HIGH_WATER,
which this also reuses to ignore early, still-unreliable readings."""


def timeline_snapshot(day: ShootingDay, now: datetime) -> TimelineSnapshot:
    """Call time to the overtime threshold, as fractions of that domain."""
    domain_start = day.general_call
    domain_end = day.overtime_threshold
    domain_minutes = (domain_end - domain_start).total_seconds() / 60

    def fraction(at: datetime, *, clamp_above_one: bool = True) -> float:
        value = (at - domain_start).total_seconds() / 60 / domain_minutes
        value = max(0.0, value)
        return min(1.0, value) if clamp_above_one else value

    projected = schedule.projected_wrap(day, now)
    return TimelineSnapshot(
        call_label=f"{domain_start:%H:%M}",
        overtime_label=f"{domain_end:%H:%M}",
        elapsed_fraction=fraction(now),
        meal_fraction=fraction(day.meal_due_by),
        golden_hour_fraction=fraction(day.golden_hour_start),
        projected_wrap_fraction=fraction(projected, clamp_above_one=False),
        projected_wrap_label=f"Projected wrap {projected:%H:%M}",
    )


def pace_snapshot(day: ShootingDay, now: datetime) -> PaceSnapshot:
    """Cumulative actual pace vs. the pace the day needed, normalized so
    the "needed" line is always the diagonal from (0, 0) to (1, 1)."""
    total_scheduled_minutes = (day.scheduled_wrap - day.general_call).total_seconds() / 60
    total_eighths = day.total_page_eighths.eighths
    rate = schedule.required_page_eighths_rate(day)

    def point(elapsed_minutes: float, completed: int) -> tuple[float, float]:
        x = elapsed_minutes / total_scheduled_minutes
        y = completed / total_eighths if total_eighths else 0.0
        return (x, y)

    points: list[tuple[float, float]] = [(0.0, 0.0)]
    behind_label: str | None = None
    for scene_number, elapsed, cumulative in schedule.scene_wrap_trace(day):
        elapsed_minutes = elapsed.total_seconds() / 60
        points.append(point(elapsed_minutes, cumulative))

        if behind_label is None and total_eighths and cumulative / total_eighths >= schedule.MIN_PROGRESS_FOR_HIGH_WATER:
            gap = rate * elapsed_minutes - cumulative
            if gap >= total_eighths * PACE_BEHIND_GAP_FRACTION:
                behind_label = f"Fell behind at Sc.{scene_number}"

    now_point = point((now - day.general_call).total_seconds() / 60, day.completed_page_eighths.eighths)
    if points[-1] != now_point:
        points.append(now_point)

    return PaceSnapshot(actual_points=points, behind_label=behind_label)


def cast_clock_snapshots(day: ShootingDay, now: datetime) -> list[CastClockSnapshot]:
    """One clock per performer on the day, ordered as ShootingDay lists
    them. turnaround_fraction reuses gate/rules/production_rules.yaml
    (via gate.checker.load_rules) rather than each Performer's own
    minimum_turnaround_hours default, so this never drifts from what the
    gate itself would rule on the same performer."""
    rules = load_rules()
    snapshots = []
    for performer in day.performers:
        required_hours = (
            rules.turnaround.minor_minimum_hours if performer.is_minor else rules.turnaround.minimum_hours
        )
        turnaround_fraction = 0.0
        if performer.previous_night_wrap is not None:
            given_hours = (performer.call_time - performer.previous_night_wrap).total_seconds() / 3600
            turnaround_fraction = min(1.0, required_hours / given_hours) if given_hours > 0 else 1.0

        hours_worked = max(0.0, (now - performer.call_time).total_seconds() / 3600)
        snapshots.append(
            CastClockSnapshot(
                character_name=performer.character_name,
                hours_worked=round(hours_worked, 1),
                turnaround_fraction=round(turnaround_fraction, 3),
                is_tight=turnaround_fraction >= TURNAROUND_TIGHT_FRACTION,
            )
        )
    return snapshots
