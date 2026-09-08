"""JSON-file storage for user-created productions (Module 7).

data/projects/<slug>/{project.json, scenes.json, cast.json, day.json,
provisioning.json} -- no database, per CLAUDE.md. Each save/load pair
is a thin, independently testable wrapper; server/routes/projects.py
is the only caller that orchestrates them together.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from agent.subagents.planner import MonitoringPlan
from agent.tools.scheduling import CastEntry
from emitter.models import Scene, ShootingDay
from server.projects.models import ProjectRecord


class ProjectNotFoundError(Exception):
    pass


def data_root() -> Path:
    return Path(__file__).parent.parent.parent / "data" / "projects"


def slugify_title(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.strip().lower()).strip("-")
    return slug or "production"


def _project_dir(slug: str) -> Path:
    return data_root() / slug


def create_project(title: str, total_days: int, crew_size: int) -> ProjectRecord:
    slug = slugify_title(title)
    record = ProjectRecord(
        slug=slug, title=title, total_days=total_days, crew_size=crew_size, created_at=datetime.now(timezone.utc)
    )
    project_dir = _project_dir(slug)
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "project.json").write_text(record.model_dump_json(indent=2))
    return record


def load_project(slug: str) -> ProjectRecord:
    path = _project_dir(slug) / "project.json"
    if not path.exists():
        raise ProjectNotFoundError(slug)
    return ProjectRecord.model_validate_json(path.read_text())


def list_projects() -> list[ProjectRecord]:
    root = data_root()
    if not root.exists():
        return []
    return [load_project(child.name) for child in sorted(root.iterdir()) if (child / "project.json").exists()]


def save_scenes(slug: str, scenes: list[Scene]) -> None:
    path = _project_dir(slug) / "scenes.json"
    path.write_text("[" + ",".join(scene.model_dump_json() for scene in scenes) + "]")


def load_scenes(slug: str) -> list[Scene] | None:
    path = _project_dir(slug) / "scenes.json"
    if not path.exists():
        return None
    import json

    return [Scene.model_validate(item) for item in json.loads(path.read_text())]


def save_cast(slug: str, cast: list[CastEntry]) -> None:
    path = _project_dir(slug) / "cast.json"
    path.write_text("[" + ",".join(entry.model_dump_json() for entry in cast) + "]")


def load_cast(slug: str) -> list[CastEntry] | None:
    path = _project_dir(slug) / "cast.json"
    if not path.exists():
        return None
    import json

    return [CastEntry.model_validate(item) for item in json.loads(path.read_text())]


def save_day(slug: str, day: ShootingDay) -> None:
    path = _project_dir(slug) / "day.json"
    path.write_text(day.model_dump_json(indent=2))


def load_day(slug: str) -> ShootingDay | None:
    path = _project_dir(slug) / "day.json"
    if not path.exists():
        return None
    return ShootingDay.model_validate_json(path.read_text())


def save_provisioning_plan(slug: str, plan: MonitoringPlan) -> None:
    path = _project_dir(slug) / "provisioning.json"
    path.write_text(plan.model_dump_json(indent=2))


def load_provisioning_plan(slug: str) -> MonitoringPlan | None:
    path = _project_dir(slug) / "provisioning.json"
    if not path.exists():
        return None
    return MonitoringPlan.model_validate_json(path.read_text())
