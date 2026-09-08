"""The planner subagent -- MARTINI's write path onto Grafana (Module 4).

An ADK LlmAgent that decides what a shooting day's burn-rate alert
should watch for -- the threshold, how long it must hold, and the
plain-English line the alert shows when it fires -- grounded in that
day's own plan (total pages, how much error budget it has). It has no
Grafana tools: the actual writes (building and sending the dashboard
and alert-rule JSON) are Python, not model output, and live in
agent/tools/provisioning.py. This agent's only output is that decision;
provisioning.py turns it into a legal Grafana alert rule.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from google.adk.agents import LlmAgent
from google.adk.runners import InMemoryRunner
from google.genai import types
from pydantic import BaseModel, ValidationError

from agent.config import GEMINI_MODEL, GRAFANA_URL
from agent.tools.provisioning import provision_burn_rate_alert, provision_day_dashboard
from emitter.models import ShootingDay

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "planner.md"


class MonitoringPlan(BaseModel):
    burn_rate_threshold: float
    evaluation_window_minutes: int
    annotation: str


class ProvisioningResult(BaseModel):
    dashboard_uid: str
    dashboard_url: str
    alert_rule_uid: str
    alert_rule_url: str
    burn_rate_threshold: float
    evaluation_window_minutes: int
    annotation: str
    provisioned_at: datetime


def _build_planner_agent() -> LlmAgent:
    return LlmAgent(
        name="planner",
        model=GEMINI_MODEL,
        instruction=_PROMPT_PATH.read_text(),
        description="Decides shooting-day burn-rate alert thresholds from the day's plan.",
    )


def parse_monitoring_plan(raw_text: str) -> MonitoringPlan:
    """Parses the planner's raw model output into a MonitoringPlan.

    Raised errors name what was wrong (invalid JSON vs. a schema
    mismatch) so a malformed model reply is diagnosable, not a bare
    traceback. Strips a markdown code fence first -- Gemini sometimes
    wraps its JSON reply in ```json ... ``` despite the prompt asking
    for strict JSON, the same defensive step agent/tools/breakdown.py
    already takes for its own JSON reply.
    """
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if "\n" in text:
            first_line, rest = text.split("\n", 1)
            text = rest if first_line.strip().lower() in ("json", "") else text

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"planner did not return valid JSON: {raw_text!r}") from exc

    try:
        return MonitoringPlan.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"planner output does not match MonitoringPlan: {exc}") from exc


def _day_summary(day: ShootingDay) -> str:
    scheduled_minutes = (day.scheduled_wrap - day.general_call).total_seconds() / 60
    budget_minutes = (day.overtime_threshold - day.scheduled_wrap).total_seconds() / 60
    return (
        f"Day {day.day_number} -- {day.production_title}\n"
        f"Total pages: {day.total_page_eighths} ({day.total_page_eighths.eighths} eighths)\n"
        f"Scheduled shoot length: {scheduled_minutes:.0f} minutes\n"
        f"Error budget: {budget_minutes:.0f} minutes\n"
        "Decide the burn-rate alert threshold and evaluation window for this day, "
        "and write the annotation."
    )


async def decide_monitoring_plan(day: ShootingDay) -> MonitoringPlan:
    """Runs the planner agent for one turn to get its monitoring decision."""
    agent = _build_planner_agent()
    runner = InMemoryRunner(agent=agent, app_name="martini-planner")
    session = await runner.session_service.create_session(
        app_name="martini-planner", user_id="martini"
    )
    message = types.Content(role="user", parts=[types.Part(text=_day_summary(day))])

    raw_text: str | None = None
    async for event in runner.run_async(
        user_id="martini", session_id=session.id, new_message=message
    ):
        if event.is_final_response() and event.content and event.content.parts:
            raw_text = event.content.parts[0].text

    if raw_text is None:
        raise RuntimeError("planner agent produced no final response")

    return parse_monitoring_plan(raw_text)


async def provision_with_plan(day: ShootingDay, plan: MonitoringPlan) -> ProvisioningResult:
    """Provisions Grafana for one shooting day from an already-decided plan.

    Skips the Gemini call entirely -- used when a project's monitoring
    plan was already decided and cached on an earlier activation
    (Module 7), so re-provisioning on a later activation costs a
    Grafana MCP round trip but not another Gemini request.
    """
    dashboard_uid = await provision_day_dashboard(day)
    alert_rule_uid = await provision_burn_rate_alert(
        day, plan.burn_rate_threshold, plan.evaluation_window_minutes, plan.annotation
    )

    return ProvisioningResult(
        dashboard_uid=dashboard_uid,
        dashboard_url=f"{GRAFANA_URL.rstrip('/')}/d/{dashboard_uid}",
        alert_rule_uid=alert_rule_uid,
        alert_rule_url=f"{GRAFANA_URL.rstrip('/')}/alerting/grafana/{alert_rule_uid}/view",
        burn_rate_threshold=plan.burn_rate_threshold,
        evaluation_window_minutes=plan.evaluation_window_minutes,
        annotation=plan.annotation,
        provisioned_at=datetime.now(timezone.utc),
    )


async def provision(day: ShootingDay) -> ProvisioningResult:
    """Provisions Grafana for one shooting day: decide, then dashboard, then burn-rate alert."""
    plan = await decide_monitoring_plan(day)
    return await provision_with_plan(day, plan)
