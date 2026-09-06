"""Tests for agent/root.py's 429 fallback (Module 6).

Gemini's free-tier daily quota is real -- these tests confirm the
recovery cycle degrades to a committed real run instead of crashing
the replay thread when either observe() or replan() hits it.
"""

from __future__ import annotations

import asyncio

import pytest
from google.genai.errors import ClientError

from agent import root
from agent.subagents.observer import DayObservation
from emitter.simulator import build_day
from gate.checker import RecoveryOption

DAY = build_day("nominal")

OBSERVATION = DayObservation(
    error_budget_consumed=0.9,
    burn_rate=1.6,
    pages_completed_eighths=30,
    pages_remaining_eighths=22,
    setups_completed=10,
    setups_total=20,
    projected_wrap_offset_minutes=60.0,
    minutes_to_golden_hour=90,
    firing_alerts=["martini_error_budget_burn"],
    observed_at="2026-09-03T15:00:00",
)

OPTION = RecoveryOption(
    id="reorder-a",
    kind="reorder",
    description="Pull scene 5 forward to bank pages before Scene 42.",
    affected_scenes=["5"],
    minutes_recovered=20,
)


def _quota_error() -> ClientError:
    return ClientError(429, {"error": {"message": "quota exceeded", "status": "RESOURCE_EXHAUSTED"}}, None)


@pytest.fixture
def cached_recovery_file(tmp_path, monkeypatch):
    cached = root.RecoveryCycleResult(
        observation=OBSERVATION,
        options=[OPTION],
        verdicts=[],
        incident_id="annotation:1",
        live=True,
    )
    path = tmp_path / "cached_recovery.json"
    path.write_text(cached.model_dump_json())
    monkeypatch.setattr(root, "_CACHED_RECOVERY_PATH", path)
    return path


def test_falls_back_to_cache_when_observe_hits_quota(monkeypatch, cached_recovery_file):
    async def _observe_429(day_number):
        raise _quota_error()

    monkeypatch.setattr(root, "observe", _observe_429)

    result = asyncio.run(root.run_recovery_cycle(DAY))

    assert result.live is False
    assert result.options[0].id == "reorder-a"


def test_falls_back_to_cache_when_replan_hits_quota(monkeypatch, cached_recovery_file):
    async def _observe_ok(day_number):
        return OBSERVATION

    async def _replan_429(day, observation):
        raise _quota_error()

    monkeypatch.setattr(root, "observe", _observe_ok)
    monkeypatch.setattr(root, "replan", _replan_429)

    result = asyncio.run(root.run_recovery_cycle(DAY))

    assert result.live is False


def test_reraises_non_quota_client_errors(monkeypatch, cached_recovery_file):
    async def _observe_500(day_number):
        raise ClientError(500, {"error": {"message": "server error"}}, None)

    monkeypatch.setattr(root, "observe", _observe_500)

    with pytest.raises(ClientError):
        asyncio.run(root.run_recovery_cycle(DAY))
