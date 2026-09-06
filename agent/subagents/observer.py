"""The observer subagent -- MARTINI's read path onto Grafana (Module 3).

An ADK LlmAgent that perceives a shooting day's current state by
querying Grafana through the Grafana MCPToolset, and nothing else. It
never imports emitter/schedule.py or reads local state: the whole
point is that the agent perceives the day through the observability
stack, the same way it will act on the day (Module 4 onward).
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from google.adk.agents import LlmAgent
from google.adk.runners import InMemoryRunner
from google.genai import types
from pydantic import BaseModel, ValidationError

from agent.config import GEMINI_MODEL
from agent.tools.grafana_mcp import build_grafana_toolset

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "observer.md"


class DayObservation(BaseModel):
    error_budget_consumed: float
    burn_rate: float
    pages_completed_eighths: int
    pages_remaining_eighths: int
    setups_completed: int
    setups_total: int
    projected_wrap_offset_minutes: float
    minutes_to_golden_hour: int
    firing_alerts: list[str]
    observed_at: datetime


def _build_observer_agent() -> LlmAgent:
    return LlmAgent(
        name="observer",
        model=GEMINI_MODEL,
        instruction=_PROMPT_PATH.read_text(),
        tools=[build_grafana_toolset()],
        description="Observes shooting-day state from Grafana via MCP.",
    )


def parse_observation(raw_text: str) -> DayObservation:
    """Parses the observer's raw model output into a DayObservation.

    Raised errors name what was wrong (invalid JSON vs. a schema
    mismatch) so a malformed model reply is diagnosable, not a bare
    traceback.
    """
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"observer did not return valid JSON: {raw_text!r}") from exc

    try:
        return DayObservation.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"observer output does not match DayObservation: {exc}") from exc


async def observe(day_number: int) -> DayObservation:
    """Queries Grafana (via MCP) for shooting day `day_number`'s current state."""
    agent = _build_observer_agent()
    runner = InMemoryRunner(agent=agent, app_name="martini-observer")
    session = await runner.session_service.create_session(
        app_name="martini-observer", user_id="martini"
    )
    message = types.Content(
        role="user",
        parts=[types.Part(text=f"Observe shooting day {day_number}.")],
    )

    raw_text: str | None = None
    async for event in runner.run_async(
        user_id="martini", session_id=session.id, new_message=message
    ):
        if event.is_final_response() and event.content and event.content.parts:
            raw_text = event.content.parts[0].text

    if raw_text is None:
        raise RuntimeError("observer agent produced no final response")

    return parse_observation(raw_text)
