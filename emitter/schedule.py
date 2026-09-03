from __future__ import annotations

from datetime import datetime, timedelta

from emitter.models import Performer, ShootingDay

_EPSILON = 1e-9


def error_budget_consumed(day: ShootingDay, now: datetime) -> float:
    """Fraction of the day's error budget consumed, clamped to [0.0, 1.0].

    The budget is the wall-clock window from general_call to
    overtime_threshold. "On pace" means the fraction of page eighths
    completed equals the fraction of that window elapsed — in that
    case this returns 1.0, meaning the day is on track to hit the
    overtime threshold exactly as the last page is shot.

    consumed = elapsed_fraction / max(progress_fraction, epsilon)

    Falling behind pace (progress_fraction < elapsed_fraction) pushes
    the ratio above 1.0, which clamps back down to 1.0 — this metric
    only signals "at or past the sustainable burn rate", it does not
    distinguish how far behind. Getting ahead of pace pulls the ratio
    below 1.0. At the very start of the day, with no elapsed time and
    no progress, this returns 0.0 rather than an indeterminate 0/0.
    """
    window = (day.overtime_threshold - day.general_call).total_seconds()
    elapsed = (now - day.general_call).total_seconds()
    elapsed_fraction = elapsed / window

    total = day.total_page_eighths.eighths
    completed = day.completed_page_eighths.eighths
    progress_fraction = completed / total if total else 0.0

    if elapsed_fraction <= 0.0:
        return 0.0

    consumed = elapsed_fraction / max(progress_fraction, _EPSILON)
    return max(0.0, min(consumed, 1.0))


def projected_wrap(day: ShootingDay, now: datetime) -> datetime:
    """Extrapolate a wrap time from the pace observed so far.

    Falls back to scheduled_wrap if nothing has been completed yet —
    there is no observed pace to extrapolate from.
    """
    completed = day.completed_page_eighths.eighths
    if completed <= 0:
        return day.scheduled_wrap

    elapsed = now - day.general_call
    remaining = day.remaining_page_eighths.eighths
    minutes_per_eighth = elapsed.total_seconds() / 60 / completed
    return now + timedelta(minutes=minutes_per_eighth * remaining)


def minutes_to_golden_hour(day: ShootingDay, now: datetime) -> int:
    """Minutes until golden_hour_start; negative once it has passed."""
    delta = day.golden_hour_start - now
    return int(delta.total_seconds() // 60)


def turnaround_violation(
    performer: Performer, proposed_call_time: datetime
) -> timedelta | None:
    """Shortfall if proposed_call_time violates the performer's minimum rest.

    Returns None when the rest between previous_night_wrap and
    proposed_call_time meets or exceeds minimum_turnaround_hours.
    """
    if performer.previous_night_wrap is None:
        return None

    required = timedelta(hours=performer.minimum_turnaround_hours)
    actual = proposed_call_time - performer.previous_night_wrap
    if actual >= required:
        return None
    return required - actual


def meal_penalty_due(day: ShootingDay, now: datetime, last_meal_break: datetime) -> bool:
    """Whether the crew is now overdue for a meal break.

    True once now has passed the day's meal_due_by and the crew has
    not broken for a meal since that deadline.
    """
    return now > day.meal_due_by and last_meal_break <= day.meal_due_by
