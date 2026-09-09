# Module 6 — React Console + SSE — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build MARTINI's console — a FastAPI server that replays a shooting day, triggers the agent's replan-and-gate recovery cycle server-side the instant the day goes at risk, and streams everything over SSE to a React console styled as film production paperwork (strip board, call sheet, clipboard) rather than a monitoring dashboard.

**Architecture:** `emitter.simulator.replay_day` runs on one background thread per "Start" click, owned by a small `AppState` singleton guarded by a `threading.Lock`. The instant the local error-budget reading crosses `agent.root.AT_RISK_ERROR_BUDGET_CONSUMED`, that same thread calls `agent.root.run_recovery_cycle` (the existing observe → replan → gate → incident cycle) exactly once per run, then keeps replaying. Every state change is turned into one `DaySnapshot` and pushed to every subscriber; new SSE connections get the last snapshot immediately, so a page refresh never causes a second Gemini call. Gemini quota exhaustion (HTTP 429) during `observe()` or `replan()` falls back to a committed real recovery-cycle fixture; the same pattern covers boot-time Grafana provisioning. The React console renders exactly what the stream sends and never calls anything except `POST /api/day/start`.

**Tech Stack:** Python 3.11+, FastAPI 0.141, uvicorn, Pydantic v2 (backend, in-process agent — no new AI SDK). React 19.2, TypeScript, Vite 8, Tailwind v4 via `@tailwindcss/vite` (CSS-first `@theme`, no `tailwind.config.js`), no state library, no component library.

**Spec:** This plan is written directly from the user's Module 6 brief (design + four corrections) given in this session — no separate spec file exists; the brief is reproduced in full in the conversation this plan was written from. Key excerpts are quoted inline in the Global Constraints below.

## Global Constraints

- Only Google Cloud AI tooling (`google-adk`, `google-genai`) — never add another AI SDK, even transitively.
- Grafana MCP (`grafana/mcp-grafana` via `uvx`) is the only path to Grafana — no REST wrapper. Already wired in `agent/tools/grafana_mcp.py` and `agent/tools/provisioning.py`; Module 6 must not bypass it.
- All demo content stays invented — no real film, studio, or person, anywhere including code comments and copy.
- Recovery triggers **server-side only**, fired from the replay thread the instant status flips to `at_risk`, guarded by a lock so concurrent requests or a page refresh can never double-fire it. The console renders what arrives over SSE; it never initiates a recovery cycle itself.
- Provisioning is cached to `data/cached_provisioning.json` on a successful boot-time provision. If live provisioning fails at startup, fall back to the cached file rather than 503ing or hiding the provisioning log; mark it honestly in the UI as not live.
- `POST /api/day/start` returns 409 if a day is already running (`running` or `at_risk` status); the Start button disables itself while running. Two overlapping replay threads must never both push metrics to Grafana.
- `live: false` is surfaced in the UI, not just logs — both for cached recovery options ("Recovery options from a cached run — Gemini daily quota reached.") and cached provisioning. Never imply cached data was live.
- 429 (`google.genai.errors.ClientError` with `.code == 429`) is caught around both `observe()` and `replan()` independently, falling back to a committed real recovery-cycle fixture (`data/cached_recovery.json`) either way.
- Verdicts are always computed fresh by `gate/checker.py`'s existing pure `check()` (which itself reloads `production_rules.yaml` on every call) — nothing in this module may cache a `GateVerdict` across calls.
- Stack ceiling: React 19, TypeScript, Vite, Tailwind v4 via `@tailwindcss/vite`. No state library, no component library, no shadcn, no UI kit. Nothing in alpha/beta/RC.
- `web/dist` is committed — the deploy host has no Node. `.gitignore`'s blanket `dist/` rule must not swallow it.
- FastAPI, agent in-process, SSE via a hand-rolled async generator — no WebSockets, no third-party SSE library.
- No Kubernetes, no auth, no database, no CI pipeline, no component library.
- Palette is exactly: `--color-board:#1C1A17 --color-paper:#F2EDE3 --color-ink:#16150F --color-strip-day-int:#FFFFFF --color-strip-day-ext:#F5D547 --color-strip-night-int:#7FA8D9 --color-strip-night-ext:#7BAE7F --color-burn:#C2452D`. Those strip colours are the only source of colour in the UI — no gradients, no other accent colours, not even for a "cached" notice.
- Type: Archivo Narrow for strip labels/scene numbers/the clock; Inter for body. The clock is genuinely large.
- The hero is the error budget bar — not a chart, not a stat card. Under it: "4 2/8 pages remaining · wrap projected 19:40" phrasing, never raw field names.
- All boldness goes to the rejection card. It is the only element that gets `--color-burn`. The reason renders in full, in plain English, at a size that cannot be missed.
- Exactly one orchestrated motion moment: the budget bar draining + the current strip pulsing during replay. No fade-up entrances, no hover transitions sprayed on every card. A click response (approving) may animate.
- Copy reads like a 1st AD, never like a field name or a percentage with six decimals.
- Responsive to mobile, visible keyboard focus (`:focus-visible`), `prefers-reduced-motion` respected, readable contrast throughout.
- One concern per commit, conventional commit messages. Tests earn their place — full coverage on `gate/` and schedule math already exists; this module's tests target the new control-flow (429 fallback, double-start guard, recovery-trigger-once) rather than trying to unit-test the SSE wire format or visual design, which get verified by hand in a real browser per the final task.

---

## File Structure

| File | Responsibility |
|---|---|
| `agent/subagents/planner.py` (modify) | `ProvisioningResult` gains the alert's threshold/window/annotation/URL so the console can show "Burn-rate alert armed at 1.35x/10m" without re-deciding it. |
| `agent/root.py` (modify) | `RecoveryCycleResult` gains `live: bool`; `run_recovery_cycle` catches 429 around `observe()` and `replan()` independently, falling back to `data/cached_recovery.json`. |
| `data/cached_provisioning.json` (new, generated) | Committed fallback `ProvisioningResult` from a real run. |
| `data/cached_recovery.json` (new, generated) | Committed fallback `RecoveryCycleResult` from a real, live recovery cycle. |
| `server/__init__.py` (new) | Empty package marker. |
| `server/state.py` (new) | `AppState` singleton (lock, run_id, status, subscribers) and the `DaySnapshot` wire schema. |
| `server/provisioning_cache.py` (new) | Read/write `data/cached_provisioning.json`. |
| `server/replay.py` (new) | Background-thread replay loop; builds `DaySnapshot`s; triggers the recovery cycle exactly once per at-risk run. |
| `server/app.py` (new) | FastAPI app: boot-time provisioning with cache fallback, `POST /api/day/start`, `GET /api/day/stream`, static hosting of `web/dist`. |
| `pyproject.toml` (modify) | Add `fastapi`, `uvicorn[standard]`; include `server*` in packaging. |
| `tests/test_provisioning.py` (modify) | Update `test_provisioning_result_parses` for the new required fields. |
| `tests/test_root.py` (new) | 429 fallback behaviour for `run_recovery_cycle`. |
| `tests/test_state.py` (new) | `AppState` start/claim/publish semantics. |
| `tests/test_replay.py` (new) | Pure snapshot-building helpers in `server/replay.py`. |
| `tests/test_app.py` (new) | `POST /api/day/start` 200/409, initial snapshot shape. |
| `.gitignore` (modify) | Exempt `web/dist/` from the blanket `dist/` rule. |
| `web/` (new Vite project) | React 19 + TS + Tailwind v4 console; `web/dist` committed. |

**Interfaces every task can rely on:**
- `agent.root.run_recovery_cycle(day: ShootingDay) -> RecoveryCycleResult` (now with `.live: bool`).
- `agent.root.AT_RISK_ERROR_BUDGET_CONSUMED: float` (already public, `0.75`).
- `agent.subagents.planner.provision(day: ShootingDay) -> ProvisioningResult` (now with `.alert_rule_url`, `.burn_rate_threshold`, `.evaluation_window_minutes`, `.annotation`).
- `emitter.simulator.build_day(scenario_name) -> ShootingDay`, `load_scenario(name) -> dict`, `replay_day(day, scenario, speed_factor=480, on_event=None, dry_run=False) -> None`.
- `emitter.schedule.error_budget_consumed(day, now) -> float`, `.burn_rate(day, now) -> float`, `.projected_wrap(day, now) -> datetime`.
- `server.state.STATE: AppState`, `server.state.DaySnapshot`, `server.state.ProvisioningSnapshot`, `server.state.RecoverySnapshot`, `server.state.SceneSnapshot`.
- `server.replay.start_replay(scenario_name: str) -> int | None`, `server.replay.scene_snapshots(day) -> list[SceneSnapshot]`.

---

## Task 1: Add FastAPI/uvicorn to the project

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add the dependencies**

Edit the `dependencies` list in `pyproject.toml` to add, after `"google-adk[mcp]==2.8.0",`:

```toml
    "fastapi==0.141.1",
    "uvicorn[standard]==0.52.4",
```

Edit `[tool.setuptools.packages.find]` to read:

```toml
[tool.setuptools.packages.find]
include = ["emitter*", "agent*", "gate*", "server*"]
```

- [ ] **Step 2: Sync**

Run: `uv sync`
Expected: resolves and installs cleanly (both packages are already present transitively, so this should be fast).

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "build: add fastapi and uvicorn for the Module 6 console server"
```

---

## Task 2: Extend `ProvisioningResult` with the alert's decided threshold

**Files:**
- Modify: `agent/subagents/planner.py`
- Modify: `scripts/provision.py`
- Modify: `tests/test_provisioning.py`

**Interfaces:**
- Produces: `ProvisioningResult.alert_rule_url: str`, `.burn_rate_threshold: float`, `.evaluation_window_minutes: int`, `.annotation: str` — all required, all populated by `provision()`.

- [ ] **Step 1: Update the failing test first**

In `tests/test_provisioning.py`, replace `test_provisioning_result_parses`:

```python
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
```

- [ ] **Step 2: Run it to see it fail**

Run: `uv run pytest tests/test_provisioning.py::test_provisioning_result_parses -v`
Expected: FAIL — `ProvisioningResult` doesn't accept `alert_rule_url` etc. yet (extra-field or missing-argument error, depending on Pydantic's default `model_config`).

- [ ] **Step 3: Extend `ProvisioningResult` and `provision()`**

In `agent/subagents/planner.py`, replace the `ProvisioningResult` class:

```python
class ProvisioningResult(BaseModel):
    dashboard_uid: str
    dashboard_url: str
    alert_rule_uid: str
    alert_rule_url: str
    burn_rate_threshold: float
    evaluation_window_minutes: int
    annotation: str
    provisioned_at: datetime
```

Replace the `provision()` function body:

```python
async def provision(day: ShootingDay) -> ProvisioningResult:
    """Provisions Grafana for one shooting day: dashboard, then burn-rate alert."""
    plan = await _decide_monitoring_plan(day)

    dashboard_uid = await provision_day_dashboard(day)
    alert_rule_uid = await provision_burn_rate_alert(
        day, plan.burn_rate_threshold, plan.evaluation_window_minutes, plan.annotation
    )

    return ProvisioningResult(
        dashboard_uid=dashboard_uid,
        dashboard_url=f"{GRAFANA_URL.rstrip('/')}/d/{dashboard_uid}",
        alert_rule_uid=alert_rule_uid,
        alert_rule_url=f"{GRAFANA_URL.rstrip('/')}/alerting/grafana/{alert_rule_uid}/view",
        burn_rate_threshold=plan.burn_rate_threshold,
        evaluation_window_minutes=plan.evaluation_window_minutes,
        annotation=plan.annotation,
        provisioned_at=datetime.now(timezone.utc),
    )
```

- [ ] **Step 4: Run the test again**

Run: `uv run pytest tests/test_provisioning.py -v`
Expected: PASS, all tests in the file.

- [ ] **Step 5: Update the CLI script's output to show the new fields**

In `scripts/provision.py`, after the `alert rule uid` print line, add:

```python
    print(f"  burn-rate alert : armed at {result.burn_rate_threshold}x/{result.evaluation_window_minutes}m")
    print(f"  annotation      : {result.annotation}")
```

- [ ] **Step 6: Commit**

```bash
git add agent/subagents/planner.py scripts/provision.py tests/test_provisioning.py
git commit -m "feat: carry the planner's decided alert threshold on ProvisioningResult"
```

---

## Task 3: 429 fallback for the recovery cycle

**Files:**
- Modify: `agent/root.py`
- Create: `tests/test_root.py`

**Interfaces:**
- Consumes: `agent.subagents.observer.observe`, `agent.subagents.replanner.replan` (both already imported by name into `agent.root`'s module namespace, so monkeypatching `agent.root.observe` / `agent.root.replan` works).
- Produces: `RecoveryCycleResult.live: bool`, `agent.root._CACHED_RECOVERY_PATH: Path` (test-overridable).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_root.py`:

```python
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
```

- [ ] **Step 2: Run to see them fail**

Run: `uv run pytest tests/test_root.py -v`
Expected: FAIL — `RecoveryCycleResult` has no `live` field yet, and no 429 handling exists.

- [ ] **Step 3: Implement the fallback in `agent/root.py`**

Add imports at the top of `agent/root.py`:

```python
import json
from pathlib import Path

from google.genai.errors import ClientError
```

Add near the top-level constants:

```python
_CACHED_RECOVERY_PATH = Path(__file__).parent.parent / "data" / "cached_recovery.json"
```

Replace `RecoveryCycleResult`:

```python
class RecoveryCycleResult(BaseModel):
    observation: DayObservation
    options: list[RecoveryOption]
    verdicts: list[GateVerdict]
    incident_id: str | None = None
    live: bool = True
```

Add, after `_incident_summary`:

```python
def _load_cached_recovery_cycle() -> RecoveryCycleResult:
    """Falls back to a committed real run's recovery cycle when Gemini's
    daily quota is exhausted -- confirmed live on this project's own
    free-tier key. Always reports live=False here regardless of what the
    committed fixture itself says, since reaching this function always
    means the live call just failed.
    """
    payload = json.loads(_CACHED_RECOVERY_PATH.read_text())
    result = RecoveryCycleResult.model_validate(payload)
    return result.model_copy(update={"live": False})
```

Replace `run_recovery_cycle`:

```python
async def run_recovery_cycle(day: ShootingDay) -> RecoveryCycleResult:
    """Runs one full observe -> replan -> gate -> incident cycle.

    Falls back to a cached, previously-real recovery cycle if Gemini's
    daily free-tier quota is exhausted (HTTP 429) during either the
    observe or replan call. Any other error is not swallowed here.
    """
    try:
        observation = await observe(day.day_number)
    except ClientError as exc:
        if exc.code == 429:
            return _load_cached_recovery_cycle()
        raise

    try:
        options = await replan(day, observation)
    except ClientError as exc:
        if exc.code == 429:
            return _load_cached_recovery_cycle()
        raise

    verdicts = [check(day, option) for option in options]

    incident_id = None
    if _day_at_risk(observation) and any(verdict.approved for verdict in verdicts):
        incident_id = await open_day_incident(day, observation, _incident_summary(options, verdicts))

    return RecoveryCycleResult(
        observation=observation, options=options, verdicts=verdicts, incident_id=incident_id, live=True
    )
```

- [ ] **Step 4: Run the tests again**

Run: `uv run pytest tests/test_root.py -v`
Expected: PASS, all three.

- [ ] **Step 5: Run the full suite to check nothing else broke**

Run: `uv run pytest -q`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add agent/root.py tests/test_root.py
git commit -m "feat: fall back to a cached recovery cycle when Gemini's quota is exhausted"
```

---

## Task 4: Generate the two committed cache fixtures for real

This is a data-generation step against your live Grafana Cloud stack and Gemini key, not new application code — there is nothing to TDD here. Do this after Tasks 2 and 3 are committed, since it uses their new fields.

**Files:**
- Create (generated, then committed as-is): `data/cached_provisioning.json`
- Create (generated, then committed as-is): `data/cached_recovery.json`

- [ ] **Step 1: Generate a real provisioning result**

```bash
uv run python3 -c "
import asyncio
from pathlib import Path
from agent.subagents.planner import provision
from emitter.simulator import build_day

day = build_day('slipping')
result = asyncio.run(provision(day))
Path('data').mkdir(exist_ok=True)
Path('data/cached_provisioning.json').write_text(result.model_dump_json(indent=2))
print(result.model_dump_json(indent=2))
"
```

Confirm the printed JSON has real-looking `dashboard_url` / `alert_rule_url` values (your actual Grafana Cloud stack URL) and no error was raised.

- [ ] **Step 2: Push a real slipping-day replay into Grafana so the day has something to observe**

```bash
uv run python3 scripts/run_emitter.py --scenario slipping --speed 2000
```

Let it run to completion (a few seconds at this speed). This is what makes the next step's `observe()` call see a day that is actually at risk.

- [ ] **Step 3: Generate a real recovery cycle from that state**

```bash
uv run python3 -c "
import asyncio
from pathlib import Path
from agent.root import run_recovery_cycle
from emitter.simulator import build_day

day = build_day('slipping')
result = asyncio.run(run_recovery_cycle(day))
Path('data/cached_recovery.json').write_text(result.model_dump_json(indent=2))
print(result.model_dump_json(indent=2))
"
```

Confirm: `live` is `true`, `options` has exactly two entries, at least one `verdicts` entry has `approved: false` with a non-empty `violations` list (the turnaround rejection this whole project is built around), and `incident_id` is set (likely `"annotation:<n>"` per `agent/tools/provisioning.py`'s documented fallback on this project's free-tier stack).

If any of those aren't true (e.g. the day didn't read as at-risk, or the gate approved everything), re-run Step 2 and Step 3 — do not hand-edit the JSON. The turnaround violation must be real, per `CLAUDE.md`'s non-negotiable invariant.

- [ ] **Step 4: Commit both fixtures**

```bash
git add data/cached_provisioning.json data/cached_recovery.json
git commit -m "chore: commit real provisioning and recovery-cycle fixtures for offline fallback"
```

---

## Task 5: `server/state.py` — the shared state singleton and wire schema

**Files:**
- Create: `server/__init__.py`
- Create: `server/state.py`
- Create: `tests/test_state.py`

**Interfaces:**
- Produces: `Status`, `EventType`, `DEFAULT_SCENARIO`, `TOTAL_SHOOT_DAYS`, `ProvisioningSnapshot`, `RecoverySnapshot`, `SceneSnapshot`, `DaySnapshot`, `AppState` (with `.lock`, `.run_id`, `.status`, `.plan_day`, `.provisioning`, `.recovery`, `.last_snapshot`, `.subscribe()`, `.unsubscribe()`, `.publish()`, `.try_start()`, `.try_claim_recovery()`, `.is_current()`), `STATE: AppState`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_state.py`:

```python
"""Tests for the concurrency guards in server/state.py (Module 6).

These are the guards the corrections called out explicitly: a second
POST /api/day/start (or a race with a page refresh) must never start a
second replay thread, and a recovery cycle must never fire twice for
the same run.
"""

from __future__ import annotations

from server.state import AppState, DaySnapshot


def test_try_start_returns_run_id_then_blocks_while_running():
    state = AppState()

    first = state.try_start()
    assert first == 1
    assert state.status == "running"

    assert state.try_start() is None

    state.status = "wrapped"
    second = state.try_start()
    assert second == 2


def test_try_claim_recovery_only_succeeds_once_per_run():
    state = AppState()
    run_id = state.try_start()

    assert state.try_claim_recovery(run_id) is True
    assert state.try_claim_recovery(run_id) is False


def test_try_claim_recovery_rejects_a_superseded_run_id():
    state = AppState()
    old_run_id = state.try_start()
    state.status = "wrapped"
    new_run_id = state.try_start()

    assert new_run_id != old_run_id
    assert state.try_claim_recovery(old_run_id) is False
    assert state.try_claim_recovery(new_run_id) is True


def test_publish_delivers_to_subscribers_and_records_last_snapshot():
    state = AppState()
    q = state.subscribe()
    snapshot = DaySnapshot(
        run_id=1,
        event_type="connected",
        status="idle",
        day_number=14,
        production_title="Invented Production",
        scenes=[],
    )

    state.publish(snapshot)

    assert q.get_nowait() is snapshot
    assert state.last_snapshot is snapshot


def test_unsubscribe_stops_delivery():
    state = AppState()
    q = state.subscribe()
    state.unsubscribe(q)

    state.publish(
        DaySnapshot(
            run_id=1, event_type="connected", status="idle",
            day_number=14, production_title="Invented Production", scenes=[],
        )
    )

    assert q.empty()
```

- [ ] **Step 2: Run to see them fail**

Run: `uv run pytest tests/test_state.py -v`
Expected: FAIL — `server` package doesn't exist yet.

- [ ] **Step 3: Create the package and implement `state.py`**

Create `server/__init__.py` (empty file).

Create `server/state.py`:

```python
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


class AppState:
    """Guards everything the replay thread and the API handlers share."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.run_id = 0
        self.status: Status = "idle"
        self.plan_day: ShootingDay = build_day(DEFAULT_SCENARIO)
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
```

- [ ] **Step 4: Run the tests again**

Run: `uv run pytest tests/test_state.py -v`
Expected: PASS, all five.

- [ ] **Step 5: Commit**

```bash
git add server/__init__.py server/state.py tests/test_state.py
git commit -m "feat: add AppState — the console server's shared, lock-guarded state"
```

---

## Task 6: `server/provisioning_cache.py`

**Files:**
- Create: `server/provisioning_cache.py`
- Create: `tests/test_provisioning_cache.py`

**Interfaces:**
- Produces: `save_cached_provisioning(result: ProvisioningResult) -> None`, `load_cached_provisioning() -> ProvisioningResult | None`, `CACHE_PATH: Path`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_provisioning_cache.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone

from agent.subagents.planner import ProvisioningResult
from server import provisioning_cache


def _result() -> ProvisioningResult:
    return ProvisioningResult(
        dashboard_uid="martini-day-14",
        dashboard_url="https://example.grafana.net/d/martini-day-14",
        alert_rule_uid="abc123",
        alert_rule_url="https://example.grafana.net/alerting/grafana/abc123/view",
        burn_rate_threshold=1.35,
        evaluation_window_minutes=10,
        annotation="Losing time against Scene 42.",
        provisioned_at=datetime.now(timezone.utc),
    )


def test_round_trips_through_disk(tmp_path, monkeypatch):
    monkeypatch.setattr(provisioning_cache, "CACHE_PATH", tmp_path / "cached_provisioning.json")

    provisioning_cache.save_cached_provisioning(_result())
    loaded = provisioning_cache.load_cached_provisioning()

    assert loaded is not None
    assert loaded.dashboard_uid == "martini-day-14"
    assert loaded.burn_rate_threshold == 1.35


def test_returns_none_when_no_cache_exists(tmp_path, monkeypatch):
    monkeypatch.setattr(provisioning_cache, "CACHE_PATH", tmp_path / "missing.json")

    assert provisioning_cache.load_cached_provisioning() is None
```

- [ ] **Step 2: Run to see it fail**

Run: `uv run pytest tests/test_provisioning_cache.py -v`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement it**

Create `server/provisioning_cache.py`:

```python
"""Disk cache for the boot-time Grafana provisioning result (Module 6).

Written once, on a successful live provision. Read back only when a
live provision attempt fails at startup (quota, network, cold start on
the host) so the console can still show a real dashboard/alert link
and keep running, instead of returning 503 and hiding the provisioning
log.
"""

from __future__ import annotations

from pathlib import Path

from agent.subagents.planner import ProvisioningResult

CACHE_PATH = Path(__file__).parent.parent / "data" / "cached_provisioning.json"


def save_cached_provisioning(result: ProvisioningResult) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(result.model_dump_json(indent=2))


def load_cached_provisioning() -> ProvisioningResult | None:
    if not CACHE_PATH.exists():
        return None
    return ProvisioningResult.model_validate_json(CACHE_PATH.read_text())
```

- [ ] **Step 4: Run the tests again**

Run: `uv run pytest tests/test_provisioning_cache.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add server/provisioning_cache.py tests/test_provisioning_cache.py
git commit -m "feat: cache boot-time Grafana provisioning to disk"
```

---

## Task 7: `server/replay.py` — snapshot builders (pure-function slice)

This task covers only the pure, testable helpers. The thread orchestration that calls them lands in Task 8, since it depends on this file existing but isn't itself unit-testable without a live Grafana/Gemini stack (it's covered by Task 11's manual browser verification instead).

**Files:**
- Create: `server/replay.py`
- Create: `tests/test_replay.py`

**Interfaces:**
- Consumes: `server.state.STATE`, `DaySnapshot`, `SceneSnapshot`, `RecoverySnapshot`.
- Produces: `scene_snapshots(day: ShootingDay) -> list[SceneSnapshot]`, `shot_scene_numbers(day: ShootingDay) -> list[str]`, `incident_url(dashboard_url: str, incident_id: str | None) -> str | None` — all consumed by Task 8 and by `server/app.py`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_replay.py`:

```python
"""Tests for the pure snapshot-building helpers in server/replay.py.

The thread-orchestration half of this module (run_replay,
start_replay) needs a live Grafana/Gemini stack to exercise
meaningfully and is covered by manual browser verification instead
(Task 11) -- these tests cover the parts that are pure functions of a
ShootingDay.
"""

from __future__ import annotations

from emitter.simulator import build_day
from server.replay import incident_url, scene_snapshots, shot_scene_numbers


def test_scene_snapshots_are_in_shooting_order_with_cast_names():
    day = build_day("nominal")

    snapshots = scene_snapshots(day)

    numbers = [s.number for s in snapshots]
    assert numbers[0] == "1"
    scene_1 = next(s for s in snapshots if s.number == "1")
    assert scene_1.cast_names == ["MARCUS", "ELENA"]
    assert scene_1.strip_color == "day-int"
    assert scene_1.page_eighths_display == "4/8"


def test_shot_scene_numbers_empty_before_any_setup_completes():
    day = build_day("nominal")

    assert shot_scene_numbers(day) == []


def test_shot_scene_numbers_reports_a_scene_once_all_its_setups_complete():
    day = build_day("nominal")
    for setup in day.setups:
        if setup.scene_number == "1":
            setup.actual_minutes = 20
            setup.takes = 2

    assert shot_scene_numbers(day) == ["1"]


def test_incident_url_links_the_dashboard_for_the_annotation_fallback():
    assert (
        incident_url("https://example.grafana.net/d/martini-day-14", "annotation:42")
        == "https://example.grafana.net/d/martini-day-14"
    )


def test_incident_url_links_the_incident_app_for_a_real_incident():
    url = incident_url("https://example.grafana.net/d/martini-day-14", "IID-1")
    assert url == "https://example.grafana.net/a/grafana-incident-app/incidents/IID-1"


def test_incident_url_is_none_without_an_incident():
    assert incident_url("https://example.grafana.net/d/martini-day-14", None) is None
```

- [ ] **Step 2: Run to see them fail**

Run: `uv run pytest tests/test_replay.py -v`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement `server/replay.py`**

```python
"""Background replay + server-side recovery trigger (Module 6).

Runs one shooting day's replay (emitter/simulator.py) on a dedicated
thread, publishing a DaySnapshot to every SSE subscriber after each
event. The instant the day's local error-budget reading crosses
agent.root.AT_RISK_ERROR_BUDGET_CONSUMED, this same thread -- and only
this thread, guarded by AppState.try_claim_recovery -- runs the full
observe -> replan -> gate -> incident cycle and publishes its result.
The console never triggers this itself; it only ever renders what
arrives over SSE.
"""

from __future__ import annotations

import asyncio
import threading
from datetime import datetime

from agent.config import GRAFANA_URL
from agent.root import AT_RISK_ERROR_BUDGET_CONSUMED, run_recovery_cycle
from emitter import schedule
from emitter.models import ShootingDay
from emitter.simulator import build_day, load_scenario, replay_day
from server.state import STATE, DaySnapshot, EventType, RecoverySnapshot, SceneSnapshot, Status


def _cast_names(day: ShootingDay, cast_ids: list[str]) -> list[str]:
    performers_by_id = {p.id: p for p in day.performers}
    return [performers_by_id[cid].character_name if cid in performers_by_id else cid for cid in cast_ids]


def _scene_shooting_order(day: ShootingDay) -> list[str]:
    seen: list[str] = []
    for setup in day.setups:
        if setup.scene_number not in seen:
            seen.append(setup.scene_number)
    return seen


def scene_snapshots(day: ShootingDay) -> list[SceneSnapshot]:
    """day.scenes as the strip board renders them: shooting order first,
    then any scene with no setup yet at the end, same fallback as
    agent/subagents/replanner.py's _scene_shooting_order."""
    order = _scene_shooting_order(day)
    scenes_by_number = {s.number: s for s in day.scenes}
    ordered_numbers = order + [s.number for s in day.scenes if s.number not in order]
    return [
        SceneSnapshot(
            number=scenes_by_number[number].number,
            synopsis=scenes_by_number[number].synopsis,
            page_eighths_display=str(scenes_by_number[number].page_eighths),
            strip_color=scenes_by_number[number].strip_color,
            cast_names=_cast_names(day, scenes_by_number[number].cast_ids),
        )
        for number in ordered_numbers
    ]


def shot_scene_numbers(day: ShootingDay) -> list[str]:
    setups_by_scene: dict[str, list] = {}
    for setup in day.setups:
        setups_by_scene.setdefault(setup.scene_number, []).append(setup)
    return [
        number
        for number in _scene_shooting_order(day)
        if all(s.is_complete for s in setups_by_scene[number])
    ]


def incident_url(dashboard_url: str, incident_id: str | None) -> str | None:
    """Links a Grafana incident, or falls back to the dashboard the
    annotation was written to when the incident-app tool is unavailable
    -- confirmed the normal path on this project's own free-tier stack
    (see agent/tools/provisioning.py's open_day_incident)."""
    if incident_id is None:
        return None
    if incident_id.startswith("annotation:"):
        return dashboard_url
    return f"{GRAFANA_URL.rstrip('/')}/a/grafana-incident-app/incidents/{incident_id}"


def _base_snapshot(day: ShootingDay, run_id: int, status: Status, event_type: EventType, *, error_message: str | None = None) -> DaySnapshot:
    with STATE.lock:
        provisioning = STATE.provisioning
        recovery = STATE.recovery
    return DaySnapshot(
        run_id=run_id,
        event_type=event_type,
        status=status,
        error_message=error_message,
        day_number=day.day_number,
        production_title=day.production_title,
        provisioning=provisioning,
        scenes=scene_snapshots(day),
        shot_scene_numbers=shot_scene_numbers(day),
        recovery=recovery,
    )


def _tick_snapshot(day: ShootingDay, run_id: int, status: Status, event: dict) -> DaySnapshot:
    now: datetime = event["now"]
    snapshot = _base_snapshot(day, run_id, status, event["type"])
    snapshot.current_scene = event.get("scene")
    snapshot.clock = now.strftime("%H:%M")
    snapshot.pages_completed_eighths = event["pages_completed_eighths"]
    snapshot.pages_remaining_eighths = event["pages_remaining_eighths"]
    snapshot.total_page_eighths = day.total_page_eighths.eighths
    snapshot.setups_completed = event["setups_completed"]
    snapshot.setups_total = event["setups_total"]
    snapshot.error_budget_consumed = schedule.error_budget_consumed(day, now)
    snapshot.burn_rate = schedule.burn_rate(day, now)
    snapshot.projected_wrap = schedule.projected_wrap(day, now).strftime("%H:%M")
    return snapshot


def _trigger_recovery_if_at_risk(day: ShootingDay, run_id: int, now: datetime) -> None:
    if schedule.error_budget_consumed(day, now) < AT_RISK_ERROR_BUDGET_CONSUMED:
        return
    if not STATE.try_claim_recovery(run_id):
        return

    with STATE.lock:
        STATE.status = "at_risk"

    cycle_result = asyncio.run(run_recovery_cycle(day))

    with STATE.lock:
        provisioning = STATE.provisioning
    dashboard_url = provisioning.info.dashboard_url if provisioning else ""
    recovery = RecoverySnapshot(
        result=cycle_result, incident_url=incident_url(dashboard_url, cycle_result.incident_id)
    )

    with STATE.lock:
        if STATE.run_id != run_id:
            return
        STATE.recovery = recovery

    STATE.publish(_base_snapshot(day, run_id, "at_risk", "recovery"))


def run_replay(scenario_name: str, run_id: int) -> None:
    """The background thread body for one Start click. Owns `day` exclusively."""
    day = build_day(scenario_name)
    with STATE.lock:
        STATE.plan_day = day
    scenario = load_scenario(scenario_name)

    def on_event(event: dict) -> None:
        if not STATE.is_current(run_id):
            return
        _trigger_recovery_if_at_risk(day, run_id, event["now"])
        if not STATE.is_current(run_id):
            return
        status: Status = "at_risk" if STATE.status == "at_risk" else "running"
        STATE.publish(_tick_snapshot(day, run_id, status, event))

    try:
        replay_day(day, scenario, on_event=on_event)
    except Exception as exc:  # noqa: BLE001 -- surfaced to the console, not silently dropped
        if STATE.is_current(run_id):
            with STATE.lock:
                STATE.status = "error"
            STATE.publish(_base_snapshot(day, run_id, "error", "error", error_message=str(exc)))
        return

    if STATE.is_current(run_id):
        with STATE.lock:
            STATE.status = "wrapped"
        STATE.publish(_base_snapshot(day, run_id, "wrapped", "wrapped"))


def start_replay(scenario_name: str) -> int | None:
    """Claims a new run and starts its replay thread. None if one is already running."""
    run_id = STATE.try_start()
    if run_id is None:
        return None
    thread = threading.Thread(target=run_replay, args=(scenario_name, run_id), daemon=True)
    thread.start()
    return run_id
```

- [ ] **Step 4: Run the tests again**

Run: `uv run pytest tests/test_replay.py -v`
Expected: PASS, all six.

- [ ] **Step 5: Run the full backend suite**

Run: `uv run pytest -q`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add server/replay.py tests/test_replay.py
git commit -m "feat: background replay thread that triggers recovery exactly once per at-risk run"
```

---

## Task 8: `server/app.py` — FastAPI endpoints

**Files:**
- Create: `server/app.py`
- Create: `tests/test_app.py`

**Interfaces:**
- Produces: `app: FastAPI` (ASGI app `server.app:app`, run via `uvicorn`).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_app.py`:

```python
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


def test_initial_snapshot_falls_back_to_provisioning_state():
    with STATE.lock:
        from server.state import ProvisioningSnapshot

        STATE.provisioning = ProvisioningSnapshot(info=_fake_provisioning_result(), live=False)

    snapshot = app_module._initial_snapshot()

    assert snapshot.provisioning is not None
    assert snapshot.provisioning.live is False
```

- [ ] **Step 2: Run to see them fail**

Run: `uv run pytest tests/test_app.py -v`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement `server/app.py`**

```python
"""FastAPI app for the MARTINI console (Module 6).

Serves the SSE stream the React console renders, the one action it can
take (start a replay), and the built static console itself. Recovery
is never triggered from here -- server/replay.py's background thread
does that the instant the day goes at risk; this module only starts
that thread and relays what it publishes.
"""

from __future__ import annotations

import asyncio
import queue
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

load_dotenv()

from agent.subagents.planner import provision  # noqa: E402 -- after load_dotenv()
from emitter.simulator import build_day  # noqa: E402
from server.provisioning_cache import load_cached_provisioning, save_cached_provisioning  # noqa: E402
from server.replay import scene_snapshots, start_replay  # noqa: E402
from server.state import DEFAULT_SCENARIO, STATE, DaySnapshot, ProvisioningSnapshot  # noqa: E402

_WEB_DIST = Path(__file__).parent.parent / "web" / "dist"
_QUEUE_TIMEOUT_SECONDS = 15.0
_VALID_SCENARIOS = {"nominal", "slipping"}


async def _provision_at_startup() -> None:
    day = build_day(DEFAULT_SCENARIO)
    try:
        result = await provision(day)
    except Exception as exc:
        print(f"martini: live provisioning failed at startup ({exc}); falling back to cache.")
        cached = load_cached_provisioning()
        if cached is None:
            print("martini: no cached provisioning available -- the console will show it as unavailable.")
            return
        with STATE.lock:
            STATE.provisioning = ProvisioningSnapshot(info=cached, live=False)
        return

    save_cached_provisioning(result)
    with STATE.lock:
        STATE.provisioning = ProvisioningSnapshot(info=result, live=True)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await _provision_at_startup()
    yield


app = FastAPI(lifespan=lifespan)


def _sse_format(snapshot: DaySnapshot) -> str:
    return f"data: {snapshot.model_dump_json()}\n\n"


def _initial_snapshot() -> DaySnapshot:
    with STATE.lock:
        if STATE.last_snapshot is not None:
            return STATE.last_snapshot
        day = STATE.plan_day
        provisioning = STATE.provisioning
        run_id = STATE.run_id
    return DaySnapshot(
        run_id=run_id,
        event_type="connected",
        status="idle",
        day_number=day.day_number,
        production_title=day.production_title,
        provisioning=provisioning,
        scenes=scene_snapshots(day),
        total_page_eighths=day.total_page_eighths.eighths,
        setups_total=day.total_setups,
    )


def _drain(q: "queue.Queue[DaySnapshot]") -> DaySnapshot | None:
    try:
        return q.get(timeout=_QUEUE_TIMEOUT_SECONDS)
    except queue.Empty:
        return None


@app.get("/api/day/stream")
async def stream(request: Request) -> StreamingResponse:
    async def event_stream():
        q = STATE.subscribe()
        try:
            yield _sse_format(_initial_snapshot())
            while True:
                if await request.is_disconnected():
                    break
                item = await asyncio.to_thread(_drain, q)
                yield _sse_format(item) if item is not None else ": keepalive\n\n"
        finally:
            STATE.unsubscribe(q)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/api/day/start")
async def start_day(scenario: str = DEFAULT_SCENARIO) -> JSONResponse:
    if scenario not in _VALID_SCENARIOS:
        return JSONResponse({"detail": "unknown scenario"}, status_code=422)

    run_id = start_replay(scenario)
    if run_id is None:
        return JSONResponse({"detail": "a day is already running"}, status_code=409)
    return JSONResponse({"run_id": run_id})


if _WEB_DIST.exists():
    app.mount("/", StaticFiles(directory=_WEB_DIST, html=True), name="console")
```

- [ ] **Step 4: Run the tests again**

Run: `uv run pytest tests/test_app.py -v`
Expected: PASS, all six.

- [ ] **Step 5: Run the full backend suite**

Run: `uv run pytest -q`
Expected: all green. The backend half of Module 6 is now complete and independently testable.

- [ ] **Step 6: Commit**

```bash
git add server/app.py tests/test_app.py
git commit -m "feat: FastAPI console server — SSE stream, guarded start, static hosting"
```

---

## Task 9: Scaffold the Vite + React 19 + TypeScript + Tailwind v4 project

**Files:**
- Create: `web/` (via `npm create vite@latest`)
- Modify: `.gitignore`

- [ ] **Step 1: Scaffold**

```bash
npm create vite@latest web -- --template react-ts
cd web && npm install
```

- [ ] **Step 2: Add Tailwind v4's Vite plugin**

```bash
npm install tailwindcss @tailwindcss/vite
```

- [ ] **Step 3: Wire the plugin into Vite, with a dev proxy to the FastAPI server**

Replace `web/vite.config.ts`:

```ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});
```

- [ ] **Step 4: Exempt `web/dist` from the blanket `dist/` ignore rule**

In `.gitignore`, after the existing `web/node_modules/` line, add:

```
!web/dist/
```

- [ ] **Step 5: Confirm the scaffold builds**

Run: `cd web && npm run build`
Expected: succeeds, produces `web/dist/index.html` and hashed assets.

- [ ] **Step 6: Commit**

```bash
git add web/package.json web/package-lock.json web/vite.config.ts web/tsconfig*.json web/index.html web/src web/public web/.gitignore .gitignore
git commit -m "chore: scaffold the Module 6 console with Vite, React 19, and Tailwind v4"
```

Do not add `web/dist` yet — it doesn't reflect the real console until Task 13.

---

## Task 10: Palette, type, and the one motion moment (theme layer)

**Files:**
- Modify: `web/src/index.css`
- Modify: `web/index.html`
- Delete: `web/src/App.css` (Vite's default template styling; the console defines its own)

- [ ] **Step 1: Replace `web/src/index.css`**

```css
@import "tailwindcss";

@theme {
  --color-board: #1c1a17;
  --color-paper: #f2ede3;
  --color-ink: #16150f;
  --color-strip-day-int: #ffffff;
  --color-strip-day-ext: #f5d547;
  --color-strip-night-int: #7fa8d9;
  --color-strip-night-ext: #7bae7f;
  --color-burn: #c2452d;

  --font-narrow: "Archivo Narrow", sans-serif;
  --font-body: "Inter", sans-serif;
}

body {
  margin: 0;
  background-color: var(--color-board);
  color: var(--color-paper);
  font-family: var(--font-body);
}

:focus-visible {
  outline: 3px solid var(--color-strip-day-ext);
  outline-offset: 2px;
}

@keyframes pulse-strip {
  0%,
  100% {
    box-shadow: 0 0 0 0 rgba(242, 237, 227, 0.55);
  }
  50% {
    box-shadow: 0 0 0 6px rgba(242, 237, 227, 0);
  }
}

.strip-current {
  animation: pulse-strip 1.6s ease-in-out infinite;
}

@media (prefers-reduced-motion: reduce) {
  .strip-current {
    animation: none;
  }
  * {
    transition-duration: 0.001ms !important;
  }
}
```

- [ ] **Step 2: Delete the default template stylesheet**

```bash
rm web/src/App.css
```

(Remove its `import "./App.css"` line from `web/src/App.tsx` too — Task 12 replaces `App.tsx` wholesale anyway.)

- [ ] **Step 3: Load the two fonts and set the tab title**

Replace `web/index.html`:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link
      href="https://fonts.googleapis.com/css2?family=Archivo+Narrow:wght@500;600;700&family=Inter:wght@400;500;600&display=swap"
      rel="stylesheet"
    />
    <title>MARTINI — Day 14</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 4: Confirm it still builds**

Run: `cd web && npm run build`
Expected: succeeds (component code still references the old template for now; Task 12 replaces it).

- [ ] **Step 5: Commit**

```bash
git add web/src/index.css web/index.html
git rm web/src/App.css
git commit -m "style: strip-board palette, Archivo Narrow / Inter, and the one motion moment"
```

---

## Task 11: Types, the SSE hook, and the start action

**Files:**
- Create: `web/src/types.ts`
- Create: `web/src/api.ts`
- Create: `web/src/hooks/useDaySnapshot.ts`

**Interfaces:**
- Produces: `DaySnapshot`, `Status`, `SceneSnapshot`, `RecoverySnapshot`, `GateVerdict`, `RecoveryOption` (TS types mirroring `server/state.py`'s Pydantic models field-for-field); `useDaySnapshot(): DaySnapshot | null`; `startDay(): Promise<{ ok: true } | { ok: false; status: number }>`.

- [ ] **Step 1: `web/src/types.ts`**

```ts
export type Status = "idle" | "running" | "at_risk" | "wrapped" | "error";

export type EventType =
  | "connected"
  | "day_start"
  | "setup_wrapped"
  | "scene_wrapped"
  | "meal_break"
  | "recovery"
  | "wrapped"
  | "error";

export interface ProvisioningInfo {
  dashboard_uid: string;
  dashboard_url: string;
  alert_rule_uid: string;
  alert_rule_url: string;
  burn_rate_threshold: number;
  evaluation_window_minutes: number;
  annotation: string;
  provisioned_at: string;
}

export interface ProvisioningSnapshot {
  info: ProvisioningInfo;
  live: boolean;
}

export interface Violation {
  rule: "turnaround" | "meal" | "minors" | "crew_rest";
  performer_id: string | null;
  reason: string;
}

export interface GateVerdict {
  option_id: string;
  approved: boolean;
  violations: Violation[];
}

export interface RecoveryOption {
  id: string;
  kind: "reorder" | "drop_coverage" | "move_to_pickups" | "flip_to_cover_set";
  description: string;
  affected_scenes: string[];
  minutes_recovered: number;
}

export interface RecoveryCycleResult {
  options: RecoveryOption[];
  verdicts: GateVerdict[];
  incident_id: string | null;
  live: boolean;
}

export interface RecoverySnapshot {
  result: RecoveryCycleResult;
  incident_url: string | null;
}

export type StripColor = "day-int" | "day-ext" | "night-int" | "night-ext";

export interface SceneSnapshot {
  number: string;
  synopsis: string;
  page_eighths_display: string;
  strip_color: StripColor;
  cast_names: string[];
}

export interface DaySnapshot {
  run_id: number;
  event_type: EventType;
  status: Status;
  error_message: string | null;
  day_number: number;
  total_days: number;
  production_title: string;
  provisioning: ProvisioningSnapshot | null;
  scenes: SceneSnapshot[];
  current_scene: string | null;
  shot_scene_numbers: string[];
  clock: string | null;
  pages_completed_eighths: number;
  pages_remaining_eighths: number;
  total_page_eighths: number;
  setups_completed: number;
  setups_total: number;
  error_budget_consumed: number;
  burn_rate: number;
  projected_wrap: string | null;
  recovery: RecoverySnapshot | null;
}
```

- [ ] **Step 2: `web/src/api.ts`**

```ts
export async function startDay(): Promise<{ ok: true } | { ok: false; status: number }> {
  const response = await fetch("/api/day/start", { method: "POST" });
  if (response.ok) return { ok: true };
  return { ok: false, status: response.status };
}
```

- [ ] **Step 3: `web/src/hooks/useDaySnapshot.ts`**

```ts
import { useEffect, useRef, useState } from "react";
import type { DaySnapshot } from "../types";

/** Subscribes to the console's SSE stream. Ignores any event whose
 * run_id is behind the highest one already seen -- a stale event from
 * a superseded replay thread should never overwrite a newer run's
 * state on screen. */
export function useDaySnapshot(): DaySnapshot | null {
  const [snapshot, setSnapshot] = useState<DaySnapshot | null>(null);
  const latestRunId = useRef(0);

  useEffect(() => {
    const source = new EventSource("/api/day/stream");

    source.onmessage = (event) => {
      const next: DaySnapshot = JSON.parse(event.data);
      if (next.run_id < latestRunId.current) return;
      latestRunId.current = next.run_id;
      setSnapshot(next);
    };

    return () => source.close();
  }, []);

  return snapshot;
}
```

- [ ] **Step 4: Confirm it still builds**

Run: `cd web && npm run build`
Expected: succeeds — nothing imports these modules yet, but `tsc` should still type-check them cleanly.

- [ ] **Step 5: Commit**

```bash
git add web/src/types.ts web/src/api.ts web/src/hooks
git commit -m "feat: console types, SSE hook, and the start action"
```

---

## Task 12: The console UI

**Files:**
- Create: `web/src/components/ProvisioningLog.tsx`
- Create: `web/src/components/Header.tsx`
- Create: `web/src/components/ErrorBudgetBar.tsx`
- Create: `web/src/components/StripBoard.tsx`
- Create: `web/src/components/RecoveryOptions.tsx`
- Create: `web/src/components/StartButton.tsx`
- Modify: `web/src/App.tsx`
- Modify: `web/src/main.tsx`

- [ ] **Step 1: `web/src/components/ProvisioningLog.tsx`**

```tsx
import type { ProvisioningSnapshot } from "../types";

export function ProvisioningLog({ provisioning }: { provisioning: ProvisioningSnapshot | null }) {
  if (!provisioning) {
    return (
      <div className="border-b border-paper/10 px-4 py-2 font-body text-xs text-paper/50">
        Provisioning unavailable — no live Grafana connection and no cached run on record.
      </div>
    );
  }

  const { info, live } = provisioning;

  return (
    <div className="border-b border-paper/10 px-4 py-2 font-body text-xs leading-relaxed text-paper/70">
      <div>
        <a
          className="underline decoration-paper/40 hover:decoration-paper"
          href={info.dashboard_url}
          target="_blank"
          rel="noreferrer"
        >
          Dashboard
        </a>{" "}
        provisioned for today's shoot.
      </div>
      <div>
        <a
          className="underline decoration-paper/40 hover:decoration-paper"
          href={info.alert_rule_url}
          target="_blank"
          rel="noreferrer"
        >
          Burn-rate alert
        </a>{" "}
        armed at {info.burn_rate_threshold}x/{info.evaluation_window_minutes}m — {info.annotation}
      </div>
      {!live && (
        <div className="italic text-paper/50">
          Provisioning from a cached run — live Grafana connection unavailable at startup.
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: `web/src/components/Header.tsx`**

```tsx
import type { DaySnapshot, Status } from "../types";

const STATUS_LABEL: Record<Status, string> = {
  idle: "Standing by",
  running: "Shooting",
  at_risk: "Behind schedule",
  wrapped: "Wrapped",
  error: "Stalled",
};

export function Header({ snapshot }: { snapshot: DaySnapshot }) {
  return (
    <header className="flex items-baseline justify-between gap-4 border-b border-paper/10 px-4 py-3">
      <div className="font-narrow text-5xl font-semibold tracking-tight tabular-nums text-paper sm:text-6xl">
        {snapshot.clock ?? "--:--"}
      </div>
      <div className="flex flex-col items-end gap-1">
        <div className="font-narrow text-xs uppercase tracking-widest text-paper/60 sm:text-sm">
          Day {snapshot.day_number} of {snapshot.total_days}
        </div>
        <div className="rounded-sm border border-paper/30 px-2 py-0.5 font-narrow text-xs uppercase tracking-widest text-paper/80">
          {STATUS_LABEL[snapshot.status]}
        </div>
      </div>
    </header>
  );
}
```

- [ ] **Step 3: `web/src/components/ErrorBudgetBar.tsx`**

```tsx
import type { DaySnapshot } from "../types";

function pagesRemainingDisplay(eighths: number): string {
  const whole = Math.floor(eighths / 8);
  const fraction = eighths % 8;
  if (whole && fraction) return `${whole} ${fraction}/8`;
  if (whole) return `${whole}`;
  if (fraction) return `${fraction}/8`;
  return "0";
}

export function ErrorBudgetBar({ snapshot }: { snapshot: DaySnapshot }) {
  const consumed = Math.min(1, Math.max(0, snapshot.error_budget_consumed));
  const percent = Math.round(consumed * 100);

  return (
    <section className="px-4 py-6" aria-label="Error budget">
      <div
        className="h-10 w-full overflow-hidden rounded-sm bg-paper/10"
        role="progressbar"
        aria-valuenow={percent}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="Error budget consumed"
      >
        <div className="h-full bg-burn transition-[width] duration-700 ease-out" style={{ width: `${percent}%` }} />
      </div>
      <p className="mt-3 font-body text-base text-paper/80">
        {pagesRemainingDisplay(snapshot.pages_remaining_eighths)} pages remaining
        {snapshot.projected_wrap ? ` · wrap projected ${snapshot.projected_wrap}` : ""}
      </p>
    </section>
  );
}
```

- [ ] **Step 4: `web/src/components/StripBoard.tsx`**

```tsx
import type { SceneSnapshot, StripColor } from "../types";

const STRIP_CLASS: Record<StripColor, string> = {
  "day-int": "bg-strip-day-int text-ink",
  "day-ext": "bg-strip-day-ext text-ink",
  "night-int": "bg-strip-night-int text-ink",
  "night-ext": "bg-strip-night-ext text-ink",
};

type StripState = "shot" | "current" | "remaining";

function Strip({ scene, state }: { scene: SceneSnapshot; state: StripState }) {
  return (
    <li
      className={[
        "flex items-center gap-3 rounded-sm px-3 py-2 font-narrow",
        STRIP_CLASS[scene.strip_color],
        state === "remaining" ? "opacity-40" : "opacity-100",
        state === "current" ? "strip-current ring-2 ring-paper" : "",
      ].join(" ")}
    >
      <span className="text-sm font-semibold tracking-wide">Sc. {scene.number}</span>
      <span className="flex-1 truncate text-sm">{scene.synopsis}</span>
      <span className="hidden text-xs opacity-70 sm:inline">{scene.cast_names.join(", ") || "—"}</span>
      <span className="text-xs font-semibold">{scene.page_eighths_display} pg</span>
    </li>
  );
}

export function StripBoard({
  scenes,
  currentScene,
  shotScenes,
}: {
  scenes: SceneSnapshot[];
  currentScene: string | null;
  shotScenes: string[];
}) {
  const shot = new Set(shotScenes);

  return (
    <section aria-label="Strip board" className="px-4 py-4">
      <ul className="flex flex-col gap-1.5">
        {scenes.map((scene) => {
          const state: StripState = shot.has(scene.number)
            ? "shot"
            : scene.number === currentScene
              ? "current"
              : "remaining";
          return <Strip key={scene.number} scene={scene} state={state} />;
        })}
      </ul>
    </section>
  );
}
```

- [ ] **Step 5: `web/src/components/RecoveryOptions.tsx`**

```tsx
import { useState } from "react";
import type { GateVerdict, RecoveryOption, RecoverySnapshot } from "../types";

function OptionCard({
  option,
  verdict,
  approved,
  onApprove,
}: {
  option: RecoveryOption;
  verdict: GateVerdict;
  approved: boolean;
  onApprove: () => void;
}) {
  if (!verdict.approved) {
    return (
      <div className="rounded-md border-2 border-burn bg-burn/10 p-5">
        <p className="font-narrow text-xs font-semibold uppercase tracking-widest text-burn">Rejected</p>
        <h3 className="mt-1 font-body text-lg font-semibold text-paper">{option.description}</h3>
        <ul className="mt-3 space-y-2">
          {verdict.violations.map((violation, index) => (
            <li key={index} className="font-body text-xl font-semibold leading-snug text-burn">
              {violation.reason}
            </li>
          ))}
        </ul>
      </div>
    );
  }

  return (
    <div className="rounded-md border border-paper/20 p-5">
      <p className="font-narrow text-xs uppercase tracking-widest text-paper/50">Approved</p>
      <h3 className="mt-1 font-body text-base font-medium text-paper">{option.description}</h3>
      <p className="mt-1 font-body text-sm text-paper/60">Recovers roughly {option.minutes_recovered} minutes.</p>
      <button
        type="button"
        onClick={onApprove}
        disabled={approved}
        className="mt-3 rounded-sm bg-paper px-4 py-1.5 font-narrow text-sm font-semibold uppercase tracking-wide text-ink transition-transform duration-150 enabled:active:scale-95 disabled:opacity-60"
      >
        {approved ? "Approved" : "Approve"}
      </button>
    </div>
  );
}

export function RecoveryOptions({ recovery }: { recovery: RecoverySnapshot }) {
  const [approvedId, setApprovedId] = useState<string | null>(null);
  const verdictsById = new Map(recovery.result.verdicts.map((v) => [v.option_id, v]));
  const rejected = recovery.result.options.filter((o) => !verdictsById.get(o.id)?.approved);
  const approved = recovery.result.options.filter((o) => verdictsById.get(o.id)?.approved);

  return (
    <section aria-label="Recovery options" className="flex flex-col gap-4 px-4 py-4">
      {!recovery.result.live && (
        <p className="font-body text-xs italic text-paper/50">
          Recovery options from a cached run — Gemini daily quota reached.
        </p>
      )}
      {[...rejected, ...approved].map((option) => {
        const verdict = verdictsById.get(option.id);
        if (!verdict) return null;
        return (
          <OptionCard
            key={option.id}
            option={option}
            verdict={verdict}
            approved={approvedId === option.id}
            onApprove={() => setApprovedId(option.id)}
          />
        );
      })}
      {recovery.incident_url && (
        <a
          href={recovery.incident_url}
          target="_blank"
          rel="noreferrer"
          className="font-body text-xs text-paper/50 underline decoration-paper/30"
        >
          View incident in Grafana
        </a>
      )}
    </section>
  );
}
```

- [ ] **Step 6: `web/src/components/StartButton.tsx`**

```tsx
import { useState } from "react";
import { startDay } from "../api";
import type { Status } from "../types";

export function StartButton({ status }: { status: Status }) {
  const [pending, setPending] = useState(false);
  const disabled = pending || status === "running" || status === "at_risk";

  async function handleClick() {
    setPending(true);
    try {
      await startDay();
    } finally {
      setPending(false);
    }
  }

  return (
    <button
      type="button"
      onClick={handleClick}
      disabled={disabled}
      className="rounded-sm bg-strip-day-ext px-5 py-2 font-narrow text-sm font-bold uppercase tracking-wide text-ink disabled:opacity-40"
    >
      {status === "wrapped" ? "Replay day" : "Start"}
    </button>
  );
}
```

- [ ] **Step 7: Replace `web/src/App.tsx`**

```tsx
import { ErrorBudgetBar } from "./components/ErrorBudgetBar";
import { Header } from "./components/Header";
import { ProvisioningLog } from "./components/ProvisioningLog";
import { RecoveryOptions } from "./components/RecoveryOptions";
import { StartButton } from "./components/StartButton";
import { StripBoard } from "./components/StripBoard";
import { useDaySnapshot } from "./hooks/useDaySnapshot";

export default function App() {
  const snapshot = useDaySnapshot();

  if (!snapshot) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-board font-body text-paper/60">
        Connecting to Day 14…
      </main>
    );
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col bg-board text-paper">
      <ProvisioningLog provisioning={snapshot.provisioning} />
      <Header snapshot={snapshot} />
      <ErrorBudgetBar snapshot={snapshot} />
      <div className="flex justify-center px-4 pb-2">
        <StartButton status={snapshot.status} />
      </div>
      {snapshot.error_message && (
        <p className="px-4 py-2 font-body text-sm text-burn">{snapshot.error_message}</p>
      )}
      <StripBoard
        scenes={snapshot.scenes}
        currentScene={snapshot.current_scene}
        shotScenes={snapshot.shot_scene_numbers}
      />
      {snapshot.recovery && <RecoveryOptions recovery={snapshot.recovery} />}
    </main>
  );
}
```

- [ ] **Step 8: Replace `web/src/main.tsx`**

```tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./index.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
```

- [ ] **Step 9: Remove any leftover scaffold files these replace**

```bash
rm -f web/src/App.tsx.bak web/src/assets/react.svg
```

(Only remove `web/src/assets/react.svg` if `App.tsx` no longer references it — the rewrite above doesn't.)

- [ ] **Step 10: Build**

Run: `cd web && npm run build`
Expected: succeeds with no TypeScript errors.

- [ ] **Step 11: Commit**

```bash
git add web/src
git commit -m "feat: the console UI — provisioning log, budget bar, strip board, recovery cards"
```

---

## Task 13: Build and commit `web/dist`

**Files:**
- Create (committed build output): `web/dist/`

- [ ] **Step 1: Build**

```bash
cd web && npm run build
```

- [ ] **Step 2: Confirm it's not still ignored**

```bash
git status web/dist
```

Expected: files listed as untracked (not silently excluded — if nothing shows up, Task 9's `.gitignore` fix didn't take; check for a stray `dist/` rule shadowing it).

- [ ] **Step 3: Commit**

```bash
git add web/dist
git commit -m "chore: commit the built console (web/dist has no Node on the deploy host)"
```

---

## Task 14: End-to-end verification in a real browser

No new files. This is the task that actually matters for whether Module 6 is done — everything before it only proves the parts compile and the pure functions behave. Do not report this module complete without doing this.

- [ ] **Step 1: Run the server**

```bash
uv run uvicorn server.app:app --host 0.0.0.0 --port 8000
```

Watch the startup log for the provisioning line — either a successful live provision or the "falling back to cache" message. If it fails AND there's no cache, stop and fix that before continuing (Task 4 should have produced the cache).

- [ ] **Step 2: Open it**

Open `http://localhost:8000` in a real browser.

Check before doing anything else:
- The provisioning log's three lines are visible and its links are real Grafana URLs (click the dashboard one — it should actually open your stack).
- The clock, "Day 14 of 32", and status pill render. Status should read "Standing by".
- The error budget bar is empty and is clearly the dominant visual element on the page — not a chart, not a stat card.
- Keyboard: press Tab repeatedly; every focusable element (the Start button, links) gets a visible outline.
- Resize the window to a phone width; nothing overflows horizontally.

- [ ] **Step 3: Press Start**

Click Start. Confirm:
- The button disables itself immediately.
- A second `POST /api/day/start` (e.g. opening a second browser tab to the same URL and pressing Start there, or curling it) gets rejected — check the Network tab or `curl -i -X POST http://localhost:8000/api/day/start` returns 409 while the first replay is still running.
- The clock advances, strips move from dim → pulsing (current) → full brightness (shot) as scenes wrap, and the budget bar fills as the day slips.

- [ ] **Step 4: Watch the slip and the recovery**

Once the day crosses into "Behind schedule": confirm the status pill updates, and within a few seconds (the real Grafana query + Gemini calls) two option cards appear.

Check the rejection card specifically:
- Is it the single most visually dominant thing on the screen at that moment — more than the header, more than the strip board? If your eye lands anywhere else first, that's a hierarchy bug — fix it (larger text, more padding, or move it above the strip board) before moving on.
- Is `--color-burn` used only on that card (and the budget bar)? Nothing else on the page should have picked up red.
- Does the rejection reason read as a full, plain-English sentence (e.g. the real turnaround shortfall from `gate/rules/production_rules.yaml`'s `description` template) — not a code, not a rule name?

If recovery came from the cached fixture instead of live (e.g. quota already spent today), confirm the "Recovery options from a cached run — Gemini daily quota reached." line is visible near the cards, and that it reads as a quiet aside, not styled like the rejection card.

- [ ] **Step 5: Approve the legal option**

Click Approve on the approved card. Confirm it animates (the one click-response motion allowed beyond the budget bar/strip pulse) and shows "Approved".

If an incident link is present, click it and confirm it opens something real in Grafana (the dashboard, if this hit the documented annotation fallback; the incident app, if `create_incident` actually succeeded on your stack).

- [ ] **Step 6: Let the day wrap**

Let the replay finish. Confirm status reaches "Wrapped" and the Start button re-enables, now reading "Replay day".

- [ ] **Step 7: Report honestly**

Run the full test suite one more time (`uv run pytest -q` and `cd web && npm run build`) and report:
- What you verified working, from the checklist above.
- Anything that didn't work, or that you didn't manage to verify (e.g. real `create_incident` support, since this project's stack is documented as free-tier and expected to hit the annotation fallback instead). Do not claim something works if you only read the code — this task exists specifically so that doesn't happen.
