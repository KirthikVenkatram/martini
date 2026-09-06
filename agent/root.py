"""Orchestrates one replan-and-gate recovery cycle for a shooting day (Module 5).

observe (Module 3) -> replan (agent/subagents/replanner.py) -> gate
each option (gate/checker.py) -> if the day is at risk and at least one
option is legal, open a Grafana incident (agent/tools/provisioning.py)
summarizing what was proposed and what was rejected.
"""

from __future__ import annotations

import json
from pathlib import Path

from google.genai.errors import ClientError
from pydantic import BaseModel

from agent.subagents.observer import DayObservation, observe
from agent.subagents.replanner import replan
from agent.tools.provisioning import open_day_incident
from emitter.models import ShootingDay
from gate.checker import GateVerdict, RecoveryOption, check
from gate.explain import explain

AT_RISK_ERROR_BUDGET_CONSUMED = 0.75
"""Matches provisioning.py's own "major" severity threshold -- the
same reading that would already have fired the day's burn-rate alert."""

_CACHED_RECOVERY_PATH = Path(__file__).parent.parent / "data" / "cached_recovery.json"


class RecoveryCycleResult(BaseModel):
    observation: DayObservation
    options: list[RecoveryOption]
    verdicts: list[GateVerdict]
    incident_id: str | None = None
    live: bool = True


def _day_at_risk(observation: DayObservation) -> bool:
    return observation.error_budget_consumed >= AT_RISK_ERROR_BUDGET_CONSUMED or bool(
        observation.firing_alerts
    )


def _incident_summary(options: list[RecoveryOption], verdicts: list[GateVerdict]) -> str:
    verdicts_by_id = {verdict.option_id: verdict for verdict in verdicts}
    lines = []
    for option in options:
        verdict = verdicts_by_id[option.id]
        if verdict.approved:
            lines.append(f"Approved -- {option.description}")
        else:
            reasons = " ".join(explain(violation) for violation in verdict.violations)
            lines.append(f"Rejected -- {option.description} {reasons}")
    return " | ".join(lines)


def _load_cached_recovery_cycle() -> RecoveryCycleResult:
    """Falls back to a committed real run's recovery cycle when Gemini's
    daily quota is exhausted -- confirmed live on this project's own
    free-tier key. Always reports live=False here regardless of what the
    committed fixture itself says, since reaching this function always
    means the live call just failed.
    """
    payload = json.loads(_CACHED_RECOVERY_PATH.read_text())
    result = RecoveryCycleResult.model_validate(payload)
    return result.model_copy(update={"live": False})


async def run_recovery_cycle(day: ShootingDay) -> RecoveryCycleResult:
    """Runs one full observe -> replan -> gate -> incident cycle.

    Falls back to a cached, previously-real recovery cycle if Gemini's
    daily free-tier quota is exhausted (HTTP 429) during either the
    observe or replan call. Any other error is not swallowed here.
    """
    try:
        observation = await observe(day.day_number)
    except ClientError as exc:
        if exc.code == 429:
            return _load_cached_recovery_cycle()
        raise

    try:
        options = await replan(day, observation)
    except ClientError as exc:
        if exc.code == 429:
            return _load_cached_recovery_cycle()
        raise

    verdicts = [check(day, option) for option in options]

    incident_id = None
    if _day_at_risk(observation) and any(verdict.approved for verdict in verdicts):
        incident_id = await open_day_incident(day, observation, _incident_summary(options, verdicts))

    return RecoveryCycleResult(
        observation=observation, options=options, verdicts=verdicts, incident_id=incident_id, live=True
    )
