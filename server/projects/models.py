from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class ProjectRecord(BaseModel):
    slug: str
    title: str
    total_days: int
    crew_size: int
    created_at: datetime
