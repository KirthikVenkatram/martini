"""Orchestrates one replan-and-gate recovery cycle for a shooting day (Module 5).

observe (Module 3) -> replan (agent/subagents/replanner.py) -> gate
each option (gate/checker.py) -> if the day is at risk and at least one
option is legal, open a Grafana incident (agent/tools/provisioning.py)
summarizing what was proposed and what was rejected.
"""

from __future__ import annotations

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


class RecoveryCycleResult(BaseModel):
    observation: DayObservation
    options: list[RecoveryOption]
    verdicts: list[GateVerdict]
    incident_id: str | None = None


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


async def run_recovery_cycle(day: ShootingDay) -> RecoveryCycleResult:
    """Runs one full observe -> replan -> gate -> incident cycle."""
    observation = await observe(day.day_number)
    options = await replan(day, observation)
    verdicts = [check(day, option) for option in options]

    incident_id = None
    if _day_at_risk(observation) and any(verdict.approved for verdict in verdicts):
        incident_id = await open_day_incident(day, observation, _incident_summary(options, verdicts))

    return RecoveryCycleResult(
        observation=observation, options=options, verdicts=verdicts, incident_id=incident_id
    )
