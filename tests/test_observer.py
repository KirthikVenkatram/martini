from __future__ import annotations

import asyncio
import json

import pytest
from google.adk.tools.base_toolset import BaseToolset
from google.genai import types

from agent.subagents import observer as observer_module
from agent.subagents.observer import DayObservation, observe, parse_observation


class _FakeGrafanaToolset(BaseToolset):
    """Stands in for the real Grafana MCPToolset -- no MCP server involved."""

    async def get_tools(self, readonly_context=None):
        return []

VALID_PAYLOAD = {
    "error_budget_consumed": 0.42,
    "burn_rate": 1.8,
    "pages_completed_eighths": 34,
    "pages_remaining_eighths": 26,
    "setups_completed": 12,
    "setups_total": 20,
    "projected_wrap_offset_minutes": 47.0,
    "firing_alerts": ["martini_error_budget_burn"],
    "observed_at": "2026-09-04T14:32:00",
}


def test_parse_observation_builds_day_observation_from_valid_json():
    observation = parse_observation(json.dumps(VALID_PAYLOAD))

    assert observation == DayObservation(**VALID_PAYLOAD)


def test_parse_observation_rejects_non_json_text():
    with pytest.raises(ValueError, match="valid JSON"):
        parse_observation("the burn rate looks fine to me")


def test_parse_observation_rejects_json_missing_required_fields():
    incomplete = json.dumps({"error_budget_consumed": 0.5})

    with pytest.raises(ValueError, match="DayObservation"):
        parse_observation(incomplete)


class _FakeSession:
    id = "test-session"


class _FakeSessionService:
    async def create_session(self, **kwargs):
        return _FakeSession()


def _final_event(text: str):
    event = type("FakeEvent", (), {})()
    event.content = types.Content(role="model", parts=[types.Part(text=text)])
    event.is_final_response = lambda: True
    return event


class _FakeRunner:
    response_text = json.dumps(VALID_PAYLOAD)

    def __init__(self, agent, app_name):
        self.session_service = _FakeSessionService()

    async def run_async(self, *, user_id, session_id, new_message):
        yield _final_event(self.response_text)


class _FakeRunnerMalformed(_FakeRunner):
    response_text = "not json at all"


def test_observe_wires_mocked_toolset_and_runner_into_a_day_observation(monkeypatch):
    monkeypatch.setattr(observer_module, "build_grafana_toolset", lambda: _FakeGrafanaToolset())
    monkeypatch.setattr(observer_module, "InMemoryRunner", _FakeRunner)

    observation = asyncio.run(observe(day_number=14))

    assert observation == DayObservation(**VALID_PAYLOAD)


def test_observe_raises_clear_error_on_malformed_model_output(monkeypatch):
    monkeypatch.setattr(observer_module, "build_grafana_toolset", lambda: _FakeGrafanaToolset())
    monkeypatch.setattr(observer_module, "InMemoryRunner", _FakeRunnerMalformed)

    with pytest.raises(ValueError, match="valid JSON"):
        asyncio.run(observe(day_number=14))


def test_observer_agent_is_built_with_model_from_config(monkeypatch):
    monkeypatch.setattr(observer_module, "GEMINI_MODEL", "gemini-test-model-from-config")

    agent = observer_module._build_observer_agent()

    assert agent.model == "gemini-test-model-from-config"
