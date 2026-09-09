"""In-memory state for the MARTINI console server (Module 6).

One shooting day replays at a time. AppState is the single source of
truth every request and the background replay thread (server/replay.py)
read and write through -- guarded by `lock` so a second POST
/api/day/start, or a stray event from a superseded replay thread, can
never be observed as if it were current.
"""

from __future__ import annotations

import queue
import threading
from typing import Literal

from pydantic import BaseModel

from agent.root import RecoveryCycleResult
from agent.subagents.planner import ProvisioningResult
from emitter.models import ShootingDay
from emitter.simulator import build_day

Status = Literal["idle", "running", "at_risk", "wrapped", "error"]
EventType = Literal[
    "connected",
    "day_start",
    "setup_wrapped",
    "scene_wrapped",
    "meal_break",
    "at_risk",
    "recovery",
    "wrapped",
    "error",
]

_BUSY_STATUSES = {"running", "at_risk"}

DEFAULT_SCENARIO = "slipping"
TOTAL_SHOOT_DAYS = 32


class ProvisioningSnapshot(BaseModel):
    info: ProvisioningResult
    live: bool


class RecoverySnapshot(BaseModel):
    result: RecoveryCycleResult
    incident_url: str | None = None


class SceneSnapshot(BaseModel):
    number: str
    synopsis: str
    page_eighths_display: str
    strip_color: Literal["day-int", "day-ext", "night-int", "night-ext"]
    cast_names: list[str]


class TimelineSnapshot(BaseModel):
    """The day timeline (Module 6.3): call time to the overtime
    threshold, as fractions of that domain so the component just places
    marks -- it never does date math of its own. projected_wrap_fraction
    is deliberately not clamped above 1.0 so the console can tell the
    projected-wrap marker sits past the overtime line."""

    call_label: str
    overtime_label: str
    elapsed_fraction: float
    meal_fraction: float
    golden_hour_fraction: float
    projected_wrap_fraction: float
    projected_wrap_label: str


class PaceSnapshot(BaseModel):
    """The pace line (Module 6.3): cumulative progress so far, as
    (elapsed fraction of the scheduled day, completed fraction of total
    pages) points. The "pace you needed" line needs no data of its own
    -- normalized this way it's always the diagonal from (0, 0) to
    (1, 1)."""

    actual_points: list[tuple[float, float]]
    behind_label: str | None = None


class CastClockSnapshot(BaseModel):
    """One performer's cast clock (Module 6.3). turnaround_fraction is
    how much of the required rest-before-call minimum today's actual
    rest used up, loaded from the same gate/rules/production_rules.yaml
    the gate itself checks against -- so this always agrees with
    whatever the gate later approves or rejects."""

    character_name: str
    hours_worked: float
    turnaround_fraction: float
    is_tight: bool


class DaySnapshot(BaseModel):
    """Everything one SSE message tells the console. Sent in full on
    every push -- there is no partial-update variant to keep in sync."""

    run_id: int
    event_type: EventType
    status: Status
    error_message: str | None = None
    day_number: int
    total_days: int = TOTAL_SHOOT_DAYS
    production_title: str
    provisioning: ProvisioningSnapshot | None = None
    scenes: list[SceneSnapshot]
    current_scene: str | None = None
    shot_scene_numbers: list[str] = []
    clock: str | None = None
    pages_completed_eighths: int = 0
    pages_remaining_eighths: int = 0
    total_page_eighths: int = 0
    setups_completed: int = 0
    setups_total: int = 0
    error_budget_consumed: float = 0.0
    burn_rate: float = 1.0
    projected_wrap: str | None = None
    recovery: RecoverySnapshot | None = None
    timeline: TimelineSnapshot
    pace: PaceSnapshot
    cast_clocks: list[CastClockSnapshot]

    # Plain-English narration (Module 6.2) -- computed once in
    # server/narration.py so the console never has to turn a raw number
    # into a sentence itself. The number still travels on the fields
    # above for anything that wants to render it directly (the budget
    # bar's width); these are what an AD actually reads.
    verdict_headline: str = ""
    verdict_subline: str = ""
    budget_sentence: str = ""
    burn_sentence: str = ""
    pages_sentence: str = ""
    cost_of_delay_sentence: str = ""


class AppState:
    """Guards everything the replay thread and the API handlers share."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.run_id = 0
        self.status: Status = "idle"
        self.plan_day: ShootingDay = build_day(DEFAULT_SCENARIO)
        self.active_project_slug: str | None = None
        self.active_total_days: int = TOTAL_SHOOT_DAYS
        self.provisioning: ProvisioningSnapshot | None = None
        self.recovery: RecoverySnapshot | None = None
        self.recovery_triggered_for_run_id: int | None = None
        self.last_snapshot: DaySnapshot | None = None
        self.subscribers: list[queue.Queue] = []

    def subscribe(self) -> "queue.Queue[DaySnapshot]":
        q: "queue.Queue[DaySnapshot]" = queue.Queue()
        with self.lock:
            self.subscribers.append(q)
        return q

    def unsubscribe(self, q: "queue.Queue[DaySnapshot]") -> None:
        with self.lock:
            if q in self.subscribers:
                self.subscribers.remove(q)

    def publish(self, snapshot: DaySnapshot) -> None:
        with self.lock:
            self.last_snapshot = snapshot
            subscribers = list(self.subscribers)
        for q in subscribers:
            q.put_nowait(snapshot)

    def try_start(self) -> int | None:
        """Atomically claims a new run, or returns None if one is already running."""
        with self.lock:
            if self.status in _BUSY_STATUSES:
                return None
            self.run_id += 1
            self.status = "running"
            self.recovery = None
            self.recovery_triggered_for_run_id = None
            return self.run_id

    def try_claim_recovery(self, run_id: int) -> bool:
        """True only the first time this run_id asks to trigger recovery."""
        with self.lock:
            if self.run_id != run_id:
                return False
            if self.recovery_triggered_for_run_id == run_id:
                return False
            self.recovery_triggered_for_run_id = run_id
            return True

    def is_current(self, run_id: int) -> bool:
        with self.lock:
            return self.run_id == run_id


STATE = AppState()
