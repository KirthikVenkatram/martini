from __future__ import annotations

from datetime import datetime

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from agent.subagents.planner import MonitoringPlan, ProvisioningResult
from agent.tools.scheduling import CastEntry
from emitter.models import PageEighths, Scene
from server.projects import storage as storage_module
from server.routes.projects import router as projects_router
from server.state import STATE


@pytest.fixture(autouse=True)
def _isolated_data_root(tmp_path, monkeypatch):
    monkeypatch.setattr(storage_module, "data_root", lambda: tmp_path / "projects")
    yield


@pytest.fixture(autouse=True)
def _reset_state():
    STATE.run_id = 0
    STATE.status = "idle"
    STATE.provisioning = None
    STATE.recovery = None
    STATE.active_project_slug = None
    STATE.last_snapshot = None
    yield


@pytest.fixture
def client():
    # A standalone app carrying only this router -- server/app.py's
    # real inclusion of projects_router (and its FastAPI lifespan,
    # which provisions Day 14 at startup) is a later task's concern,
    # not this one's. Mounting the router on a bare FastAPI() here
    # means these tests exercise exactly this task's routes with no
    # lifespan to mock and no dependency on when app.py wires it in.
    app = FastAPI()
    app.include_router(projects_router)
    with TestClient(app) as test_client:
        yield test_client


def test_create_then_list_projects(client):
    response = client.post("/api/projects", json={"title": "The Quarry", "total_days": 12, "crew_size": 40})
    assert response.status_code == 200
    slug = response.json()["slug"]

    listed = client.get("/api/projects").json()
    assert any(p["slug"] == slug for p in listed)


def test_get_unknown_project_is_404(client):
    response = client.get("/api/projects/does-not-exist")
    assert response.status_code == 404


def test_upload_script_writes_scenes_and_caches_on_second_call(client, monkeypatch):
    created = client.post("/api/projects", json={"title": "The Quarry", "total_days": 1, "crew_size": 1}).json()
    slug = created["slug"]

    calls = {"count": 0}

    def _fake_breakdown(pdf_bytes: bytes) -> list[Scene]:
        calls["count"] += 1
        return [
            Scene(
                number="1",
                synopsis="A.",
                page_eighths=PageEighths.from_string("1"),
                int_ext="INT",
                day_night="DAY",
                location="Set",
                cast_ids=["marcus"],
                estimated_setups=1,
            )
        ]

    monkeypatch.setattr("server.routes.projects.breakdown_script", _fake_breakdown)

    first = client.post(f"/api/projects/{slug}/script", files={"file": ("script.pdf", b"%PDF-1", "application/pdf")})
    assert first.status_code == 200
    assert len(first.json()["scenes"]) == 1
    assert calls["count"] == 1

    second = client.post(f"/api/projects/{slug}/script", files={"file": ("script.pdf", b"%PDF-1", "application/pdf")})
    assert second.status_code == 200
    assert calls["count"] == 1  # cached -- breakdown_script was not called again


def test_upload_script_surfaces_a_quota_error_plainly(client, monkeypatch):
    created = client.post("/api/projects", json={"title": "The Quarry", "total_days": 1, "crew_size": 1}).json()
    slug = created["slug"]

    from agent.tools.breakdown import BreakdownQuotaExceeded

    def _raise_quota(pdf_bytes: bytes) -> list[Scene]:
        raise BreakdownQuotaExceeded("quota's gone")

    monkeypatch.setattr("server.routes.projects.breakdown_script", _raise_quota)

    response = client.post(f"/api/projects/{slug}/script", files={"file": ("script.pdf", b"%PDF-1", "application/pdf")})

    assert response.status_code == 429
    assert "quota" in response.json()["detail"].lower()


def test_upload_script_surfaces_a_parse_error_plainly(client, monkeypatch):
    created = client.post("/api/projects", json={"title": "The Quarry", "total_days": 1, "crew_size": 1}).json()
    slug = created["slug"]

    from agent.tools.breakdown import BreakdownParseError

    def _raise_parse_error(pdf_bytes: bytes) -> list[Scene]:
        raise BreakdownParseError("scene at index 0 failed to parse: 'page_eighths'")

    monkeypatch.setattr("server.routes.projects.breakdown_script", _raise_parse_error)

    response = client.post(f"/api/projects/{slug}/script", files={"file": ("script.pdf", b"%PDF-1", "application/pdf")})

    assert response.status_code == 422
    assert "page_eighths" in response.json()["detail"]


def test_save_cast_then_build_day(client):
    created = client.post("/api/projects", json={"title": "The Quarry", "total_days": 1, "crew_size": 1}).json()
    slug = created["slug"]
    storage_module.save_scenes(
        slug,
        [
            Scene(
                number="1",
                synopsis="A.",
                page_eighths=PageEighths.from_string("1"),
                int_ext="INT",
                day_night="DAY",
                location="Set",
                cast_ids=["marcus"],
                estimated_setups=1,
            )
        ],
    )

    cast_response = client.post(
        f"/api/projects/{slug}/cast",
        json=[{"character_name": "MARCUS", "previous_night_wrap": "2026-09-02T20:00:00"}],
    )
    assert cast_response.status_code == 200

    day_response = client.post(f"/api/projects/{slug}/day", json={"day_number": 1, "date": "2026-09-08"})
    assert day_response.status_code == 200
    body = day_response.json()
    assert body["day_number"] == 1
    assert body["production_title"] == "The Quarry"


def test_activate_sets_state_and_reprovisions(client, monkeypatch):
    created = client.post("/api/projects", json={"title": "The Quarry", "total_days": 5, "crew_size": 1}).json()
    slug = created["slug"]
    storage_module.save_scenes(
        slug,
        [
            Scene(
                number="1",
                synopsis="A.",
                page_eighths=PageEighths.from_string("1"),
                int_ext="INT",
                day_night="DAY",
                location="Set",
                cast_ids=[],
                estimated_setups=1,
            )
        ],
    )
    client.post(f"/api/projects/{slug}/cast", json=[])
    client.post(f"/api/projects/{slug}/day", json={"day_number": 1, "date": "2026-09-08"})

    async def _fake_decide(day):
        return MonitoringPlan(burn_rate_threshold=1.4, evaluation_window_minutes=10, annotation="Watch it.")

    async def _fake_provision_with_plan(day, plan):
        return ProvisioningResult(
            dashboard_uid="d",
            dashboard_url="http://x/d/d",
            alert_rule_uid="a",
            alert_rule_url="http://x/a/a",
            burn_rate_threshold=plan.burn_rate_threshold,
            evaluation_window_minutes=plan.evaluation_window_minutes,
            annotation=plan.annotation,
            provisioned_at=datetime.now(),
        )

    monkeypatch.setattr("server.routes.projects.decide_monitoring_plan", _fake_decide)
    monkeypatch.setattr("server.routes.projects.provision_with_plan", _fake_provision_with_plan)

    response = client.post(f"/api/projects/{slug}/activate")

    assert response.status_code == 200
    assert STATE.active_project_slug == slug
    assert STATE.active_total_days == 5
    assert STATE.plan_day.production_title == "The Quarry"
    assert STATE.provisioning is not None


def test_activate_reuses_a_cached_provisioning_plan(client, monkeypatch):
    created = client.post("/api/projects", json={"title": "The Quarry", "total_days": 1, "crew_size": 1}).json()
    slug = created["slug"]
    storage_module.save_scenes(slug, [])
    client.post(f"/api/projects/{slug}/cast", json=[])
    client.post(f"/api/projects/{slug}/day", json={"day_number": 1, "date": "2026-09-08"})
    storage_module.save_provisioning_plan(
        slug, MonitoringPlan(burn_rate_threshold=1.6, evaluation_window_minutes=8, annotation="Cached.")
    )

    async def _fail_if_called(day):
        raise AssertionError("decide_monitoring_plan should not be called when a plan is cached")

    async def _fake_provision_with_plan(day, plan):
        return ProvisioningResult(
            dashboard_uid="d",
            dashboard_url="http://x/d/d",
            alert_rule_uid="a",
            alert_rule_url="http://x/a/a",
            burn_rate_threshold=plan.burn_rate_threshold,
            evaluation_window_minutes=plan.evaluation_window_minutes,
            annotation=plan.annotation,
            provisioned_at=datetime.now(),
        )

    monkeypatch.setattr("server.routes.projects.decide_monitoring_plan", _fail_if_called)
    monkeypatch.setattr("server.routes.projects.provision_with_plan", _fake_provision_with_plan)

    response = client.post(f"/api/projects/{slug}/activate")

    assert response.status_code == 200
    assert STATE.provisioning.info.burn_rate_threshold == 1.6
    assert STATE.provisioning.live is False


def test_activate_rejects_while_a_replay_is_running(client):
    created = client.post("/api/projects", json={"title": "The Quarry", "total_days": 1, "crew_size": 1}).json()
    slug = created["slug"]
    storage_module.save_scenes(slug, [])
    client.post(f"/api/projects/{slug}/cast", json=[])
    client.post(f"/api/projects/{slug}/day", json={"day_number": 1, "date": "2026-09-08"})

    STATE.status = "running"

    response = client.post(f"/api/projects/{slug}/activate")

    assert response.status_code == 409
