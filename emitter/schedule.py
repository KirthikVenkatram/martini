from __future__ import annotations

from datetime import datetime, timedelta

from emitter.models import Performer, ShootingDay

MIN_PROGRESS_FOR_HIGH_WATER = 0.20
"""Fraction of total_page_eighths that must be complete before a pace
reading is trusted enough to ratchet error_budget_consumed's high-water
mark. Early in the day, a handful of completed eighths extrapolated
across nearly the whole remaining script is numerically unstable — a
single slightly-slow scene can project a wrap far past the overtime
threshold on almost no evidence. Since the high-water mark never comes
back down, letting an unstable early reading into it would pin
consumed near 1.0 for the rest of the day on noise, not a real slip.
Below this threshold, error_budget_consumed reports the plain
instantaneous reading instead of ratcheting."""


def _scene_wrap_elapsed(day: ShootingDay) -> dict[str, timedelta]:
    """Elapsed time (since general_call) at which each fully-shot scene wrapped.

    Assumes day.setups lists setups in the order they are actually shot
    (a single-camera day proceeds through its setups in order). Walks
    that order accumulating actual_minutes, and stops at the first
    setup with no actual_minutes — nothing after it has happened yet.
    A scene only gets a wrap time once every one of its setups has an
    elapsed time, i.e. it is fully shot.
    """
    cumulative = timedelta()
    setup_elapsed: dict[str, timedelta] = {}
    for setup in day.setups:
        if setup.actual_minutes is None:
            break
        cumulative += timedelta(minutes=setup.actual_minutes)
        setup_elapsed[setup.id] = cumulative

    setup_ids_by_scene: dict[str, list[str]] = {}
    for setup in day.setups:
        setup_ids_by_scene.setdefault(setup.scene_number, []).append(setup.id)

    wrap_elapsed: dict[str, timedelta] = {}
    for scene in day.scenes:
        ids = setup_ids_by_scene.get(scene.number, [])
        if ids and all(setup_id in setup_elapsed for setup_id in ids):
            wrap_elapsed[scene.number] = max(setup_elapsed[setup_id] for setup_id in ids)
    return wrap_elapsed


def _eighths_wrapped_in_window(
    day: ShootingDay, window_start: timedelta, window_end: timedelta
) -> int:
    """Page eighths whose scene wrapped in (window_start, window_end]."""
    wrap_elapsed = _scene_wrap_elapsed(day)
    total = 0
    for scene in day.scenes:
        wrapped_at = wrap_elapsed.get(scene.number)
        if wrapped_at is not None and window_start < wrapped_at <= window_end:
            total += scene.page_eighths.eighths
    return total


def burn_rate(day: ShootingDay, now: datetime, window_minutes: int = 60) -> float:
    """Pace over the trailing window, not the whole day.

    Compares the page eighths actually wrapped in the trailing
    window_minutes ending at now against the eighths that should have
    wrapped in a window that size at the day's required pace
    (total_page_eighths / scheduled day length). The ratio is inverted
    so that 1.0 means on pace, >1.0 means burning budget faster than
    sustainable (little wrapped for the time spent), and <1.0 means
    recovering (more wrapped than the sustainable rate demands).

    Unlike error_budget_consumed, this only looks at recent pace — it
    can spike during a bad scene and recover once the crew catches up,
    independent of how the cumulative, whole-day budget is doing.

    If nothing wrapped in the trailing window, steps back a further
    window and tries again, repeating until a window has progress to
    measure or the walk runs off the start of the day, in which case
    this returns 1.0 (no history yet to call it anything else).
    """
    window = timedelta(minutes=window_minutes)
    total_scheduled_minutes = (day.scheduled_wrap - day.general_call).total_seconds() / 60
    required_rate = day.total_page_eighths.eighths / total_scheduled_minutes
    required_in_window = required_rate * window_minutes

    window_end = now - day.general_call
    while window_end > timedelta():
        window_start = window_end - window
        observed = _eighths_wrapped_in_window(day, window_start, window_end)
        if observed > 0:
            return required_in_window / observed
        window_end = window_start

    return 1.0


def _projected_wrap_from_pace(day: ShootingDay, elapsed: timedelta, completed_eighths: int) -> datetime:
    """Extrapolate a wrap time from an arbitrary (elapsed, completed) pace snapshot.

    Shared by projected_wrap (which uses the day's current elapsed/
    completed) and error_budget_consumed's high-water walk (which
    replays this same extrapolation at each earlier point in the day).
    Falls back to scheduled_wrap if nothing had been completed yet at
    that snapshot — there is no observed pace to extrapolate from.
    """
    if completed_eighths <= 0:
        return day.scheduled_wrap

    remaining = day.total_page_eighths.eighths - completed_eighths
    minutes_per_eighth = elapsed.total_seconds() / 60 / completed_eighths
    return day.general_call + elapsed + timedelta(minutes=minutes_per_eighth * remaining)


def projected_wrap(day: ShootingDay, now: datetime) -> datetime:
    """Extrapolate a wrap time from the pace observed so far.

    Falls back to scheduled_wrap if nothing has been completed yet —
    there is no observed pace to extrapolate from. This is the current
    forecast: unlike error_budget_consumed, it moves both ways — a
    recovered pace projects an earlier wrap, same as a slowed pace
    projects a later one.
    """
    return _projected_wrap_from_pace(day, now - day.general_call, day.completed_page_eighths.eighths)


def error_budget_total(day: ShootingDay) -> timedelta:
    """The day's error budget: the overtime buffer past the scheduled wrap."""
    return day.overtime_threshold - day.scheduled_wrap


def schedule_slippage(day: ShootingDay, now: datetime) -> timedelta:
    """How far behind plan the day is, projected from pace observed so far.

    Negative means the day is projected to wrap ahead of schedule.
    """
    return projected_wrap(day, now) - day.scheduled_wrap


def _completed_eighths_trace(day: ShootingDay) -> list[tuple[timedelta, int]]:
    """(elapsed since general_call, cumulative completed page eighths) at each scene wrap, in order."""
    wrap_elapsed = _scene_wrap_elapsed(day)
    eighths_by_scene = {scene.number: scene.page_eighths.eighths for scene in day.scenes}
    ordered = sorted(wrap_elapsed.items(), key=lambda item: item[1])

    trace: list[tuple[timedelta, int]] = []
    cumulative = 0
    for scene_number, elapsed in ordered:
        cumulative += eighths_by_scene[scene_number]
        trace.append((elapsed, cumulative))
    return trace


def _instantaneous_consumed(day: ShootingDay, elapsed: timedelta, completed_eighths: int) -> float:
    projected = _projected_wrap_from_pace(day, elapsed, completed_eighths)
    consumed = (projected - day.scheduled_wrap) / error_budget_total(day)
    return max(0.0, min(consumed, 1.0))


def error_budget_consumed(day: ShootingDay, now: datetime) -> float:
    """High-water mark of the day's error budget consumed, clamped to [0.0, 1.0].

    A schedule slip is spent time — once the day has fallen behind, that
    slack is spent for good. Recovering pace slows further burn (see
    burn_rate) and improves the forecast (see projected_recovery), but
    it does not refund budget already used. So this isn't the
    instantaneous projection at now — it's the worst instantaneous
    projection seen at any point up to now, evaluated at now and at
    every scene wrap along the way. Monotonically non-decreasing by
    construction: each additional wrap (or now itself) can only add
    another candidate to the max, never remove one.

    Readings from before MIN_PROGRESS_FOR_HIGH_WATER of the day's pages
    were done are excluded from that history — too little evidence to
    trust ratcheting on. If now itself falls below that threshold,
    there's no trustworthy history to ratchet at all, so this just
    reports the plain instantaneous reading at now.
    """
    total = day.total_page_eighths.eighths
    elapsed_now = now - day.general_call
    now_completed = day.completed_page_eighths.eighths

    if not total or now_completed / total < MIN_PROGRESS_FOR_HIGH_WATER:
        return _instantaneous_consumed(day, elapsed_now, now_completed)

    candidates = [
        _instantaneous_consumed(day, elapsed, completed)
        for elapsed, completed in _completed_eighths_trace(day)
        if elapsed <= elapsed_now and completed / total >= MIN_PROGRESS_FOR_HIGH_WATER
    ]
    candidates.append(_instantaneous_consumed(day, elapsed_now, now_completed))
    return max(candidates)


def projected_recovery(day: ShootingDay, now: datetime) -> timedelta:
    """How much better the current forecast is than scheduled_wrap.

    Positive when the current pace projects a wrap ahead of
    scheduled_wrap. This is how a recovery actually shows up: not as
    budget returning (error_budget_consumed never falls), but as
    ground clawed back against the current projection.
    """
    return day.scheduled_wrap - projected_wrap(day, now)


def error_budget_remaining(day: ShootingDay, now: datetime) -> timedelta:
    """Slack left before the day exhausts its error budget.

    Negative once the day has slipped past the overtime threshold.
    """
    return error_budget_total(day) - schedule_slippage(day, now)


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
