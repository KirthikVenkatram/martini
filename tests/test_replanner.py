from __future__ import annotations

import asyncio
import json

import pytest
from google.adk.tools.base_toolset import BaseToolset
from google.genai import types

from agent.subagents import replanner as replanner_module
from agent.subagents.observer import DayObservation
from agent.subagents.replanner import parse_recovery_options, replan
from emitter.simulator import build_day

VALID_PAYLOAD = {
    "options": [
        {
            "id": "move_sc43_to_pickups",
            "kind": "move_to_pickups",
            "description": "Move Sc.43 to a pickup day.",
            "affected_scenes": ["Sc.43"],
            "minutes_recovered": 47,
        },
        {
            "id": "drop_coverage_sc43",
            "kind": "drop_coverage",
            "description": "Drop reverse coverage on Sc.43.",
            "affected_scenes": ["Sc.43"],
            "minutes_recovered": 25,
        },
    ]
}


def test_parse_recovery_options_strips_markdown_code_fences():
    fenced = "```json\n" + json.dumps(VALID_PAYLOAD) + "\n```"

    options = parse_recovery_options(fenced)

    assert len(options) == 2
    assert options[0].id == "move_sc43_to_pickups"


DAY = build_day("slipping")
OBSERVATION = DayObservation(
    error_budget_consumed=0.42,
    burn_rate=1.8,
    pages_completed_eighths=34,
    pages_remaining_eighths=26,
    setups_completed=12,
    setups_total=20,
    projected_wrap_offset_minutes=47.0,
    minutes_to_golden_hour=210,
    firing_alerts=["martini_error_budget_burn"],
    observed_at="2026-09-04T14:32:00",
)


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


def _no_final_text_event():
    event = type("FakeEvent", (), {})()
    event.content = None
    event.is_final_response = lambda: True
    return event


class _FakeRunnerSequence:
    """Returns a scripted response per instantiation -- one per retry attempt.

    responses/calls are class attributes because replan() builds a new
    runner instance for each retry, so per-instance state can't track
    which attempt this is.
    """

    responses: list[str | None] = []
    calls = 0

    def __init__(self, agent, app_name):
        self.session_service = _FakeSessionService()
        self.response = _FakeRunnerSequence.responses[_FakeRunnerSequence.calls]
        _FakeRunnerSequence.calls += 1

    async def run_async(self, *, user_id, session_id, new_message):
        if self.response is None:
            yield _no_final_text_event()
        else:
            yield _final_event(self.response)


class _FakeRunnerRaisesOnce:
    """Raises on its first instantiation's run, returns text on its second.

    Reproduces what the ADK runner does for some malformed model tool
    calls: not a clean "no final event", but an exception raised while
    iterating run_async.
    """

    calls = 0

    def __init__(self, agent, app_name):
        self.session_service = _FakeSessionService()
        self.attempt = _FakeRunnerRaisesOnce.calls
        _FakeRunnerRaisesOnce.calls += 1

    async def run_async(self, *, user_id, session_id, new_message):
        if self.attempt == 0:
            raise ValueError("Tool 'isoformat' not found.")
        yield _final_event(json.dumps(VALID_PAYLOAD))


def test_replan_retries_once_when_first_turn_raises(monkeypatch):
    _FakeRunnerRaisesOnce.calls = 0
    monkeypatch.setattr(replanner_module, "InMemoryRunner", _FakeRunnerRaisesOnce)

    options = asyncio.run(replan(DAY, OBSERVATION))

    assert len(options) == 2
    assert _FakeRunnerRaisesOnce.calls == 2


def test_replan_retries_once_when_first_turn_produces_no_final_text(monkeypatch):
    _FakeRunnerSequence.responses = [None, json.dumps(VALID_PAYLOAD)]
    _FakeRunnerSequence.calls = 0
    monkeypatch.setattr(replanner_module, "InMemoryRunner", _FakeRunnerSequence)

    options = asyncio.run(replan(DAY, OBSERVATION))

    assert len(options) == 2
    assert _FakeRunnerSequence.calls == 2


def test_replan_raises_if_retry_also_produces_no_final_text(monkeypatch):
    _FakeRunnerSequence.responses = [None, None]
    _FakeRunnerSequence.calls = 0
    monkeypatch.setattr(replanner_module, "InMemoryRunner", _FakeRunnerSequence)

    with pytest.raises(RuntimeError, match="no final response"):
        asyncio.run(replan(DAY, OBSERVATION))

    assert _FakeRunnerSequence.calls == 2
