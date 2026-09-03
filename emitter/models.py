from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel


class PageEighths(BaseModel):
    """A film script page length measured in eighths of a page (8 eighths = 1 page)."""

    eighths: int

    @classmethod
    def from_string(cls, value: str) -> "PageEighths":
        parts = value.strip().split()
        if len(parts) not in (1, 2):
            raise ValueError(f"invalid page eighths string: {value!r}")

        whole_part = parts[0] if len(parts) == 2 else None
        fraction_part = parts[-1]

        if "/" in fraction_part:
            numerator, _, denominator = fraction_part.partition("/")
            if denominator != "8":
                raise ValueError(f"invalid page eighths string: {value!r}")
            fraction = int(numerator)
            whole = int(whole_part) if whole_part is not None else 0
        else:
            if whole_part is not None:
                raise ValueError(f"invalid page eighths string: {value!r}")
            fraction = 0
            whole = int(fraction_part)

        return cls(eighths=whole * 8 + fraction)

    def __str__(self) -> str:
        if self.eighths == 0:
            return "0"
        whole, fraction = divmod(self.eighths, 8)
        parts = []
        if whole:
            parts.append(str(whole))
        if fraction:
            parts.append(f"{fraction}/8")
        return " ".join(parts)

    def __add__(self, other: "PageEighths") -> "PageEighths":
        return PageEighths(eighths=self.eighths + other.eighths)

    def __sub__(self, other: "PageEighths") -> "PageEighths":
        return PageEighths(eighths=self.eighths - other.eighths)

    def __lt__(self, other: "PageEighths") -> bool:
        return self.eighths < other.eighths

    def __le__(self, other: "PageEighths") -> bool:
        return self.eighths <= other.eighths

    def __gt__(self, other: "PageEighths") -> bool:
        return self.eighths > other.eighths

    def __ge__(self, other: "PageEighths") -> bool:
        return self.eighths >= other.eighths


_STRIP_COLORS = {
    ("INT", "DAY"): "day-int",
    ("EXT", "DAY"): "day-ext",
    ("INT", "NIGHT"): "night-int",
    ("EXT", "NIGHT"): "night-ext",
}


class Scene(BaseModel):
    number: str
    synopsis: str
    page_eighths: PageEighths
    int_ext: Literal["INT", "EXT"]
    day_night: Literal["DAY", "NIGHT"]
    location: str
    cast_ids: list[str]
    estimated_setups: int

    @property
    def strip_color(self) -> str:
        return _STRIP_COLORS[(self.int_ext, self.day_night)]


class Setup(BaseModel):
    """A camera position within a scene."""

    id: str
    scene_number: str
    description: str
    estimated_minutes: int
    actual_minutes: int | None = None
    takes: int = 0

    @property
    def is_complete(self) -> bool:
        return self.actual_minutes is not None


class Performer(BaseModel):
    id: str
    name: str
    character_name: str
    call_time: datetime
    wrap_time: datetime | None = None
    minimum_turnaround_hours: float = 11.0
    is_minor: bool = False
    previous_night_wrap: datetime | None = None


class ShootingDay(BaseModel):
    day_number: int
    production_title: str
    shoot_date: date
    general_call: datetime
    scheduled_wrap: datetime
    overtime_threshold: datetime
    golden_hour_start: datetime
    meal_due_by: datetime
    scenes: list[Scene]
    setups: list[Setup]
    performers: list[Performer]

    @property
    def total_page_eighths(self) -> PageEighths:
        total = PageEighths(eighths=0)
        for scene in self.scenes:
            total = total + scene.page_eighths
        return total

    @property
    def completed_page_eighths(self) -> PageEighths:
        total = PageEighths(eighths=0)
        for scene in self.scenes:
            scene_setups = [s for s in self.setups if s.scene_number == scene.number]
            if scene_setups and all(s.is_complete for s in scene_setups):
                total = total + scene.page_eighths
        return total

    @property
    def remaining_page_eighths(self) -> PageEighths:
        return self.total_page_eighths - self.completed_page_eighths

    @property
    def total_setups(self) -> int:
        return len(self.setups)

    @property
    def completed_setups(self) -> int:
        return sum(1 for setup in self.setups if setup.is_complete)
