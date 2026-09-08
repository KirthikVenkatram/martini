from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from agent.subagents.observer import DayObservation
from agent.subagents.planner import ProvisioningResult
from agent.tools import provisioning
from agent.tools.provisioning import (
    build_burn_rate_alert_rule,
    build_dashboard,
    open_day_incident,
    provision_burn_rate_alert,
    provision_day_dashboard,
)
from emitter.simulator import build_day

DAY = build_day("nominal")
PROM_UID = "grafanacloud-prom"

OBSERVATION = DayObservation(
    error_budget_consumed=0.42,
    burn_rate=1.8,
    pages_completed_eighths=34,
    pages_remaining_eighths=26,
    setups_completed=12,
    setups_total=20,
    projected_wrap_offset_minutes=47.0,
    minutes_to_golden_hour=210,
    firing_alerts=[],
    observed_at="2026-09-04T14:32:00",
)


def test_build_dashboard_is_well_formed():
    dashboard = build_dashboard(DAY, PROM_UID)

    assert dashboard["uid"] == f"martini-day-{DAY.day_number}"
    assert dashboard["title"] == f"Day {DAY.day_number} - {DAY.production_title}"
    assert dashboard["tags"] == ["martini"]

    panels_by_title = {p["title"]: p for p in dashboard["panels"]}
    assert set(panels_by_title) == {
        "Error budget consumed",
        "Burn rate",
        "Pages completed / remaining (eighths)",
        "Setups completed",
        "Projected wrap offset (min)",
    }

    gauge = panels_by_title["Error budget consumed"]
    assert gauge["type"] == "gauge"
    assert gauge["fieldConfig"]["defaults"]["min"] == 0
    assert gauge["fieldConfig"]["defaults"]["max"] == 1
    steps = gauge["fieldConfig"]["defaults"]["thresholds"]["steps"]
    assert {"color": "red", "value": 0.75} in steps

    trend = panels_by_title["Burn rate"]
    assert trend["type"] == "timeseries"
    trend_steps = trend["fieldConfig"]["defaults"]["thresholds"]["steps"]
    assert {"color": "red", "value": 1.0} in trend_steps

    for panel in dashboard["panels"]:
        for target in panel["targets"]:
            assert target["datasource"] == {"type": "prometheus", "uid": PROM_UID}


def test_build_burn_rate_alert_rule_condition_and_duration():
    rule = build_burn_rate_alert_rule(
        DAY, PROM_UID, "folder-uid", threshold=1.5, evaluation_window_minutes=10, annotation="Losing time."
    )

    assert rule["operation"] == "create"
    assert rule["condition"] == "B"
    assert rule["for"] == "10m"
    assert rule["folder_uid"] == "folder-uid"
    assert rule["annotations"] == {"summary": "Losing time."}

    query, threshold_expr = rule["data"]
    assert query["datasourceUid"] == PROM_UID
    assert query["model"]["expr"] == "martini_burn_rate"
    assert threshold_expr["datasourceUid"] == "__expr__"
    assert threshold_expr["model"]["conditions"][0]["evaluator"]["params"] == [1.5]


def test_provisioning_result_parses():
    result = ProvisioningResult(
        dashboard_uid="martini-day-14",
        dashboard_url="https://example.grafana.net/d/martini-day-14",
        alert_rule_uid="abc123",
        alert_rule_url="https://example.grafana.net/alerting/grafana/abc123/view",
        burn_rate_threshold=1.35,
        evaluation_window_minutes=10,
        annotation="Losing time against Scene 42.",
        provisioned_at="2026-09-06T15:00:00Z",
    )

    assert result.dashboard_uid == "martini-day-14"
    assert result.alert_rule_url == "https://example.grafana.net/alerting/grafana/abc123/view"
    assert result.burn_rate_threshold == 1.35


class _FakeResult:
    def __init__(self, payload: dict | None = None, is_error: bool = False, error_text: str = "boom"):
        self.isError = is_error
        text = error_text if is_error else json.dumps(payload)
        self.content = [SimpleNamespace(text=text)]


class _FakeSession:
    """Stands in for the real MCP ClientSession -- no server process involved."""

    def __init__(self, responses: dict[str, _FakeResult]):
        self._responses = responses
        self.calls: list[tuple[str, dict]] = []

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        return self._responses[name]


def _base_responses(**overrides: _FakeResult) -> dict[str, _FakeResult]:
    responses = {
        "list_datasources": _FakeResult({"datasources": [{"type": "prometheus", "uid": PROM_UID, "isDefault": True}]}),
        "search_folders": _FakeResult({"dashboards": [{"type": "dash-folder", "title": "MARTINI", "uid": "folder-uid"}]}),
    }
    responses.update(overrides)
    return responses


def _patch_connect(monkeypatch, session: _FakeSession) -> None:
    @asynccontextmanager
    async def _fake_connect():
        yield session

    monkeypatch.setattr(provisioning, "_connect", _fake_connect)


def test_provision_day_dashboard_calls_update_dashboard(monkeypatch):
    session = _FakeSession(
        _base_responses(update_dashboard=_FakeResult({"uid": f"martini-day-{DAY.day_number}"}))
    )
    _patch_connect(monkeypatch, session)

    uid = asyncio.run(provision_day_dashboard(DAY))

    assert uid == f"martini-day-{DAY.day_number}"
    tool_name, args = next(call for call in session.calls if call[0] == "update_dashboard")
    assert args["dashboard"]["uid"] == uid
    assert args["folderUid"] == "folder-uid"
    assert args["overwrite"] is True


def test_provision_burn_rate_alert_calls_alerting_manage_rules(monkeypatch):
    session = _FakeSession(_base_responses(alerting_manage_rules=_FakeResult({"uid": "alert-uid"})))
    _patch_connect(monkeypatch, session)

    uid = asyncio.run(provision_burn_rate_alert(DAY, 1.6, 8, "Slipping behind."))

    assert uid == "alert-uid"
    tool_name, args = next(call for call in session.calls if call[0] == "alerting_manage_rules")
    assert args["condition"] == "B"
    assert args["for"] == "8m"
    assert args["annotations"] == {"summary": "Slipping behind."}


def test_open_day_incident_uses_incident_tool_when_available(monkeypatch):
    session = _FakeSession(
        {
            "create_incident": _FakeResult({"incidentID": "IID-1"}),
            "add_activity_to_incident": _FakeResult({"activityID": "A-1"}),
        }
    )
    _patch_connect(monkeypatch, session)

    incident_id = asyncio.run(open_day_incident(DAY, OBSERVATION, "Day 14 is at risk."))

    assert incident_id == "IID-1"
    assert any(call[0] == "add_activity_to_incident" for call in session.calls)


def test_open_day_incident_falls_back_to_annotation_when_incident_tool_fails(monkeypatch):
    session = _FakeSession(
        {
            "create_incident": _FakeResult(is_error=True, error_text="incident feature unavailable"),
            "create_annotation": _FakeResult({"Payload": {"id": 42, "message": "Annotation added"}}),
        }
    )
    _patch_connect(monkeypatch, session)

    incident_id = asyncio.run(open_day_incident(DAY, OBSERVATION, "Day 14 is at risk."))

    assert incident_id == "annotation:42"
    tool_name, args = next(call for call in session.calls if call[0] == "create_annotation")
    assert args["dashboardUid"] == f"martini-day-{DAY.day_number}"
    assert args["text"] == "Day 14 is at risk."


def test_planner_agent_is_built_with_model_from_config(monkeypatch):
    from agent.subagents import planner as planner_module

    monkeypatch.setattr(planner_module, "GEMINI_MODEL", "gemini-test-model-from-config")

    agent = planner_module._build_planner_agent()

    assert agent.model == "gemini-test-model-from-config"


def test_parse_monitoring_plan_rejects_non_json_text():
    from agent.subagents.planner import parse_monitoring_plan

    with pytest.raises(ValueError, match="valid JSON"):
        parse_monitoring_plan("the burn rate looks fine to me")


def test_provision_with_plan_skips_the_decision_call(monkeypatch):
    from agent.subagents import planner as planner_module

    async def _fail_if_called(day):
        raise AssertionError("decide_monitoring_plan should not be called by provision_with_plan")

    monkeypatch.setattr(planner_module, "decide_monitoring_plan", _fail_if_called)

    async def _fake_dashboard(day):
        return "dash-uid"

    async def _fake_alert(day, threshold, window, annotation):
        return "alert-uid"

    monkeypatch.setattr(planner_module, "provision_day_dashboard", _fake_dashboard)
    monkeypatch.setattr(planner_module, "provision_burn_rate_alert", _fake_alert)

    plan = planner_module.MonitoringPlan(
        burn_rate_threshold=1.5, evaluation_window_minutes=10, annotation="Losing time."
    )

    result = asyncio.run(planner_module.provision_with_plan(DAY, plan))

    assert result.dashboard_uid == "dash-uid"
    assert result.alert_rule_uid == "alert-uid"
    assert result.burn_rate_threshold == 1.5
