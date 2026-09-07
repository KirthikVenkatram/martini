"""Tests for server/app.py's HTTP surface (Module 6).

Boot-time provisioning is monkeypatched everywhere here so these tests
never touch the network -- Task 11's manual browser run is what
exercises the real Grafana/Gemini path end to end.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from starlette.testclient import TestClient

from agent.subagents.planner import ProvisioningResult
from server import app as app_module
from server.state import STATE


@pytest.fixture(autouse=True)
def _reset_state():
    STATE.run_id = 0
    STATE.status = "idle"
    STATE.provisioning = None
    STATE.recovery = None
    STATE.recovery_triggered_for_run_id = None
    STATE.last_snapshot = None
    yield


def _fake_provisioning_result() -> ProvisioningResult:
    return ProvisioningResult(
        dashboard_uid="martini-day-14",
        dashboard_url="https://example.grafana.net/d/martini-day-14",
        alert_rule_uid="alert-uid",
        alert_rule_url="https://example.grafana.net/alerting/grafana/alert-uid/view",
        burn_rate_threshold=1.35,
        evaluation_window_minutes=10,
        annotation="Losing time against Scene 42.",
        provisioned_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def client(monkeypatch):
    async def _fake_provision(day):
        return _fake_provisioning_result()

    monkeypatch.setattr(app_module, "provision", _fake_provision)
    monkeypatch.setattr(app_module, "save_cached_provisioning", lambda result: None)

    with TestClient(app_module.app) as test_client:
        yield test_client


def test_start_returns_run_id(client, monkeypatch):
    monkeypatch.setattr(app_module, "start_replay", lambda scenario: 1)

    response = client.post("/api/day/start")

    assert response.status_code == 200
    assert response.json() == {"run_id": 1}


def test_start_returns_409_when_already_running(client, monkeypatch):
    monkeypatch.setattr(app_module, "start_replay", lambda scenario: None)

    response = client.post("/api/day/start")

    assert response.status_code == 409


def test_start_rejects_an_unknown_scenario(client):
    response = client.post("/api/day/start?scenario=bogus")

    assert response.status_code == 422


def test_initial_snapshot_reports_idle_with_the_default_scenario_plan():
    snapshot = app_module._initial_snapshot()

    assert snapshot.status == "idle"
    assert snapshot.day_number == 14
    assert snapshot.scenes  # the default-scenario plan is always available
    assert snapshot.total_page_eighths > 0
    # At idle, "remaining" is the whole day's pages -- nothing shot yet.
    assert snapshot.pages_remaining_eighths == snapshot.total_page_eighths
    assert snapshot.verdict_headline == "STANDING BY FOR CALL"
    assert snapshot.cost_of_delay_sentence  # narration is wired, not left blank


def test_initial_snapshot_falls_back_to_provisioning_state():
    with STATE.lock:
        from server.state import ProvisioningSnapshot

        STATE.provisioning = ProvisioningSnapshot(info=_fake_provisioning_result(), live=False)

    snapshot = app_module._initial_snapshot()

    assert snapshot.provisioning is not None
    assert snapshot.provisioning.live is False
