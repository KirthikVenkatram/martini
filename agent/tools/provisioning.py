"""Grafana write path for the MARTINI agent -- provisioning (Module 4).

Three functions build the dashboard and alert-rule JSON for a shooting
day and send it to Grafana over the ``mcp-grafana`` server's write
tools -- never a REST call this repo writes itself. Unlike the
observer's read path (agent/subagents/observer.py), there is no LlmAgent
turn in the write path itself: the JSON a dashboard or alert rule needs
is exact and structural (panel types, gridPos, threshold steps, query
expressions), and an LLM asked to freehand it would occasionally get a
field wrong with nothing here to catch it -- unlike gate/checker.py's
deterministic legality check downstream of the replanner. So this
module builds that JSON in plain Python and is unit-testable against it
(tests/test_provisioning.py asserts the JSON is well-formed without
touching a network).

That split is deliberate: the agent still makes a real decision, just
not this one. agent/subagents/planner.py's LlmAgent reasons over the
day's plan (total pages, how much slack the schedule has) to decide
what's worth alerting on -- the burn-rate threshold, how long it must
hold, and the plain-English annotation describing why. Those decided
values are passed into ``provision_burn_rate_alert`` below, which then
handles the schema. The agent decides WHAT to monitor; Python decides
HOW to say that to Grafana.

Each write still goes through mcp-grafana's MCP tools, opened here over
its own raw ``mcp`` SDK session (agent.tools.grafana_mcp's
``grafana_server_params()``) rather than through an ADK McpToolset:
McpTool.run_async requires a ToolContext that only exists inside an
LlmAgent's own turn, and there is no such turn on this path.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from mcp import ClientSession
from mcp.client.stdio import stdio_client

from agent.subagents.observer import DayObservation
from agent.tools.grafana_mcp import grafana_server_params
from emitter.models import ShootingDay

_MARTINI_FOLDER_TITLE = "MARTINI"


def _dashboard_uid(day: ShootingDay) -> str:
    return f"martini-day-{day.day_number}"


@asynccontextmanager
async def _connect() -> AsyncIterator[ClientSession]:
    """Opens one raw MCP session against mcp-grafana for a single write."""
    async with stdio_client(grafana_server_params()) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


async def _call_tool(session: ClientSession, name: str, arguments: dict[str, Any]) -> Any:
    """Calls one MCP tool and returns its parsed JSON payload.

    Raises RuntimeError naming the tool on an MCP-level error, so a
    failed write is diagnosable (which tool, what Grafana said) instead
    of a bare KeyError further down.
    """
    result = await session.call_tool(name, arguments)
    text = result.content[0].text if result.content else ""
    if result.isError:
        raise RuntimeError(f"Grafana MCP tool {name!r} failed: {text}")
    return json.loads(text)


async def _ensure_martini_folder(session: ClientSession) -> str:
    """Finds the shared MARTINI folder, creating it on first use."""
    found = await _call_tool(session, "search_folders", {})
    for entry in found.get("dashboards", []):
        if entry.get("type") == "dash-folder" and entry.get("title") == _MARTINI_FOLDER_TITLE:
            return entry["uid"]
    created = await _call_tool(session, "create_folder", {"title": _MARTINI_FOLDER_TITLE})
    return created["uid"]


async def _resolve_prometheus_datasource_uid(session: ClientSession) -> str:
    """Finds the stack's Prometheus datasource UID rather than hardcoding it.

    Grafana Cloud names this per-stack (e.g. "grafanacloud-<stack>-prom"),
    so hardcoding one stack's UID would break on any other. Prefers the
    default datasource; falls back to the first Prometheus one if none
    is marked default.
    """
    result = await _call_tool(session, "list_datasources", {})
    datasources = result.get("datasources", [])
    prometheus = [ds for ds in datasources if ds.get("type") == "prometheus"]
    for ds in prometheus:
        if ds.get("isDefault"):
            return ds["uid"]
    if prometheus:
        return prometheus[0]["uid"]
    raise RuntimeError("no Prometheus datasource found on this Grafana stack")


def _panel(
    panel_id: int,
    title: str,
    panel_type: str,
    grid: dict[str, int],
    targets: list[dict[str, Any]],
    field_defaults: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": panel_id,
        "title": title,
        "type": panel_type,
        "gridPos": grid,
        "targets": targets,
        "fieldConfig": {"defaults": field_defaults or {}, "overrides": []},
    }


def _target(ref_id: str, prom_uid: str, expr: str, instant: bool) -> dict[str, Any]:
    return {
        "refId": ref_id,
        "datasource": {"type": "prometheus", "uid": prom_uid},
        "expr": expr,
        "instant": instant,
        "range": not instant,
    }


def build_dashboard(day: ShootingDay, prom_uid: str) -> dict[str, Any]:
    """Builds the day's dashboard JSON: budget gauge, burn-rate trend, and three stats."""
    return {
        "uid": _dashboard_uid(day),
        "title": f"Day {day.day_number} - {day.production_title}",
        "tags": ["martini"],
        "timezone": "browser",
        "schemaVersion": 39,
        "time": {"from": "now-6h", "to": "now"},
        "refresh": "30s",
        "panels": [
            _panel(
                1,
                "Error budget consumed",
                "gauge",
                {"h": 8, "w": 8, "x": 0, "y": 0},
                [_target("A", prom_uid, "martini_error_budget_consumed", instant=True)],
                {
                    "min": 0,
                    "max": 1,
                    "unit": "percentunit",
                    "thresholds": {
                        "mode": "absolute",
                        "steps": [{"color": "green", "value": None}, {"color": "red", "value": 0.75}],
                    },
                },
            ),
            _panel(
                2,
                "Burn rate",
                "timeseries",
                {"h": 8, "w": 16, "x": 8, "y": 0},
                [_target("A", prom_uid, "martini_burn_rate", instant=False)],
                {
                    "custom": {"thresholdsStyle": {"mode": "line"}},
                    "thresholds": {
                        "mode": "absolute",
                        "steps": [{"color": "green", "value": None}, {"color": "red", "value": 1.0}],
                    },
                },
            ),
            _panel(
                3,
                "Pages completed / remaining (eighths)",
                "stat",
                {"h": 4, "w": 8, "x": 0, "y": 8},
                [
                    {**_target("A", prom_uid, "martini_pages_completed_eighths", instant=True), "legendFormat": "Completed"},
                    {**_target("B", prom_uid, "martini_pages_remaining_eighths", instant=True), "legendFormat": "Remaining"},
                ],
            ),
            _panel(
                4,
                "Setups completed",
                "stat",
                {"h": 4, "w": 8, "x": 8, "y": 8},
                [_target("A", prom_uid, "martini_setups_completed", instant=True)],
            ),
            _panel(
                5,
                "Projected wrap offset (min)",
                "stat",
                {"h": 4, "w": 8, "x": 16, "y": 8},
                [_target("A", prom_uid, "martini_projected_wrap_offset_minutes", instant=True)],
                {"unit": "m"},
            ),
        ],
    }


def build_burn_rate_alert_rule(
    day: ShootingDay,
    prom_uid: str,
    folder_uid: str,
    threshold: float,
    evaluation_window_minutes: int,
    annotation: str,
) -> dict[str, Any]:
    """Builds the alerting_manage_rules 'create' payload for the day's burn-rate alert."""
    return {
        "operation": "create",
        "title": f"Day {day.day_number} burn rate -- {day.production_title}",
        "folder_uid": folder_uid,
        "rule_group": f"martini-day-{day.day_number}",
        "org_id": 1,
        "condition": "B",
        "data": [
            {
                "refId": "A",
                "datasourceUid": prom_uid,
                "model": {"expr": "martini_burn_rate"},
                "relativeTimeRange": {"from": 600, "to": 0},
            },
            {
                "refId": "B",
                "datasourceUid": "__expr__",
                "model": {
                    "type": "threshold",
                    "expression": "A",
                    "conditions": [{"evaluator": {"type": "gt", "params": [threshold]}}],
                },
            },
        ],
        "no_data_state": "OK",
        "exec_err_state": "OK",
        "for": f"{evaluation_window_minutes}m",
        "annotations": {"summary": annotation},
    }


async def provision_day_dashboard(day: ShootingDay) -> str:
    """Creates (or updates) this day's Grafana dashboard. Returns its UID."""
    async with _connect() as session:
        prom_uid = await _resolve_prometheus_datasource_uid(session)
        folder_uid = await _ensure_martini_folder(session)
        result = await _call_tool(
            session,
            "update_dashboard",
            {
                "dashboard": build_dashboard(day, prom_uid),
                "folderUid": folder_uid,
                "overwrite": True,
                "message": f"martini: provisioned day {day.day_number}",
            },
        )
    return result["uid"]


async def provision_burn_rate_alert(
    day: ShootingDay,
    threshold: float,
    evaluation_window_minutes: int,
    annotation: str,
) -> str:
    """Creates this day's burn-rate alert rule. Returns its UID.

    threshold, evaluation_window_minutes, and annotation are the
    planner LlmAgent's decision (agent/subagents/planner.py) about what
    is worth alerting on for this specific day's plan -- this function
    only turns that decision into a legal Grafana alert rule.
    """
    async with _connect() as session:
        prom_uid = await _resolve_prometheus_datasource_uid(session)
        folder_uid = await _ensure_martini_folder(session)
        result = await _call_tool(
            session,
            "alerting_manage_rules",
            build_burn_rate_alert_rule(
                day, prom_uid, folder_uid, threshold, evaluation_window_minutes, annotation
            ),
        )
    return result["uid"]


def _incident_severity(observation: DayObservation) -> str:
    if observation.error_budget_consumed >= 1.0:
        return "critical"
    if observation.error_budget_consumed >= 0.75:
        return "major"
    return "minor"


async def open_day_incident(day: ShootingDay, observation: DayObservation, summary: str) -> str:
    """Opens a Grafana incident for this at-risk day. Returns its identifier.

    Falls back to a dashboard annotation, prefixed "annotation:", if the
    incident tool is unavailable -- confirmed live on this project's own
    free-tier stack, where create_incident fails with a backend error
    (the org isn't provisioned for Incident on that tier). The prefix is
    how the console tells the two identifier shapes apart when building
    a deep link.
    """
    async with _connect() as session:
        try:
            incident = await _call_tool(
                session,
                "create_incident",
                {
                    "title": summary,
                    "severity": _incident_severity(observation),
                    "roomPrefix": f"day{day.day_number}",
                },
            )
            incident_id = incident["incidentID"]
            await _call_tool(
                session,
                "add_activity_to_incident",
                {
                    "incidentId": incident_id,
                    "body": (
                        f"Error budget consumed {observation.error_budget_consumed:.0%}, "
                        f"burn rate {observation.burn_rate:.2f}x pace, "
                        f"projected wrap {observation.projected_wrap_offset_minutes:+.0f} min "
                        "against schedule."
                    ),
                },
            )
            return incident_id
        except RuntimeError:
            annotation = await _call_tool(
                session,
                "create_annotation",
                {
                    "dashboardUid": _dashboard_uid(day),
                    "text": summary,
                    "tags": ["martini", f"day-{day.day_number}"],
                },
            )
            return f"annotation:{annotation['id']}"
