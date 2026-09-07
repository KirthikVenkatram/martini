"""Plain-English narration for the console (Module 6.2).

An AD reads a call sheet for answers, not telemetry: is the day making
it, what's left to shoot, what do they do about it. This module turns
emitter/schedule.py's raw numbers into the sentences that answer those
questions, once, in one place -- so server/app.py's idle snapshot and
server/replay.py's tick snapshots never each invent their own wording.

No new metrics live here. Every sentence is a translation of a number
emitter/schedule.py (or ShootingDay itself) already computes; this
module never re-derives schedule math of its own.
"""

from __future__ import annotations

from datetime import datetime

from emitter import schedule
from emitter.models import PageEighths, ShootingDay

CREW_SIZE = 42
"""Invented, realistic crew headcount for the cost-of-delay line -- not
a production input anywhere else in the domain model, just the number
that one sentence quotes to make overtime legible to someone who has
never been on a set."""


def cost_of_delay_sentence(day: ShootingDay) -> str:
    return (
        f"Every 30 minutes past {day.scheduled_wrap:%H:%M} costs the production "
        f"overtime on a {CREW_SIZE}-person crew."
    )


def idle_narration(day: ShootingDay) -> dict[str, str]:
    """Narration before the day has called -- no `now` to read a pace from yet."""
    return {
        "verdict_headline": "STANDING BY FOR CALL",
        "verdict_subline": f"General call {day.general_call:%H:%M} -- Day {day.day_number} hasn't started.",
        "budget_sentence": "Cushion is untouched -- the full overtime buffer is still there.",
        "burn_sentence": "No pace to report yet -- the day hasn't started.",
        "pages_sentence": f"{day.total_page_eighths} pages to shoot, {day.total_setups} setups planned.",
        "cost_of_delay_sentence": cost_of_delay_sentence(day),
    }


def _verdict_headline_and_subline(day: ShootingDay, now: datetime, status: str) -> tuple[str, str]:
    projected = schedule.projected_wrap(day, now)

    if status == "at_risk":
        headline = "THE DAY IS AT RISK"
    elif projected <= day.scheduled_wrap:
        headline = "MAKING THE DAY"
    else:
        minutes_behind = round((projected - day.scheduled_wrap).total_seconds() / 60)
        headline = f"RUNNING {minutes_behind} MINUTES BEHIND"

    if projected > day.overtime_threshold:
        overtime_minutes = round((projected - day.overtime_threshold).total_seconds() / 60)
        subline = f"Wrap projected {projected:%H:%M} -- {overtime_minutes} minutes into overtime."
    elif projected > day.scheduled_wrap:
        subline = f"Wrap projected {projected:%H:%M} -- inside the overtime buffer."
    else:
        ahead_minutes = round((day.scheduled_wrap - projected).total_seconds() / 60)
        if ahead_minutes > 0:
            subline = f"Wrap projected {projected:%H:%M} -- {ahead_minutes} minutes ahead of schedule."
        else:
            subline = f"Wrap projected {projected:%H:%M} -- on schedule."

    return headline, subline


def _budget_sentence(day: ShootingDay, now: datetime) -> str:
    percent = round(schedule.error_budget_consumed(day, now) * 100)
    if percent <= 0:
        return "Cushion is untouched -- the full overtime buffer is still there."

    remaining_minutes = round(schedule.error_budget_remaining(day, now).total_seconds() / 60)
    if remaining_minutes >= 0:
        return f"{percent}% of your cushion is gone -- about {remaining_minutes} minutes of slack left."
    return f"{percent}% of your cushion is gone -- you're already {abs(remaining_minutes)} minutes into overtime."


def _burn_sentence(burn_rate: float) -> str:
    if burn_rate > 1.05:
        return f"Right now you're losing about {burn_rate:.1f} minutes for every minute scheduled."
    if burn_rate < 0.95:
        return "Right now you're gaining time back -- clearing pages faster than scheduled."
    return "Right now you're holding pace."


def _pages_sentence(pages_remaining_eighths: int, setups_remaining: int) -> str:
    display = str(PageEighths(eighths=pages_remaining_eighths))
    return f"{display} pages still to shoot, {setups_remaining} setups left."


def tick_narration(
    day: ShootingDay,
    now: datetime,
    status: str,
    *,
    pages_remaining_eighths: int,
    setups_completed: int,
    setups_total: int,
    burn_rate: float,
) -> dict[str, str]:
    """Narration for a running/at-risk tick -- everything here reads
    `now` and the day's own schedule, never state the caller doesn't
    already have in scope."""
    headline, subline = _verdict_headline_and_subline(day, now, status)
    return {
        "verdict_headline": headline,
        "verdict_subline": subline,
        "budget_sentence": _budget_sentence(day, now),
        "burn_sentence": _burn_sentence(burn_rate),
        "pages_sentence": _pages_sentence(pages_remaining_eighths, setups_total - setups_completed),
        "cost_of_delay_sentence": cost_of_delay_sentence(day),
    }
