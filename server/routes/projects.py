"""HTTP surface for user-created productions (Module 7).

Orchestrates server/projects/storage.py (disk) with
agent/tools/breakdown.py (Gemini) and agent/tools/scheduling.py
(deterministic day math) into the six endpoints the /projects console
page needs. Activation is the only place this module touches
server/state.py -- everything upstream of that is pure storage +
domain-tool calls, easy to test without a running replay thread.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, UploadFile
from pydantic import BaseModel

from agent.subagents.planner import decide_monitoring_plan, provision_with_plan
from agent.tools.breakdown import BreakdownParseError, BreakdownQuotaExceeded, breakdown_script
from agent.tools.scheduling import CastEntry, build_shooting_day
from server.projects import storage
from server.projects.models import ProjectRecord
from server.state import STATE, ProvisioningSnapshot

router = APIRouter(prefix="/api/projects", tags=["projects"])


class CreateProjectRequest(BaseModel):
    title: str
    total_days: int
    crew_size: int


class BuildDayRequest(BaseModel):
    day_number: int
    date: date


@router.get("")
def list_projects() -> list[ProjectRecord]:
    return storage.list_projects()


@router.post("")
def create_project(body: CreateProjectRequest) -> ProjectRecord:
    return storage.create_project(title=body.title, total_days=body.total_days, crew_size=body.crew_size)


@router.get("/{slug}")
def get_project(slug: str) -> dict:
    try:
        record = storage.load_project(slug)
    except storage.ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="no such project")

    return {
        "project": record,
        "scenes": storage.load_scenes(slug),
        "cast": storage.load_cast(slug),
        "has_day": storage.load_day(slug) is not None,
    }


@router.post("/{slug}/script")
async def upload_script(slug: str, file: UploadFile) -> dict:
    try:
        storage.load_project(slug)
    except storage.ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="no such project")

    cached = storage.load_scenes(slug)
    if cached is not None:
        return {"scenes": cached}

    pdf_bytes = await file.read()

    try:
        scenes = breakdown_script(pdf_bytes)
    except BreakdownQuotaExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc))
    except BreakdownParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    storage.save_scenes(slug, scenes)
    return {"scenes": scenes}


@router.post("/{slug}/cast")
def save_cast(slug: str, cast: list[CastEntry]) -> dict:
    try:
        storage.load_project(slug)
    except storage.ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="no such project")

    storage.save_cast(slug, cast)
    return {"ok": True}


@router.post("/{slug}/day")
def build_day(slug: str, body: BuildDayRequest):
    try:
        record = storage.load_project(slug)
    except storage.ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="no such project")

    scenes = storage.load_scenes(slug)
    if scenes is None:
        raise HTTPException(status_code=400, detail="upload a script before building the day")
    cast = storage.load_cast(slug) or []

    day = build_shooting_day(
        scenes, cast, day_number=body.day_number, shoot_date=body.date, production_title=record.title
    )
    storage.save_day(slug, day)
    return day


@router.post("/{slug}/activate")
async def activate_project(slug: str) -> dict:
    try:
        record = storage.load_project(slug)
    except storage.ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="no such project")

    day = storage.load_day(slug)
    if day is None:
        raise HTTPException(status_code=400, detail="build the day before activating")

    if STATE.status in ("running", "at_risk"):
        raise HTTPException(status_code=409, detail="a day is already running")

    cached_plan = storage.load_provisioning_plan(slug)
    if cached_plan is not None:
        plan = cached_plan
        live = False
    else:
        plan = await decide_monitoring_plan(day)
        storage.save_provisioning_plan(slug, plan)
        live = True

    result = await provision_with_plan(day, plan)

    with STATE.lock:
        STATE.plan_day = day
        STATE.active_project_slug = slug
        STATE.active_total_days = record.total_days
        STATE.provisioning = ProvisioningSnapshot(info=result, live=live)
        STATE.recovery = None
        STATE.last_snapshot = None

    return {"ok": True}
