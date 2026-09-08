"""Background replay + server-side recovery trigger (Module 6).

Runs one shooting day's replay (emitter/simulator.py) on a dedicated
thread, publishing a DaySnapshot to every SSE subscriber after each
event. The instant the day's local error-budget reading crosses
agent.root.AT_RISK_ERROR_BUDGET_CONSUMED, this same thread -- and only
this thread, guarded by AppState.try_claim_recovery -- runs the full
observe -> replan -> gate -> incident cycle and publishes its result.
The console never triggers this itself; it only ever renders what
arrives over SSE.
"""

from __future__ import annotations

import asyncio
import threading
from datetime import datetime

from agent.config import GRAFANA_URL
from agent.root import AT_RISK_ERROR_BUDGET_CONSUMED, run_recovery_cycle
from agent.tools.scheduling import generate_scenario
from emitter import schedule
from emitter.models import ShootingDay
from emitter.simulator import build_day, load_scenario, replay_day
from server import derived, narration
from server.projects import storage as projects_storage
from server.state import STATE, DaySnapshot, EventType, RecoverySnapshot, SceneSnapshot, Status


def _cast_names(day: ShootingDay, cast_ids: list[str]) -> list[str]:
    performers_by_id = {p.id: p for p in day.performers}
    return [performers_by_id[cid].character_name if cid in performers_by_id else cid for cid in cast_ids]


def _scene_shooting_order(day: ShootingDay) -> list[str]:
    seen: list[str] = []
    for setup in day.setups:
        if setup.scene_number not in seen:
            seen.append(setup.scene_number)
    return seen


def scene_snapshots(day: ShootingDay) -> list[SceneSnapshot]:
    """day.scenes as the strip board renders them: shooting order first,
    then any scene with no setup yet at the end, same fallback as
    agent/subagents/replanner.py's _scene_shooting_order."""
    order = _scene_shooting_order(day)
    scenes_by_number = {s.number: s for s in day.scenes}
    ordered_numbers = order + [s.number for s in day.scenes if s.number not in order]
    return [
        SceneSnapshot(
            number=scenes_by_number[number].number,
            synopsis=scenes_by_number[number].synopsis,
            page_eighths_display=str(scenes_by_number[number].page_eighths),
            strip_color=scenes_by_number[number].strip_color,
            cast_names=_cast_names(day, scenes_by_number[number].cast_ids),
        )
        for number in ordered_numbers
    ]


def shot_scene_numbers(day: ShootingDay) -> list[str]:
    setups_by_scene: dict[str, list] = {}
    for setup in day.setups:
        setups_by_scene.setdefault(setup.scene_number, []).append(setup)
    return [
        number
        for number in _scene_shooting_order(day)
        if all(s.is_complete for s in setups_by_scene[number])
    ]


def incident_url(dashboard_url: str, incident_id: str | None) -> str | None:
    """Links a Grafana incident, or falls back to the dashboard the
    annotation was written to when the incident-app tool is unavailable
    -- confirmed the normal path on this project's own free-tier stack
    (see agent/tools/provisioning.py's open_day_incident)."""
    if incident_id is None:
        return None
    if incident_id.startswith("annotation:"):
        return dashboard_url
    return f"{GRAFANA_URL.rstrip('/')}/a/grafana-incident-app/incidents/{incident_id}"


def _base_snapshot(
    day: ShootingDay, run_id: int, status: Status, event_type: EventType, *, error_message: str | None = None
) -> DaySnapshot:
    with STATE.lock:
        provisioning = STATE.provisioning
        recovery = STATE.recovery
    return DaySnapshot(
        run_id=run_id,
        event_type=event_type,
        status=status,
        error_message=error_message,
        day_number=day.day_number,
        total_days=STATE.active_total_days,
        production_title=day.production_title,
        provisioning=provisioning,
        scenes=scene_snapshots(day),
        shot_scene_numbers=shot_scene_numbers(day),
        recovery=recovery,
        timeline=derived.timeline_snapshot(day, day.general_call),
        pace=derived.pace_snapshot(day, day.general_call),
        cast_clocks=derived.cast_clock_snapshots(day, day.general_call),
    )


def _carry_forward_snapshot(
    day: ShootingDay, run_id: int, status: Status, event_type: EventType, *, error_message: str | None = None
) -> DaySnapshot:
    """Builds the wrapped/error snapshot from the last real tick rather
    than resetting progress fields (clock, pages, budget, burn rate) to
    their defaults -- the day still finished at a specific time with a
    specific budget consumed, and the console shouldn't flash back to
    zero at the exact moment it wraps."""
    with STATE.lock:
        last = STATE.last_snapshot
        provisioning = STATE.provisioning
        recovery = STATE.recovery
    if last is not None and last.run_id == run_id:
        return last.model_copy(
            update={
                "event_type": event_type,
                "status": status,
                "error_message": error_message,
                "provisioning": provisioning,
                "recovery": recovery,
                "shot_scene_numbers": shot_scene_numbers(day),
                "current_scene": None,
            }
        )
    return _base_snapshot(day, run_id, status, event_type, error_message=error_message)


def _tick_snapshot(day: ShootingDay, run_id: int, status: Status, event: dict) -> DaySnapshot:
    now: datetime = event["now"]
    snapshot = _base_snapshot(day, run_id, status, event["type"])
    snapshot.current_scene = event.get("scene")
    snapshot.clock = now.strftime("%H:%M")
    snapshot.pages_completed_eighths = event["pages_completed_eighths"]
    snapshot.pages_remaining_eighths = event["pages_remaining_eighths"]
    snapshot.total_page_eighths = day.total_page_eighths.eighths
    snapshot.setups_completed = event["setups_completed"]
    snapshot.setups_total = event["setups_total"]
    snapshot.error_budget_consumed = schedule.error_budget_consumed(day, now)
    snapshot.burn_rate = schedule.burn_rate(day, now)
    snapshot.projected_wrap = schedule.projected_wrap(day, now).strftime("%H:%M")
    snapshot.timeline = derived.timeline_snapshot(day, now)
    snapshot.pace = derived.pace_snapshot(day, now)
    snapshot.cast_clocks = derived.cast_clock_snapshots(day, now)

    for field, value in narration.tick_narration(
        day,
        now,
        status,
        pages_remaining_eighths=snapshot.pages_remaining_eighths,
        setups_completed=snapshot.setups_completed,
        setups_total=snapshot.setups_total,
        burn_rate=snapshot.burn_rate,
    ).items():
        setattr(snapshot, field, value)

    return snapshot


def _trigger_recovery_if_at_risk(day: ShootingDay, run_id: int, now: datetime) -> None:
    if schedule.error_budget_consumed(day, now) < AT_RISK_ERROR_BUDGET_CONSUMED:
        return
    if not STATE.try_claim_recovery(run_id):
        return

    with STATE.lock:
        STATE.status = "at_risk"

    cycle_result = asyncio.run(run_recovery_cycle(day))

    with STATE.lock:
        provisioning = STATE.provisioning
    dashboard_url = provisioning.info.dashboard_url if provisioning else ""
    recovery = RecoverySnapshot(
        result=cycle_result, incident_url=incident_url(dashboard_url, cycle_result.incident_id)
    )

    with STATE.lock:
        if STATE.run_id != run_id:
            return
        STATE.recovery = recovery

    STATE.publish(_carry_forward_snapshot(day, run_id, "at_risk", "recovery"))


def _active_day_and_scenario(scenario_name: str) -> tuple[ShootingDay, dict[str, dict]]:
    """The day + replay timing run_replay should use this run.

    Falls back to the named built-in scenario (unchanged behavior) when
    no project has been activated. When one has, its own day.json and a
    freshly-generated scenario (Module 7) are used instead -- the
    nominal/slipping toggle is ignored, since the console never exposes
    it anyway.
    """
    if STATE.active_project_slug is not None:
        day = projects_storage.load_day(STATE.active_project_slug)
        if day is not None:
            return day, generate_scenario(day).scenario

    return build_day(scenario_name), load_scenario(scenario_name)


def run_replay(scenario_name: str, run_id: int) -> None:
    """The background thread body for one Start click. Owns `day` exclusively."""
    day, scenario = _active_day_and_scenario(scenario_name)
    with STATE.lock:
        STATE.plan_day = day

    def on_event(event: dict) -> None:
        if not STATE.is_current(run_id):
            return
        _trigger_recovery_if_at_risk(day, run_id, event["now"])
        if not STATE.is_current(run_id):
            return
        status: Status = "at_risk" if STATE.status == "at_risk" else "running"
        STATE.publish(_tick_snapshot(day, run_id, status, event))

    try:
        replay_day(day, scenario, on_event=on_event)
    except Exception as exc:  # noqa: BLE001 -- surfaced to the console, not silently dropped
        if STATE.is_current(run_id):
            with STATE.lock:
                STATE.status = "error"
            STATE.publish(_carry_forward_snapshot(day, run_id, "error", "error", error_message=str(exc)))
        return

    if STATE.is_current(run_id):
        with STATE.lock:
            STATE.status = "wrapped"
        STATE.publish(_carry_forward_snapshot(day, run_id, "wrapped", "wrapped"))


def start_replay(scenario_name: str) -> int | None:
    """Claims a new run and starts its replay thread. None if one is already running."""
    run_id = STATE.try_start()
    if run_id is None:
        return None
    thread = threading.Thread(target=run_replay, args=(scenario_name, run_id), daemon=True)
    thread.start()
    return run_id
