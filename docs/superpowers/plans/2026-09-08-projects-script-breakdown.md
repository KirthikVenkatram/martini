# Module 7 — Projects & Script Breakdown Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A user creates a production, uploads a screenplay PDF, Gemini breaks it into scenes, the user enters cast with turnaround constraints, and the console replays that generated day — with `/` still the console landing page and Day 14 still the default when nothing is activated.

**Architecture:** New `agent/tools/breakdown.py` (Gemini multimodal PDF → `Scene`s) and `agent/tools/scheduling.py` (deterministic `ShootingDay` + synthetic replay-timing generation) feed a new `server/projects/` storage layer and `server/routes/projects.py` API. Activation swaps `AppState.plan_day`/`active_project_slug` and re-provisions Grafana (with the Gemini planning decision cached per project). The frontend adds hand-rolled pathname routing (`/` vs `/projects`) with no new dependency.

**Tech Stack:** Python 3.11+, Pydantic v2, `google-genai` (Gemini Developer API, multimodal), FastAPI, React 19 + TypeScript + Tailwind v4. No new AI SDK, no database, no router library, no state/component library.

**Spec:** `docs/superpowers/specs/2026-09-08-projects-script-breakdown-design.md`

## Global Constraints

- Only Google AI SDKs (`google-adk`, `google-genai`, already resolved at 2.22.0 via `google-adk`'s own dependency — this plan pins it explicitly in `pyproject.toml`). No OpenAI/LangChain/etc.
- All demo content (test PDFs, fixture scenes/cast) invented — no real film, studio, or person.
- Never commit `.env`, API keys, or tokens.
- Gemini is called only when unavoidable — never per emitter tick, never speculatively. Breakdown and the planner's monitoring decision are the only two call sites this module adds, and Task 6 makes the second one cacheable.
- `gate/`, `emitter/schedule.py`, `agent/subagents/replanner.py`, `agent/subagents/observer.py`, and every `web/src/components/*` file are **not modified** by this plan — they consume `ShootingDay` unchanged.
- `generate_scenario` must terminate on a bound, never loop searching for an unreachable AT_RISK crossing (Correction 1).
- The Gemini planning decision (`MonitoringPlan`) is cached per project after its first live call; only the Grafana MCP write repeats on later activations (Correction 2).
- `data/gemini_quota.json` is a local-dev convenience only — it does not persist on Cloud Run's ephemeral filesystem. The real defence against quota exhaustion is a clean 429 handler that never crashes the caller (Correction 3).
- One concern per commit, conventional commit messages, ending with:
  ```
  Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
  ```

---

## Task 1: Pin `google-genai` as an explicit dependency

`breakdown.py` (Task 3) imports `google.genai` directly rather than only through `google-adk`'s `LlmAgent`. It's already resolved to `2.22.0` in `uv.lock` (as `google-adk`'s own dependency) — this task just makes that pin explicit and load-bearing instead of implicit.

**Files:**
- Modify: `pyproject.toml`

**Interfaces:**
- Produces: `google-genai==2.22.0` as a direct project dependency, importable as `from google import genai` / `from google.genai import types` / `from google.genai.errors import ClientError`.

- [ ] **Step 1: Add the dependency**

In `pyproject.toml`, in the `dependencies` list, add a line after `"google-adk[mcp]==2.8.0",`:

```toml
    "google-genai==2.22.0",
```

- [ ] **Step 2: Sync and verify nothing moved**

Run: `uv sync`
Expected: resolves with no changes to `uv.lock` beyond marking `google-genai` as a direct (not just transitive) dependency — it was already locked at this version.

- [ ] **Step 3: Run the existing test suite to confirm nothing broke**

Run: `uv run pytest -q`
Expected: PASS, same count as before this change.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "$(cat <<'EOF'
build: pin google-genai as a direct dependency

agent/tools/breakdown.py (Module 7) calls the Gemini Developer API
client directly rather than only through google-adk's LlmAgent, so the
dependency that was already resolved transitively needs to be pinned
explicitly.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Gemini quota counter (`agent/tools/quota.py`)

A pure, injectable-path function so it's fully testable without touching the real `data/` directory or wall-clock date.

**Files:**
- Create: `agent/tools/quota.py`
- Test: `tests/test_quota.py`

**Interfaces:**
- Produces: `check_and_increment(path: Path, limit: int, today: date) -> bool` — `True` and increments if under `limit` for `today`; `False` and does not increment if at or over `limit`. Resets transparently when `today` differs from what's on disk.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_quota.py`:

```python
from __future__ import annotations

import json
from datetime import date

from agent.tools.quota import check_and_increment


def test_allows_calls_under_the_limit(tmp_path):
    path = tmp_path / "quota.json"
    today = date(2026, 9, 8)

    for _ in range(3):
        assert check_and_increment(path, limit=3, today=today) in (True, False)

    assert json.loads(path.read_text())["count"] == 3


def test_blocks_once_the_limit_is_reached(tmp_path):
    path = tmp_path / "quota.json"
    today = date(2026, 9, 8)

    for _ in range(3):
        assert check_and_increment(path, limit=3, today=today) is True

    assert check_and_increment(path, limit=3, today=today) is False
    assert json.loads(path.read_text())["count"] == 3


def test_resets_on_a_new_day(tmp_path):
    path = tmp_path / "quota.json"
    path.write_text(json.dumps({"date": "2026-09-07", "count": 20}))

    assert check_and_increment(path, limit=20, today=date(2026, 9, 8)) is True
    assert json.loads(path.read_text()) == {"date": "2026-09-08", "count": 1}


def test_tolerates_a_missing_or_corrupt_file(tmp_path):
    path = tmp_path / "quota.json"
    path.write_text("not json")

    assert check_and_increment(path, limit=20, today=date(2026, 9, 8)) is True
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_quota.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'agent.tools.quota'`

- [ ] **Step 3: Implement**

Create `agent/tools/quota.py`:

```python
"""A local-dev daily call counter (Module 7).

This is a convenience that warns before a script upload burns the
day's Gemini free-tier quota during local development -- it is NOT a
real guard in production. Cloud Run's filesystem is ephemeral and
resets every cold start, so this file will not reliably persist a
count there. The real defence against quota exhaustion is the 429
handler around the Gemini call itself (agent/tools/breakdown.py),
which must stay clean and never crash its caller regardless of what
this counter says.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path


def check_and_increment(path: Path, limit: int, today: date) -> bool:
    """True (and records the call) if under `limit` calls for `today` so far."""
    state = {"date": today.isoformat(), "count": 0}
    if path.exists():
        try:
            loaded = json.loads(path.read_text())
            if loaded.get("date") == today.isoformat():
                state = loaded
        except (json.JSONDecodeError, OSError):
            pass

    if state["count"] >= limit:
        return False

    state["count"] += 1
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state))
    return True
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_quota.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add agent/tools/quota.py tests/test_quota.py
git commit -m "$(cat <<'EOF'
feat: add a local-dev Gemini quota counter

A pure, injectable-path daily call counter for agent/tools/breakdown.py
to check before spending a request. Explicitly documented as a
dev-only convenience -- Cloud Run's ephemeral filesystem means it does
not persist there, so the 429 handler stays the real defence.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Script breakdown (`agent/tools/breakdown.py`)

**Files:**
- Create: `agent/tools/breakdown.py`
- Test: `tests/test_breakdown.py`

**Interfaces:**
- Consumes: `agent.config.{GEMINI_MODEL, GOOGLE_API_KEY, GOOGLE_GENAI_USE_VERTEXAI}`, `agent.tools.quota.check_and_increment`, `emitter.models.{PageEighths, Scene}`
- Produces: `breakdown_script(pdf_bytes: bytes) -> list[Scene]`, `slugify_character_name(name: str) -> str` (also used by Task 4's `build_shooting_day` to keep `Scene.cast_ids` and `Performer.id` joined on the same key), `BreakdownParseError`, `BreakdownQuotaExceeded` (both `Exception` subclasses; routes.py in Task 8 catches these to return a clean error instead of a 500)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_breakdown.py`:

```python
from __future__ import annotations

from datetime import date

import pytest
from google.genai.errors import ClientError

from agent.tools import breakdown


def _quota_error() -> ClientError:
    return ClientError(429, {"error": {"message": "quota exceeded", "status": "RESOURCE_EXHAUSTED"}}, None)


def test_slugify_character_name_normalizes():
    assert breakdown.slugify_character_name("PRIYA") == "priya"
    assert breakdown.slugify_character_name("  Desmond Ruiz ") == "desmond-ruiz"
    assert breakdown.slugify_character_name("***") == "cast"


def test_parses_a_well_formed_json_array():
    raw = """
    [
      {
        "number": "1",
        "synopsis": "MARCUS and ELENA argue in the kitchen.",
        "int_ext": "int",
        "day_night": "day",
        "location": "Kitchen",
        "page_eighths": "2 3/8",
        "cast_names": ["MARCUS", "ELENA"],
        "estimated_setups": 3
      }
    ]
    """

    scenes = breakdown._parse_breakdown_payload(raw)

    assert len(scenes) == 1
    scene = scenes[0]
    assert scene.number == "1"
    assert scene.int_ext == "INT"
    assert scene.day_night == "DAY"
    assert str(scene.page_eighths) == "2 3/8"
    assert scene.cast_ids == ["marcus", "elena"]
    assert scene.estimated_setups == 3


def test_strips_markdown_code_fences():
    raw = '```json\n[{"number": "1", "synopsis": "A.", "int_ext": "INT", "day_night": "DAY", "location": "Set", "page_eighths": "1", "cast_names": [], "estimated_setups": 1}]\n```'

    scenes = breakdown._parse_breakdown_payload(raw)

    assert len(scenes) == 1


def test_raises_a_named_error_on_invalid_json():
    with pytest.raises(breakdown.BreakdownParseError, match="not valid JSON"):
        breakdown._parse_breakdown_payload("not json at all")


def test_raises_a_named_error_naming_the_bad_scene():
    raw = '[{"number": "1", "synopsis": "A.", "int_ext": "SIDEWAYS", "day_night": "DAY", "location": "Set", "page_eighths": "1", "cast_names": [], "estimated_setups": 1}]'

    with pytest.raises(breakdown.BreakdownParseError, match="scene at index 0"):
        breakdown._parse_breakdown_payload(raw)


def test_breakdown_script_raises_quota_exceeded_when_the_counter_is_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(breakdown, "_QUOTA_PATH", tmp_path / "quota.json")
    monkeypatch.setattr(breakdown, "_QUOTA_DAILY_LIMIT", 0)

    with pytest.raises(breakdown.BreakdownQuotaExceeded, match="quota"):
        breakdown.breakdown_script(b"%PDF-fake")


def test_breakdown_script_raises_quota_exceeded_on_a_live_429(tmp_path, monkeypatch):
    monkeypatch.setattr(breakdown, "_QUOTA_PATH", tmp_path / "quota.json")

    class _FakeModels:
        def generate_content(self, **kwargs):
            raise _quota_error()

    class _FakeClient:
        def __init__(self, **kwargs):
            self.models = _FakeModels()

    monkeypatch.setattr(breakdown.genai, "Client", _FakeClient)

    with pytest.raises(breakdown.BreakdownQuotaExceeded, match="quota"):
        breakdown.breakdown_script(b"%PDF-fake")


def test_breakdown_script_reraises_non_quota_errors(tmp_path, monkeypatch):
    monkeypatch.setattr(breakdown, "_QUOTA_PATH", tmp_path / "quota.json")

    class _FakeModels:
        def generate_content(self, **kwargs):
            raise ClientError(500, {"error": {"message": "server error"}}, None)

    class _FakeClient:
        def __init__(self, **kwargs):
            self.models = _FakeModels()

    monkeypatch.setattr(breakdown.genai, "Client", _FakeClient)

    with pytest.raises(ClientError):
        breakdown.breakdown_script(b"%PDF-fake")


def test_breakdown_script_parses_a_successful_response(tmp_path, monkeypatch):
    monkeypatch.setattr(breakdown, "_QUOTA_PATH", tmp_path / "quota.json")

    raw = '[{"number": "1", "synopsis": "A.", "int_ext": "INT", "day_night": "DAY", "location": "Set", "page_eighths": "1", "cast_names": [], "estimated_setups": 1}]'

    class _FakeResponse:
        text = raw

    class _FakeModels:
        def generate_content(self, **kwargs):
            return _FakeResponse()

    class _FakeClient:
        def __init__(self, **kwargs):
            self.models = _FakeModels()

    monkeypatch.setattr(breakdown.genai, "Client", _FakeClient)

    scenes = breakdown.breakdown_script(b"%PDF-fake")

    assert len(scenes) == 1
    assert scenes[0].number == "1"
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_breakdown.py -v`
Expected: FAIL — module doesn't exist yet

- [ ] **Step 3: Implement**

Create `agent/tools/breakdown.py`:

```python
"""Script breakdown via Gemini multimodal (Module 7).

breakdown_script(pdf_bytes) sends the screenplay PDF straight to
Gemini as an inline document part -- no text extraction first, the
multimodal path is the point -- and parses the strict-JSON reply into
Scene objects (emitter/models.py), the same model every other part of
MARTINI already consumes.

A screenplay only names characters, not performer ids, so cast_names
here are turned into slugs (slugify_character_name) that
agent/tools/scheduling.py's build_shooting_day re-derives from the
cast form's character names -- as long as a cast entry's name matches
what appeared in the breakdown, Scene.cast_ids and Performer.id agree
without either side ever seeing an explicit id.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from google import genai
from google.genai import types
from google.genai.errors import ClientError

from agent.config import GEMINI_MODEL, GOOGLE_API_KEY, GOOGLE_GENAI_USE_VERTEXAI
from agent.tools.quota import check_and_increment
from emitter.models import PageEighths, Scene

_QUOTA_PATH = Path(__file__).parent.parent.parent / "data" / "gemini_quota.json"
_QUOTA_DAILY_LIMIT = 20

_PROMPT = """You are breaking down a film screenplay into a shooting-day scene list.

Read the attached screenplay PDF and reply with a strict JSON array,
nothing else -- no markdown code fences, no prose before or after it.
Each element describes one scene, in script order, with exactly these
keys:

- "number": the scene number as it appears in the script (string)
- "synopsis": one plain sentence describing what happens in the scene
- "int_ext": "INT" or "EXT"
- "day_night": "DAY" or "NIGHT"
- "location": the scene heading's location, in a few words
- "page_eighths": the scene's length in page eighths, as a string like
  "2 3/8" (a film script is scheduled in eighths of a page -- 8
  eighths make one full page; a scene running just under three pages
  is "2 7/8", a scene under a quarter of a page is "1/8" or "2/8")
- "cast_names": the character names (as written in the script) who
  appear in the scene
- "estimated_setups": your best estimate of how many distinct camera
  setups this scene needs to cover, as an integer

Do not invent scenes that aren't in the script. Do not skip any scene
that is."""


class BreakdownParseError(ValueError):
    """The breakdown response couldn't be parsed into Scenes."""


class BreakdownQuotaExceeded(RuntimeError):
    """Gemini's daily free-tier quota is used up."""


def slugify_character_name(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return slug or "cast"


def _parse_breakdown_payload(raw_text: str) -> list[Scene]:
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if "\n" in text:
            first_line, rest = text.split("\n", 1)
            text = rest if first_line.strip().lower() in ("json", "") else text

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise BreakdownParseError(f"breakdown response was not valid JSON: {raw_text!r}") from exc

    if not isinstance(payload, list):
        raise BreakdownParseError(f"breakdown response was not a JSON array: {raw_text!r}")

    scenes: list[Scene] = []
    for index, raw_scene in enumerate(payload):
        try:
            scenes.append(
                Scene(
                    number=str(raw_scene["number"]),
                    synopsis=raw_scene["synopsis"],
                    page_eighths=PageEighths.from_string(str(raw_scene["page_eighths"])),
                    int_ext=str(raw_scene["int_ext"]).strip().upper(),
                    day_night=str(raw_scene["day_night"]).strip().upper(),
                    location=raw_scene["location"],
                    cast_ids=[slugify_character_name(n) for n in raw_scene.get("cast_names", [])],
                    estimated_setups=int(raw_scene["estimated_setups"]),
                )
            )
        except Exception as exc:  # noqa: BLE001 -- re-raised immediately, named and scoped to one scene
            raise BreakdownParseError(f"scene at index {index} failed to parse: {exc}") from exc

    return scenes


def breakdown_script(pdf_bytes: bytes) -> list[Scene]:
    if not check_and_increment(_QUOTA_PATH, _QUOTA_DAILY_LIMIT, date.today()):
        raise BreakdownQuotaExceeded(
            f"MARTINI's local Gemini quota ({_QUOTA_DAILY_LIMIT} requests/day) is used up for today."
        )

    client = genai.Client(api_key=GOOGLE_API_KEY, vertexai=GOOGLE_GENAI_USE_VERTEXAI.upper() == "TRUE")

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[
                types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
                types.Part(text=_PROMPT),
            ],
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
    except ClientError as exc:
        if exc.code == 429:
            raise BreakdownQuotaExceeded("Gemini's daily free-tier quota is exhausted.") from exc
        raise

    if response.text is None:
        raise BreakdownParseError("breakdown response had no text")

    return _parse_breakdown_payload(response.text)
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_breakdown.py -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add agent/tools/breakdown.py tests/test_breakdown.py
git commit -m "$(cat <<'EOF'
feat: script breakdown via Gemini multimodal

breakdown_script sends a screenplay PDF inline to Gemini and parses
strict JSON into emitter.models.Scene -- the same model every other
part of MARTINI consumes. Defensive parsing names exactly which scene
failed; a 429 raises a clean BreakdownQuotaExceeded instead of
propagating a raw ClientError.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Deterministic day building (`agent/tools/scheduling.py`, part 1)

**Files:**
- Create: `agent/tools/scheduling.py`
- Test: `tests/test_scheduling.py`

**Interfaces:**
- Consumes: `emitter.models.{Scene, Setup, Performer, ShootingDay}`, `gate.checker.load_rules`, `agent.tools.breakdown.slugify_character_name`
- Produces: `CastEntry` (pydantic model: `character_name: str`, `is_minor: bool = False`, `previous_night_wrap: datetime`, `minimum_turnaround_hours: float | None = None`), `build_shooting_day(scenes: list[Scene], cast: list[CastEntry], day_number: int, shoot_date: date, production_title: str) -> ShootingDay`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_scheduling.py`:

```python
from __future__ import annotations

from datetime import date, datetime

from emitter.models import PageEighths, Scene
from agent.tools.scheduling import CastEntry, build_shooting_day


def _scene(number: str, eighths: str, cast_ids: list[str], setups: int) -> Scene:
    return Scene(
        number=number,
        synopsis=f"Scene {number}.",
        page_eighths=PageEighths.from_string(eighths),
        int_ext="INT",
        day_night="DAY",
        location="Set",
        cast_ids=cast_ids,
        estimated_setups=setups,
    )


def test_build_shooting_day_derives_setups_from_estimated_setups():
    scenes = [_scene("1", "2", ["marcus"], setups=3)]
    cast = [CastEntry(character_name="MARCUS", previous_night_wrap=datetime(2026, 9, 2, 20, 0))]

    day = build_shooting_day(scenes, cast, day_number=1, shoot_date=date(2026, 9, 8), production_title="Test Day")

    scene_setups = [s for s in day.setups if s.scene_number == "1"]
    assert len(scene_setups) == 3
    assert all(s.estimated_minutes > 0 for s in scene_setups)
    assert all(s.actual_minutes is None for s in scene_setups)


def test_build_shooting_day_assigns_call_and_wrap_times_in_order():
    scenes = [_scene("1", "1", [], setups=1)]
    cast: list[CastEntry] = []

    day = build_shooting_day(scenes, cast, day_number=1, shoot_date=date(2026, 9, 8), production_title="Test Day")

    assert day.general_call < day.scheduled_wrap < day.overtime_threshold
    assert day.general_call.date() == date(2026, 9, 8)


def test_build_shooting_day_defaults_turnaround_from_production_rules():
    scenes = [_scene("1", "1", ["priya", "juno"], setups=1)]
    cast = [
        CastEntry(character_name="PRIYA", is_minor=False, previous_night_wrap=datetime(2026, 9, 2, 20, 0)),
        CastEntry(character_name="JUNO", is_minor=True, previous_night_wrap=datetime(2026, 9, 2, 20, 0)),
    ]

    day = build_shooting_day(scenes, cast, day_number=1, shoot_date=date(2026, 9, 8), production_title="Test Day")

    priya = next(p for p in day.performers if p.character_name == "PRIYA")
    juno = next(p for p in day.performers if p.character_name == "JUNO")
    assert priya.minimum_turnaround_hours == 11.0
    assert juno.minimum_turnaround_hours == 12.0


def test_build_shooting_day_honors_an_explicit_turnaround_override():
    scenes = [_scene("1", "1", ["marcus"], setups=1)]
    cast = [
        CastEntry(
            character_name="MARCUS",
            previous_night_wrap=datetime(2026, 9, 2, 20, 0),
            minimum_turnaround_hours=13.0,
        )
    ]

    day = build_shooting_day(scenes, cast, day_number=1, shoot_date=date(2026, 9, 8), production_title="Test Day")

    assert day.performers[0].minimum_turnaround_hours == 13.0


def test_build_shooting_day_joins_scene_cast_ids_to_performer_ids_by_slug():
    scenes = [_scene("1", "1", ["desmond-ruiz"], setups=1)]
    cast = [CastEntry(character_name="Desmond Ruiz", previous_night_wrap=datetime(2026, 9, 2, 20, 0))]

    day = build_shooting_day(scenes, cast, day_number=1, shoot_date=date(2026, 9, 8), production_title="Test Day")

    assert day.performers[0].id == "desmond-ruiz"
    assert day.scenes[0].cast_ids == ["desmond-ruiz"]
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_scheduling.py -v`
Expected: FAIL — module doesn't exist yet

- [ ] **Step 3: Implement**

Create `agent/tools/scheduling.py`:

```python
"""Deterministic shooting-day construction (Module 7).

build_shooting_day never calls an LLM -- it turns a Gemini breakdown's
scenes and a cast form into the same ShootingDay every other part of
MARTINI already consumes (emitter/schedule.py, gate/checker.py, the
console). Turnaround defaults are read from
gate/rules/production_rules.yaml, the same file the gate itself checks
against, so a freshly-built day's displayed turnaround margin always
agrees with what the gate would later approve or reject.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from pydantic import BaseModel

from agent.tools.breakdown import slugify_character_name
from emitter.models import Performer, Scene, ShootingDay, Setup
from gate.checker import load_rules

_GENERAL_CALL_TIME = time(7, 0)
_SCHEDULED_SHOOT_HOURS = 11
_OVERTIME_BUFFER_HOURS = 1
_GOLDEN_HOUR_LEAD_MINUTES = 30
_MEAL_DUE_AFTER_HOURS = 6
_DEFAULT_SETUP_MINUTES = 20


class CastEntry(BaseModel):
    character_name: str
    is_minor: bool = False
    previous_night_wrap: datetime
    minimum_turnaround_hours: float | None = None


def build_shooting_day(
    scenes: list[Scene],
    cast: list[CastEntry],
    day_number: int,
    shoot_date: date,
    production_title: str,
) -> ShootingDay:
    rules = load_rules()

    general_call = datetime.combine(shoot_date, _GENERAL_CALL_TIME)
    scheduled_wrap = general_call + timedelta(hours=_SCHEDULED_SHOOT_HOURS)
    overtime_threshold = scheduled_wrap + timedelta(hours=_OVERTIME_BUFFER_HOURS)
    golden_hour_start = overtime_threshold - timedelta(minutes=_GOLDEN_HOUR_LEAD_MINUTES)
    meal_due_by = general_call + timedelta(hours=_MEAL_DUE_AFTER_HOURS)

    setups: list[Setup] = []
    for scene in scenes:
        setup_count = max(1, scene.estimated_setups)
        for i in range(setup_count):
            setups.append(
                Setup(
                    id=f"{scene.number}-{i + 1}",
                    scene_number=scene.number,
                    description=f"Sc.{scene.number} setup {i + 1}",
                    estimated_minutes=_DEFAULT_SETUP_MINUTES,
                )
            )

    performers = [
        Performer(
            id=slugify_character_name(entry.character_name),
            name=entry.character_name.title(),
            character_name=entry.character_name.upper(),
            call_time=general_call,
            previous_night_wrap=entry.previous_night_wrap,
            minimum_turnaround_hours=entry.minimum_turnaround_hours
            or (rules.turnaround.minor_minimum_hours if entry.is_minor else rules.turnaround.minimum_hours),
            is_minor=entry.is_minor,
        )
        for entry in cast
    ]

    return ShootingDay(
        day_number=day_number,
        production_title=production_title,
        shoot_date=shoot_date,
        general_call=general_call,
        scheduled_wrap=scheduled_wrap,
        overtime_threshold=overtime_threshold,
        golden_hour_start=golden_hour_start,
        meal_due_by=meal_due_by,
        scenes=scenes,
        setups=setups,
        performers=performers,
    )
```

Note: `Scene.cast_ids` entries must already be slugged consistently with `Performer.id` for the join in `test_build_shooting_day_joins_scene_cast_ids_to_performer_ids_by_slug` to pass — this is exactly what Task 3's `breakdown_script` already produces, and what this task's `build_shooting_day` produces on the cast side via the same `slugify_character_name`.

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_scheduling.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add agent/tools/scheduling.py tests/test_scheduling.py
git commit -m "$(cat <<'EOF'
feat: deterministic ShootingDay construction from a breakdown + cast form

build_shooting_day derives setups from estimated_setups, assigns a
standard call/wrap template, and defaults turnaround minimums from the
same production_rules.yaml the gate checks against -- no LLM call, no
network.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Replay-timing generation (`agent/tools/scheduling.py`, part 2)

The piece with no spec: `replay_day` (`emitter/simulator.py`) needs per-setup `actual_minutes`/`takes`, which a screenplay breakdown has no signal for. This generates it deterministically, injecting a capped slip on the day's longest scene so the SLIP → REPLAN → GATE cycle can fire on a user's own day (Correction 1).

**Files:**
- Modify: `agent/tools/scheduling.py`
- Test: `tests/test_scheduling.py` (same file as Task 4, appended)

**Interfaces:**
- Consumes: `agent.root.AT_RISK_ERROR_BUDGET_CONSUMED`, `emitter.schedule.error_budget_consumed`
- Produces: `ScenarioResult` (pydantic: `scenario: dict[str, dict[str, int]]`, `at_risk_reachable: bool`), `generate_scenario(day: ShootingDay) -> ScenarioResult`. `.scenario`'s shape (`{setup_id: {"actual_minutes": int, "takes": int}}`) matches `emitter.simulator.load_scenario`'s return type exactly, so it drops straight into the existing, unmodified `replay_day(day, scenario, ...)`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_scheduling.py`:

```python
from datetime import timedelta

from agent.root import AT_RISK_ERROR_BUDGET_CONSUMED
from emitter.models import ShootingDay, Setup
from emitter.schedule import error_budget_consumed
from agent.tools.scheduling import generate_scenario


def _day_with_scenes(scene_eighths: dict[str, str], setups_per_scene: int = 1) -> ShootingDay:
    scenes = [_scene(number, eighths, [], setups=setups_per_scene) for number, eighths in scene_eighths.items()]
    return build_shooting_day(scenes, [], day_number=1, shoot_date=date(2026, 9, 8), production_title="Test Day")


def _tight_day() -> ShootingDay:
    """A hand-built day (bypassing build_shooting_day's fixed 11-hour
    template) with only a 30-minute error budget and setups whose
    baseline timing already finishes the day early -- so the AT_RISK
    crossing in the test below happens only once generate_scenario's
    inflation of the longest scene (scene "2", 3 setups) pushes the
    total elapsed time past it, not from the baseline alone."""
    general_call = datetime(2026, 9, 8, 7, 0)
    scheduled_wrap = general_call + timedelta(hours=2)
    overtime_threshold = scheduled_wrap + timedelta(minutes=30)
    scenes = [
        _scene("1", "1", [], setups=1),
        _scene("2", "6", [], setups=3),
    ]
    setups = [
        Setup(id="1-1", scene_number="1", description="setup", estimated_minutes=20),
        Setup(id="2-1", scene_number="2", description="setup", estimated_minutes=20),
        Setup(id="2-2", scene_number="2", description="setup", estimated_minutes=20),
        Setup(id="2-3", scene_number="2", description="setup", estimated_minutes=20),
    ]
    return ShootingDay(
        day_number=1,
        production_title="Test Day",
        shoot_date=general_call.date(),
        general_call=general_call,
        scheduled_wrap=scheduled_wrap,
        overtime_threshold=overtime_threshold,
        golden_hour_start=overtime_threshold - timedelta(minutes=15),
        meal_due_by=general_call + timedelta(hours=1),
        scenes=scenes,
        setups=setups,
        performers=[],
    )


def test_generate_scenario_is_deterministic():
    day = _day_with_scenes({"1": "4", "2": "4", "3": "6"}, setups_per_scene=2)

    first = generate_scenario(day)
    second = generate_scenario(day)

    assert first.scenario == second.scenario
    assert first.at_risk_reachable == second.at_risk_reachable


def test_generate_scenario_covers_every_setup():
    day = _day_with_scenes({"1": "4", "2": "6"}, setups_per_scene=2)

    result = generate_scenario(day)

    assert set(result.scenario.keys()) == {s.id for s in day.setups}
    assert all(t["actual_minutes"] > 0 and t["takes"] > 0 for t in result.scenario.values())


def test_generate_scenario_crosses_at_risk_on_a_tight_day():
    # scheduled_wrap is 2h after call, overtime_threshold only 30 more
    # minutes past that (error_budget_total = 30 min). Baseline timing
    # (4 setups, ~20 min each) finishes around the 80-minute mark --
    # comfortably inside the 2-hour scheduled length, consumed=0. Only
    # once scene "2"'s 3 setups (the longest scene, by page_eighths)
    # are inflated towards their cap does the day's total elapsed time
    # push past scheduled_wrap + 0.75 * 30min, crossing AT_RISK.
    day = _tight_day()

    result = generate_scenario(day)

    assert result.at_risk_reachable is True
    working = day.model_copy(deep=True)
    for setup in working.setups:
        timing = result.scenario[setup.id]
        setup.actual_minutes = timing["actual_minutes"]
        setup.takes = timing["takes"]
    elapsed = sum(t["actual_minutes"] for t in result.scenario.values())
    now = working.general_call + timedelta(minutes=elapsed)
    assert error_budget_consumed(working, now) >= AT_RISK_ERROR_BUDGET_CONSUMED

    # And it stayed within Correction 1's cap getting there.
    for setup in day.setups:
        if setup.scene_number == "2":
            timing = result.scenario[setup.id]
            assert timing["actual_minutes"] <= setup.estimated_minutes * 3
            assert timing["takes"] <= 15


def test_generate_scenario_reports_unreachable_on_a_generously_slacked_day():
    # A single tiny scene with a huge overtime buffer -- even inflated
    # to the cap (3x estimated_minutes, 15 takes), one small scene
    # cannot burn a day this generously budgeted past AT_RISK. Proves
    # the loop terminates on the cap rather than searching forever.
    scenes = [_scene("1", "1", [], setups=1)]
    day = build_shooting_day(scenes, [], day_number=1, shoot_date=date(2026, 9, 8), production_title="Test Day")
    day = day.model_copy(update={"overtime_threshold": day.overtime_threshold + timedelta(hours=48)})

    result = generate_scenario(day)

    assert result.at_risk_reachable is False
    timing = next(iter(result.scenario.values()))
    assert timing["actual_minutes"] <= _DEFAULT_SETUP_MINUTES_FOR_TEST * 3
    assert timing["takes"] <= 15


_DEFAULT_SETUP_MINUTES_FOR_TEST = 20
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_scheduling.py -v`
Expected: FAIL — `generate_scenario` doesn't exist yet

- [ ] **Step 3: Implement**

Append to `agent/tools/scheduling.py` (add these imports to the top alongside the existing ones: `from pydantic import BaseModel` is already imported; add `from agent.root import AT_RISK_ERROR_BUDGET_CONSUMED` and `from emitter.schedule import error_budget_consumed`):

```python
from agent.root import AT_RISK_ERROR_BUDGET_CONSUMED
from emitter.schedule import error_budget_consumed

_JITTER_PATTERN = [0, 2, -1, 3, -2, 1]
_BASE_TAKES = 2
_INFLATION_STEP_MINUTES = 2
_MAX_INFLATION_MULTIPLIER = 3.0
_MAX_TAKES = 15


class ScenarioResult(BaseModel):
    scenario: dict[str, dict[str, int]]
    at_risk_reachable: bool


def _elapsed_minutes(scenario: dict[str, dict[str, int]]) -> int:
    return sum(timing["actual_minutes"] for timing in scenario.values())


def _consumed_with_scenario(day: ShootingDay, scenario: dict[str, dict[str, int]]) -> float:
    working = day.model_copy(deep=True)
    for setup in working.setups:
        timing = scenario[setup.id]
        setup.actual_minutes = timing["actual_minutes"]
        setup.takes = timing["takes"]
    now = working.general_call + timedelta(minutes=_elapsed_minutes(scenario))
    return error_budget_consumed(working, now)


def generate_scenario(day: ShootingDay) -> ScenarioResult:
    """Deterministic per-setup actual_minutes/takes for replay_day.

    Nothing in a screenplay breakdown says how long a setup actually
    took -- something has to invent it. Every setup gets a fixed,
    reproducible jitter around its own estimate; the day's single
    longest scene (by page count) then has its setups' takes/minutes
    inflated, capped at 3x estimated_minutes and 15 takes per setup, up
    to the point error_budget_consumed crosses AT_RISK_ERROR_BUDGET_CONSUMED
    -- so the SLIP -> REPLAN -> GATE cycle fires on the user's own day,
    not only Day 14's canned scenario.

    Bounded, not a search: the inflation loop only ever moves every
    target setup towards its cap and stops the moment nothing moved,
    so a day with enough error budget that no reachable inflation
    would cross AT_RISK terminates with at_risk_reachable=False rather
    than looping.
    """
    scenario: dict[str, dict[str, int]] = {
        setup.id: {
            "actual_minutes": max(1, setup.estimated_minutes + _JITTER_PATTERN[i % len(_JITTER_PATTERN)]),
            "takes": _BASE_TAKES,
        }
        for i, setup in enumerate(day.setups)
    }

    if not day.scenes:
        return ScenarioResult(scenario=scenario, at_risk_reachable=False)

    longest_scene = max(day.scenes, key=lambda scene: scene.page_eighths.eighths)
    target_setups = [s for s in day.setups if s.scene_number == longest_scene.number]

    at_risk_reachable = _consumed_with_scenario(day, scenario) >= AT_RISK_ERROR_BUDGET_CONSUMED

    while target_setups and not at_risk_reachable:
        moved = False
        for setup in target_setups:
            timing = scenario[setup.id]
            cap_minutes = round(setup.estimated_minutes * _MAX_INFLATION_MULTIPLIER)
            if timing["actual_minutes"] < cap_minutes:
                timing["actual_minutes"] = min(timing["actual_minutes"] + _INFLATION_STEP_MINUTES, cap_minutes)
                moved = True
            if timing["takes"] < _MAX_TAKES:
                timing["takes"] += 1
                moved = True

        if _consumed_with_scenario(day, scenario) >= AT_RISK_ERROR_BUDGET_CONSUMED:
            at_risk_reachable = True
            break
        if not moved:
            break

    return ScenarioResult(scenario=scenario, at_risk_reachable=at_risk_reachable)
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_scheduling.py -v`
Expected: PASS (9 tests total in the file)

- [ ] **Step 5: Commit**

```bash
git add agent/tools/scheduling.py tests/test_scheduling.py
git commit -m "$(cat <<'EOF'
feat: generate deterministic replay timing for a built shooting day

replay_day needs per-setup actual_minutes/takes that a screenplay
breakdown has no signal for. generate_scenario invents it: jittered
baseline timing plus a capped, deterministic inflation of the day's
longest scene until error_budget_consumed crosses AT_RISK, so REPLAN
and GATE can fire on a user's own day. Reports at_risk_reachable=False
rather than looping when the cap can't reach it.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Split the planner's decision from its Grafana write

Needed so activation can reuse a cached `MonitoringPlan` (no Gemini call) while still always repeating the (free) Grafana writes (Correction 2).

**Files:**
- Modify: `agent/subagents/planner.py`
- Test: `tests/test_provisioning.py` (existing file — add new tests, don't remove any)

**Interfaces:**
- Consumes: existing `MonitoringPlan`, `provision_day_dashboard`, `provision_burn_rate_alert` (unchanged)
- Produces: `decide_monitoring_plan(day: ShootingDay) -> MonitoringPlan` (renamed from the private `_decide_monitoring_plan` — same behavior, now importable), `provision_with_plan(day: ShootingDay, plan: MonitoringPlan) -> ProvisioningResult` (does the two Grafana writes only, no Gemini call). `provision()` keeps its exact existing signature and behavior, now implemented as `decide_monitoring_plan` + `provision_with_plan`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_provisioning.py` (near the existing planner test, `test_planner_agent_is_built_with_model_from_config`):

```python
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
```

`tests/test_provisioning.py` already defines `DAY = build_day("nominal")` and `import asyncio` at module level — this new test uses both directly, no new imports needed.

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_provisioning.py -v`
Expected: FAIL — `provision_with_plan` doesn't exist yet

- [ ] **Step 3: Implement**

In `agent/subagents/planner.py`, rename `_decide_monitoring_plan` to `decide_monitoring_plan` (drop the leading underscore — every call site in this file), and change `provision()` to:

```python
async def decide_monitoring_plan(day: ShootingDay) -> MonitoringPlan:
    """Runs the planner agent for one turn to get its monitoring decision."""
    agent = _build_planner_agent()
    runner = InMemoryRunner(agent=agent, app_name="martini-planner")
    session = await runner.session_service.create_session(
        app_name="martini-planner", user_id="martini"
    )
    message = types.Content(role="user", parts=[types.Part(text=_day_summary(day))])

    raw_text: str | None = None
    async for event in runner.run_async(
        user_id="martini", session_id=session.id, new_message=message
    ):
        if event.is_final_response() and event.content and event.content.parts:
            raw_text = event.content.parts[0].text

    if raw_text is None:
        raise RuntimeError("planner agent produced no final response")

    return parse_monitoring_plan(raw_text)


async def provision_with_plan(day: ShootingDay, plan: MonitoringPlan) -> ProvisioningResult:
    """Provisions Grafana for one shooting day from an already-decided plan.

    Skips the Gemini call entirely -- used when a project's monitoring
    plan was already decided and cached on an earlier activation
    (Module 7), so re-provisioning on a later activation costs a
    Grafana MCP round trip but not another Gemini request.
    """
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


async def provision(day: ShootingDay) -> ProvisioningResult:
    """Provisions Grafana for one shooting day: decide, then dashboard, then burn-rate alert."""
    plan = await decide_monitoring_plan(day)
    return await provision_with_plan(day, plan)
```

Remove the old `_decide_monitoring_plan` definition (replaced by the above).

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_provisioning.py tests/test_root.py -v`
Expected: PASS — the new test passes, and every pre-existing test in both files still passes unchanged (they exercise `provision()`, `parse_monitoring_plan`, and `_build_planner_agent`, none of which changed behavior).

- [ ] **Step 5: Commit**

```bash
git add agent/subagents/planner.py tests/test_provisioning.py
git commit -m "$(cat <<'EOF'
refactor: split the planner's monitoring decision from its Grafana write

provision_with_plan(day, plan) does only the two Grafana MCP writes,
no Gemini call -- lets Module 7's project activation reuse a cached
MonitoringPlan on later activations while still repeating the (free)
Grafana write every time. provision() is unchanged in behavior,
composed from decide_monitoring_plan + provision_with_plan.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Project storage (`server/projects/`)

**Files:**
- Create: `server/projects/__init__.py`
- Create: `server/projects/models.py`
- Create: `server/projects/storage.py`
- Test: `tests/test_projects_storage.py`

**Interfaces:**
- Consumes: `agent.tools.scheduling.CastEntry`, `emitter.models.{Scene, ShootingDay}`, `agent.subagents.planner.MonitoringPlan`
- Produces:
  - `server.projects.models.ProjectRecord` (pydantic: `slug: str`, `title: str`, `total_days: int`, `crew_size: int`, `created_at: datetime`)
  - `server.projects.storage.ProjectNotFoundError(Exception)`
  - `slugify_title(title: str) -> str`
  - `data_root() -> Path` (the `data/projects/` directory — a function, not a module constant, so tests can monkeypatch it)
  - `create_project(title: str, total_days: int, crew_size: int) -> ProjectRecord`
  - `list_projects() -> list[ProjectRecord]`
  - `load_project(slug: str) -> ProjectRecord`
  - `save_scenes(slug: str, scenes: list[Scene]) -> None` / `load_scenes(slug: str) -> list[Scene] | None`
  - `save_cast(slug: str, cast: list[CastEntry]) -> None` / `load_cast(slug: str) -> list[CastEntry] | None`
  - `save_day(slug: str, day: ShootingDay) -> None` / `load_day(slug: str) -> ShootingDay | None`
  - `save_provisioning_plan(slug: str, plan: MonitoringPlan) -> None` / `load_provisioning_plan(slug: str) -> MonitoringPlan | None`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_projects_storage.py`:

```python
from __future__ import annotations

from datetime import date, datetime

import pytest

from agent.subagents.planner import MonitoringPlan
from agent.tools.scheduling import CastEntry, build_shooting_day
from emitter.models import PageEighths, Scene
from server.projects import storage


@pytest.fixture(autouse=True)
def _isolated_data_root(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "data_root", lambda: tmp_path / "projects")
    yield


def _scene() -> Scene:
    return Scene(
        number="1",
        synopsis="A.",
        page_eighths=PageEighths.from_string("1"),
        int_ext="INT",
        day_night="DAY",
        location="Set",
        cast_ids=[],
        estimated_setups=1,
    )


def test_slugify_title_is_url_safe_and_lowercase():
    assert storage.slugify_title("The Quarry, Part Two!") == "the-quarry-part-two"


def test_create_project_round_trips():
    record = storage.create_project(title="The Quarry", total_days=12, crew_size=40)

    loaded = storage.load_project(record.slug)

    assert loaded.title == "The Quarry"
    assert loaded.total_days == 12
    assert loaded.crew_size == 40


def test_load_project_raises_a_named_error_when_missing():
    with pytest.raises(storage.ProjectNotFoundError):
        storage.load_project("does-not-exist")


def test_list_projects_returns_every_created_project():
    storage.create_project(title="Alpha", total_days=1, crew_size=1)
    storage.create_project(title="Beta", total_days=1, crew_size=1)

    titles = {p.title for p in storage.list_projects()}

    assert titles == {"Alpha", "Beta"}


def test_scenes_round_trip_and_are_none_before_saving():
    record = storage.create_project(title="The Quarry", total_days=1, crew_size=1)

    assert storage.load_scenes(record.slug) is None

    storage.save_scenes(record.slug, [_scene()])

    loaded = storage.load_scenes(record.slug)
    assert loaded is not None
    assert loaded[0].number == "1"


def test_cast_round_trips():
    record = storage.create_project(title="The Quarry", total_days=1, crew_size=1)
    cast = [CastEntry(character_name="MARCUS", previous_night_wrap=datetime(2026, 9, 2, 20, 0))]

    storage.save_cast(record.slug, cast)

    loaded = storage.load_cast(record.slug)
    assert loaded is not None
    assert loaded[0].character_name == "MARCUS"


def test_day_round_trips():
    record = storage.create_project(title="The Quarry", total_days=1, crew_size=1)
    day = build_shooting_day([_scene()], [], day_number=1, shoot_date=date(2026, 9, 8), production_title="The Quarry")

    storage.save_day(record.slug, day)

    loaded = storage.load_day(record.slug)
    assert loaded is not None
    assert loaded.production_title == "The Quarry"
    assert loaded.day_number == 1


def test_provisioning_plan_round_trips_and_is_none_before_saving():
    record = storage.create_project(title="The Quarry", total_days=1, crew_size=1)

    assert storage.load_provisioning_plan(record.slug) is None

    plan = MonitoringPlan(burn_rate_threshold=1.4, evaluation_window_minutes=10, annotation="Watch it.")
    storage.save_provisioning_plan(record.slug, plan)

    loaded = storage.load_provisioning_plan(record.slug)
    assert loaded is not None
    assert loaded.burn_rate_threshold == 1.4
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_projects_storage.py -v`
Expected: FAIL — `server.projects` doesn't exist yet

- [ ] **Step 3: Implement**

Create `server/projects/__init__.py` (empty).

Create `server/projects/models.py`:

```python
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class ProjectRecord(BaseModel):
    slug: str
    title: str
    total_days: int
    crew_size: int
    created_at: datetime
```

Create `server/projects/storage.py`:

```python
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
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_projects_storage.py -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add server/projects/ tests/test_projects_storage.py
git commit -m "$(cat <<'EOF'
feat: JSON-file storage for user-created productions

data/projects/<slug>/{project,scenes,cast,day,provisioning}.json --
each save/load pair independently testable, no database, matching
CLAUDE.md's storage constraint for Module 7.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Project API routes (`server/routes/projects.py`)

**Files:**
- Create: `server/routes/__init__.py`
- Create: `server/routes/projects.py`
- Test: `tests/test_projects_routes.py`

**Interfaces:**
- Consumes: `server.projects.storage.*`, `server.projects.models.ProjectRecord`, `agent.tools.breakdown.{breakdown_script, BreakdownParseError, BreakdownQuotaExceeded}`, `agent.tools.scheduling.{CastEntry, build_shooting_day}`, `agent.subagents.planner.{decide_monitoring_plan, provision_with_plan}`, `server.state.STATE`
- Produces: `router: fastapi.APIRouter` mounted at `/api/projects` by Task 11's `server/app.py`. Route table exactly as the spec: `GET /`, `POST /`, `GET /{slug}`, `POST /{slug}/script`, `POST /{slug}/cast`, `POST /{slug}/day`, `POST /{slug}/activate`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_projects_routes.py`:

```python
from __future__ import annotations

from datetime import datetime

import pytest
from starlette.testclient import TestClient

from agent.subagents.planner import MonitoringPlan, ProvisioningResult
from agent.tools.scheduling import CastEntry
from emitter.models import PageEighths, Scene
from server import app as app_module
from server.projects import storage as storage_module
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


def _fake_startup_provisioning_result() -> ProvisioningResult:
    return ProvisioningResult(
        dashboard_uid="martini-day-14",
        dashboard_url="https://example.grafana.net/d/martini-day-14",
        alert_rule_uid="alert-uid",
        alert_rule_url="https://example.grafana.net/alerting/grafana/alert-uid/view",
        burn_rate_threshold=1.35,
        evaluation_window_minutes=10,
        annotation="Losing time against Scene 42.",
        provisioned_at=datetime.now(),
    )


@pytest.fixture
def client(monkeypatch):
    # TestClient(app) runs the real FastAPI lifespan on entry, which
    # calls _provision_at_startup() -- mocked here exactly like
    # tests/test_app.py's own `client` fixture, so opening a TestClient
    # in this file never makes a real Gemini/Grafana call.
    async def _fake_provision(day):
        return _fake_startup_provisioning_result()

    monkeypatch.setattr(app_module, "provision", _fake_provision)
    monkeypatch.setattr(app_module, "save_cached_provisioning", lambda result: None)

    with TestClient(app_module.app) as test_client:
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
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_projects_routes.py -v`
Expected: FAIL — `server.routes` doesn't exist yet

- [ ] **Step 3: Implement**

Create `server/routes/__init__.py` (empty).

Create `server/routes/projects.py`:

```python
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
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_projects_routes.py -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add server/routes/ tests/test_projects_routes.py
git commit -m "$(cat <<'EOF'
feat: project API routes -- create, script upload, cast, day, activate

Orchestrates storage + breakdown + scheduling into the six endpoints
the /projects console page needs. Script upload caches scenes.json and
never re-parses a script twice; a 429 from Gemini surfaces as a plain
422/429 HTTP error, never a 500. Activation reuses a cached monitoring
plan after the first live provision.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: `AppState` gains an active project

**Files:**
- Modify: `server/state.py`
- Test: `tests/test_state.py` (existing file — add tests)

**Interfaces:**
- Produces: `AppState.active_project_slug: str | None` (default `None`), `AppState.active_total_days: int` (default `TOTAL_SHOOT_DAYS`)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_state.py`:

```python
def test_active_project_defaults_to_none_and_day_14_total_days():
    state = AppState()

    assert state.active_project_slug is None
    assert state.active_total_days == 32
```

(`32` matches `TOTAL_SHOOT_DAYS` already defined in `server/state.py` — import it in the test if not already imported: `from server.state import TOTAL_SHOOT_DAYS`, and assert against that name rather than the literal, to avoid the test silently drifting from the constant.)

Replace the literal with the import:

```python
from server.state import TOTAL_SHOOT_DAYS, AppState, DaySnapshot, PaceSnapshot, TimelineSnapshot


def test_active_project_defaults_to_none_and_day_14_total_days():
    state = AppState()

    assert state.active_project_slug is None
    assert state.active_total_days == TOTAL_SHOOT_DAYS
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_state.py -v`
Expected: FAIL — `AttributeError: 'AppState' object has no attribute 'active_project_slug'`

- [ ] **Step 3: Implement**

In `server/state.py`, in `AppState.__init__`, add after `self.plan_day = build_day(DEFAULT_SCENARIO)`:

```python
        self.active_project_slug: str | None = None
        self.active_total_days: int = TOTAL_SHOOT_DAYS
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_state.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add server/state.py tests/test_state.py
git commit -m "$(cat <<'EOF'
feat: AppState tracks the active project

active_project_slug/active_total_days default to None/TOTAL_SHOOT_DAYS
(Day 14's unchanged behavior) and are set only by
server/routes/projects.py's /activate endpoint.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: `run_replay` uses the active project's day

**Files:**
- Modify: `server/replay.py`
- Test: `tests/test_replay.py` (existing file — add a test for the pure selection logic; the threaded path stays covered by manual verification, matching this file's existing documented convention)

**Interfaces:**
- Consumes: `server.state.STATE.active_project_slug`, `server.projects.storage.load_day`, `agent.tools.scheduling.generate_scenario`
- Produces: a new pure helper `_active_day_and_scenario() -> tuple[ShootingDay, dict[str, dict]]` that `run_replay` calls instead of always calling `build_day(scenario_name)` / `load_scenario(scenario_name)`; behavior is unchanged when no project is active.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_replay.py`:

```python
def test_active_day_and_scenario_falls_back_to_the_named_scenario_when_no_project_is_active(monkeypatch):
    from server import replay as replay_module

    with STATE.lock:
        STATE.active_project_slug = None

    day, scenario = replay_module._active_day_and_scenario("nominal")

    assert day.day_number == 14
    assert "1a" in scenario


def test_active_day_and_scenario_loads_the_active_project(monkeypatch):
    from server import replay as replay_module
    from server.projects import storage as storage_module

    fake_day = build_day("nominal")

    with STATE.lock:
        STATE.active_project_slug = "the-quarry"

    monkeypatch.setattr(storage_module, "load_day", lambda slug: fake_day if slug == "the-quarry" else None)

    day, scenario = replay_module._active_day_and_scenario("nominal")

    assert day is fake_day
    assert set(scenario.keys()) == {s.id for s in fake_day.setups}

    with STATE.lock:
        STATE.active_project_slug = None
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_replay.py -v`
Expected: FAIL — `_active_day_and_scenario` doesn't exist yet

- [ ] **Step 3: Implement**

In `server/replay.py`, add imports and the helper, then use it in `run_replay`:

```python
from agent.tools.scheduling import generate_scenario
from server.projects import storage as projects_storage


def _active_day_and_scenario(scenario_name: str) -> tuple[ShootingDay, dict[str, dict]]:
    """The day + replay timing run_replay should use this run.

    Falls back to the named built-in scenario (unchanged behavior) when
    no project has been activated. When one has, its own day.json and a
    freshly-generated scenario (Module 7) are used instead -- the
    nominal/slipping toggle is ignored, since the console never exposes
    it anyway.
    """
    if STATE.active_project_slug is not None:
        day = projects_storage.load_day(STATE.active_project_slug)
        if day is not None:
            return day, generate_scenario(day).scenario

    return build_day(scenario_name), load_scenario(scenario_name)
```

Replace the first two lines of `run_replay`:

```python
def run_replay(scenario_name: str, run_id: int) -> None:
    """The background thread body for one Start click. Owns `day` exclusively."""
    day, scenario = _active_day_and_scenario(scenario_name)
    with STATE.lock:
        STATE.plan_day = day
```

(delete the old `scenario = load_scenario(scenario_name)` line that followed — it's now folded into `_active_day_and_scenario`.)

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_replay.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add server/replay.py tests/test_replay.py
git commit -m "$(cat <<'EOF'
feat: replay the active project's day when one is activated

_active_day_and_scenario falls back to the existing nominal/slipping
scenario files unchanged when no project is active; otherwise loads
the project's day.json and a freshly-generated replay scenario
(Module 7's generate_scenario) instead.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: Wire the router into `server/app.py`; thread `total_days`; SPA fallback

**Files:**
- Modify: `server/app.py`
- Test: `tests/test_app.py` (existing file — add tests)

**Interfaces:**
- Produces: `/api/projects/*` live (Task 8's router included), `GET /projects` returns the built console `index.html`, `_initial_snapshot()`'s `total_days` reflects `STATE.active_total_days`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_app.py`:

```python
def test_initial_snapshot_reports_the_active_project_total_days():
    from server.state import STATE

    with STATE.lock:
        STATE.active_total_days = 5

    snapshot = app_module._initial_snapshot()

    assert snapshot.total_days == 5

    with STATE.lock:
        STATE.active_total_days = 32  # restore the default for other tests


def test_projects_route_is_registered(client):
    response = client.get("/api/projects")
    assert response.status_code == 200
```

(`/projects`'s HTML-fallback route needs `web/dist/index.html` to exist to return 200 — since that directory is only present after a frontend build, and this test suite runs before Task 16 produces one in CI order, assert on the route existing rather than its content: use `client.app.routes` — simpler: skip an HTTP assertion for `/projects` here and instead assert the route is registered, e.g. `assert any(r.path == "/projects" for r in app_module.app.routes)`.)

Replace that second test with:

```python
def test_projects_page_route_is_registered():
    assert any(getattr(route, "path", None) == "/projects" for route in app_module.app.routes)
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_app.py -v`
Expected: FAIL — `total_days` still hardcoded, `/projects` route doesn't exist, `/api/projects` not registered

- [ ] **Step 3: Implement**

In `server/app.py`:

1. Add the import (alongside the other `# noqa: E402` imports after `load_dotenv()`):

```python
from server.routes.projects import router as projects_router  # noqa: E402
```

2. Include the router (after `app = FastAPI(lifespan=lifespan)`):

```python
app.include_router(projects_router)
```

3. In `_initial_snapshot()`, change the `DaySnapshot(...)` construction to pass `total_days` explicitly:

```python
    return DaySnapshot(
        run_id=run_id,
        event_type="connected",
        status="idle",
        day_number=day.day_number,
        total_days=STATE.active_total_days,
        production_title=day.production_title,
        ...
```

(keep every other existing field as-is; only the added `total_days=STATE.active_total_days,` line is new.)

4. Add `FileResponse` to the existing import line:

```python
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
```

5. Add the SPA fallback route, right before the existing `if _WEB_DIST.exists(): app.mount(...)` block:

```python
@app.get("/projects")
async def projects_page() -> FileResponse | JSONResponse:
    index_path = _WEB_DIST / "index.html"
    if not index_path.exists():
        return JSONResponse({"detail": "console not built"}, status_code=404)
    return FileResponse(index_path)
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_app.py -v`
Expected: PASS

- [ ] **Step 5: Run the full backend suite**

Run: `uv run pytest -q`
Expected: PASS, no regressions anywhere in the suite.

- [ ] **Step 6: Commit**

```bash
git add server/app.py tests/test_app.py
git commit -m "$(cat <<'EOF'
feat: mount project routes, /projects SPA fallback, active total_days

server/app.py now includes the projects router, serves the built
console for a direct /projects load (today only / resolves through
StaticFiles' directory-index behavior), and threads
STATE.active_total_days into the idle snapshot instead of the
hardcoded Day 14 constant.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 12: Frontend types + API client additions

**Files:**
- Modify: `web/src/types.ts`
- Modify: `web/src/api.ts`

**Interfaces:**
- Produces (in `types.ts`): `ProjectRecord`, `Scene`, `CastEntry` (frontend mirrors of the backend pydantic models — field names identical, dates as `string`)
- Produces (in `api.ts`): `listProjects()`, `createProject(input)`, `uploadScript(slug, file)`, `saveCast(slug, cast)`, `buildDay(slug, dayNumber, date)`, `activateProject(slug)`, `getProject(slug)`

- [ ] **Step 1: Add types**

Append to `web/src/types.ts`:

```typescript
export interface ProjectRecord {
  slug: string;
  title: string;
  total_days: number;
  crew_size: number;
  created_at: string;
}

export type StripColorSource = "INT" | "EXT";

export interface Scene {
  number: string;
  synopsis: string;
  page_eighths: { eighths: number };
  int_ext: "INT" | "EXT";
  day_night: "DAY" | "NIGHT";
  location: string;
  cast_ids: string[];
  estimated_setups: number;
}

export interface CastEntry {
  character_name: string;
  is_minor: boolean;
  previous_night_wrap: string;
  minimum_turnaround_hours: number | null;
}

export interface ProjectDetail {
  project: ProjectRecord;
  scenes: Scene[] | null;
  cast: CastEntry[] | null;
  has_day: boolean;
}
```

- [ ] **Step 2: Add API client functions**

Append to `web/src/api.ts`:

```typescript
import type { CastEntry, ProjectDetail, ProjectRecord, Scene } from "./types";

async function _json<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(body.detail ?? `request failed: ${response.status}`);
  }
  return response.json();
}

export function listProjects(): Promise<ProjectRecord[]> {
  return fetch("/api/projects").then((r) => _json(r));
}

export function createProject(input: { title: string; total_days: number; crew_size: number }): Promise<ProjectRecord> {
  return fetch("/api/projects", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  }).then((r) => _json(r));
}

export function getProject(slug: string): Promise<ProjectDetail> {
  return fetch(`/api/projects/${slug}`).then((r) => _json(r));
}

export function uploadScript(slug: string, file: File): Promise<{ scenes: Scene[] }> {
  const form = new FormData();
  form.append("file", file);
  return fetch(`/api/projects/${slug}/script`, { method: "POST", body: form }).then((r) => _json(r));
}

export function saveCast(slug: string, cast: CastEntry[]): Promise<{ ok: true }> {
  return fetch(`/api/projects/${slug}/cast`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(cast),
  }).then((r) => _json(r));
}

export function buildDay(slug: string, dayNumber: number, date: string): Promise<unknown> {
  return fetch(`/api/projects/${slug}/day`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ day_number: dayNumber, date }),
  }).then((r) => _json(r));
}

export function activateProject(slug: string): Promise<{ ok: true }> {
  return fetch(`/api/projects/${slug}/activate`, { method: "POST" }).then((r) => _json(r));
}
```

- [ ] **Step 3: Verify the build type-checks**

Run: `cd web && npm run build`
Expected: succeeds (`tsc -b && vite build`) — `web/dist` is regenerated but not yet committed until Task 16, since nothing consumes these new exports yet.

- [ ] **Step 4: Commit**

```bash
git add web/src/types.ts web/src/api.ts
git commit -m "$(cat <<'EOF'
feat: frontend types and API client for the projects endpoints

Mirrors server/routes/projects.py's request/response shapes so the
new-production flow (next task) has a typed client to call.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 13: Hand-rolled routing; move the console into `pages/Console.tsx`

**Files:**
- Create: `web/src/router.ts`
- Create: `web/src/pages/Console.tsx` (existing `App.tsx` body, moved verbatim)
- Modify: `web/src/App.tsx` (becomes the route switch)

**Interfaces:**
- Produces: `useRoute(): string` (the current pathname, re-rendering on navigation), `navigate(path: string): void`, `Link` component (`<Link to="/projects">Projects</Link>`, intercepts the click into `navigate` instead of a full page load)

- [ ] **Step 1: Create the router**

Create `web/src/router.ts`:

```typescript
import { useEffect, useState } from "react";

const _listeners = new Set<() => void>();

export function navigate(path: string): void {
  if (path === window.location.pathname) return;
  window.history.pushState({}, "", path);
  _listeners.forEach((listener) => listener());
}

export function useRoute(): string {
  const [pathname, setPathname] = useState(window.location.pathname);

  useEffect(() => {
    const onChange = () => setPathname(window.location.pathname);
    _listeners.add(onChange);
    window.addEventListener("popstate", onChange);
    return () => {
      _listeners.delete(onChange);
      window.removeEventListener("popstate", onChange);
    };
  }, []);

  return pathname;
}
```

Create `web/src/components/Link.tsx`:

```typescript
import type { ReactNode } from "react";
import { navigate } from "../router";

export function Link({ to, className, children }: { to: string; className?: string; children: ReactNode }) {
  return (
    <a
      href={to}
      className={className}
      onClick={(event) => {
        event.preventDefault();
        navigate(to);
      }}
    >
      {children}
    </a>
  );
}
```

- [ ] **Step 2: Move the console into its own page**

Move the entire current contents of `web/src/App.tsx` into a new `web/src/pages/Console.tsx`, renaming the exported function from `App` to `Console`, and fixing the relative import paths (one extra `../` level since it's now under `pages/`):

```typescript
import { CastClocks } from "../components/CastClocks";
import { DayTimeline } from "../components/DayTimeline";
import { ErrorBudgetBar } from "../components/ErrorBudgetBar";
import { Header } from "../components/Header";
import { PaceLine } from "../components/PaceLine";
import { ProvisioningFooter } from "../components/ProvisioningFooter";
import { RecoveryOptions } from "../components/RecoveryOptions";
import { StartButton } from "../components/StartButton";
import { StripBoard } from "../components/StripBoard";
import { Verdict } from "../components/Verdict";
import { useDaySnapshot } from "../hooks/useDaySnapshot";

export default function Console() {
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
      <div className="bg-paper text-ink">
        <Header snapshot={snapshot} />
        <Verdict snapshot={snapshot} />
        <ErrorBudgetBar snapshot={snapshot} />
        <DayTimeline timeline={snapshot.timeline} />
        <PaceLine pace={snapshot.pace} />
      </div>
      <div className="flex justify-center px-4 py-0.5">
        <StartButton status={snapshot.status} />
      </div>
      {snapshot.error_message && (
        <p className="px-4 py-1 font-body text-xs text-paper/70">Stalled: {snapshot.error_message}</p>
      )}
      <StripBoard
        scenes={snapshot.scenes}
        currentScene={snapshot.current_scene}
        shotScenes={snapshot.shot_scene_numbers}
      />
      <CastClocks clocks={snapshot.cast_clocks} />
      {snapshot.recovery && (
        <div className="mt-0.5 border-t border-paper/10 pt-0.5">
          <RecoveryOptions recovery={snapshot.recovery} />
        </div>
      )}
      <div className="mt-auto">
        <ProvisioningFooter
          provisioning={snapshot.provisioning}
          incidentUrl={snapshot.recovery?.incident_url ?? null}
        />
      </div>
    </main>
  );
}
```

- [ ] **Step 3: Rewrite `App.tsx` as the route switch**

Replace the full contents of `web/src/App.tsx`:

```typescript
import Console from "./pages/Console";
import Projects from "./pages/Projects";
import { useRoute } from "./router";

export default function App() {
  const pathname = useRoute();

  if (pathname === "/projects") return <Projects />;
  return <Console />;
}
```

(`pages/Projects.tsx` doesn't exist yet — Task 14 creates it. This won't type-check until then; that's expected and is why Task 14 follows immediately, before any intermediate build/commit gate.)

- [ ] **Step 4: Commit (folded with Task 14 — see that task's Step 5)**

This task has no independent commit: `App.tsx` doesn't compile without `pages/Projects.tsx`. Proceed directly to Task 14 and commit both together.

---

## Task 14: `/projects` page — grid + new-production flow

**Files:**
- Create: `web/src/pages/Projects.tsx`
- Create: `web/src/pages/NewProduction.tsx`
- Modify: `web/src/components/Header.tsx` (active-project line + link, only task in this plan touching an existing console component, and only additively — its existing render path for `snapshot` is unchanged)

**Interfaces:**
- Consumes: Task 12's `api.ts` functions and `types.ts` types, Task 13's `useRoute`/`navigate`/`Link`
- Produces: `Projects` (default export of `pages/Projects.tsx`), `NewProduction` (default export of `pages/NewProduction.tsx`)

- [ ] **Step 1: Build the new-production flow**

Create `web/src/pages/NewProduction.tsx`:

```typescript
import { useState } from "react";
import { activateProject, buildDay, createProject, saveCast, uploadScript } from "../api";
import { navigate } from "../router";
import type { CastEntry, ProjectRecord, Scene } from "../types";

type Step = "details" | "script" | "cast";

const STRIP_CLASS: Record<string, string> = {
  "INT-DAY": "bg-strip-day-int text-ink",
  "EXT-DAY": "bg-strip-day-ext text-ink",
  "INT-NIGHT": "bg-strip-night-int text-ink",
  "EXT-NIGHT": "bg-strip-night-ext text-ink",
};

export default function NewProduction({ onCancel }: { onCancel: () => void }) {
  const [step, setStep] = useState<Step>("details");
  const [project, setProject] = useState<ProjectRecord | null>(null);
  const [title, setTitle] = useState("");
  const [totalDays, setTotalDays] = useState(1);
  const [crewSize, setCrewSize] = useState(30);
  const [scenes, setScenes] = useState<Scene[]>([]);
  const [parsing, setParsing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [cast, setCast] = useState<CastEntry[]>([]);
  const [opening, setOpening] = useState(false);

  async function handleCreateDetails() {
    setError(null);
    try {
      const created = await createProject({ title, total_days: totalDays, crew_size: crewSize });
      setProject(created);
      setStep("script");
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function handleScriptUpload(file: File) {
    if (!project) return;
    setParsing(true);
    setError(null);
    try {
      const result = await uploadScript(project.slug, file);
      setScenes(result.scenes);
      const names = new Set<string>();
      for (const scene of result.scenes) {
        for (const id of scene.cast_ids) names.add(id);
      }
      setCast(
        [...names].map((id) => ({
          character_name: id.toUpperCase(),
          is_minor: false,
          previous_night_wrap: "",
          minimum_turnaround_hours: null,
        })),
      );
      setStep("cast");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setParsing(false);
    }
  }

  async function handleOpen() {
    if (!project) return;
    setOpening(true);
    setError(null);
    try {
      await saveCast(project.slug, cast);
      await buildDay(project.slug, 1, new Date().toISOString().slice(0, 10));
      await activateProject(project.slug);
      navigate("/");
    } catch (err) {
      setError((err as Error).message);
      setOpening(false);
    }
  }

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-4 bg-paper p-6 text-ink">
      <div className="flex items-center justify-between">
        <h2 className="font-narrow text-lg font-bold uppercase tracking-wide">New production</h2>
        <button type="button" onClick={onCancel} className="font-body text-xs text-ink/50 underline">
          Cancel
        </button>
      </div>

      {error && <p className="font-body text-xs text-burn">{error}</p>}

      <section className="flex flex-col gap-2">
        <p className="font-narrow text-xs uppercase tracking-widest text-ink/50">1. Details</p>
        <input
          className="border border-ink/20 bg-paper px-2 py-1 font-body text-sm"
          placeholder="Production title"
          value={title}
          disabled={step !== "details"}
          onChange={(e) => setTitle(e.target.value)}
        />
        <div className="flex gap-2">
          <input
            type="number"
            min={1}
            className="w-32 border border-ink/20 bg-paper px-2 py-1 font-body text-sm"
            placeholder="Total shoot days"
            value={totalDays}
            disabled={step !== "details"}
            onChange={(e) => setTotalDays(Number(e.target.value))}
          />
          <input
            type="number"
            min={1}
            className="w-32 border border-ink/20 bg-paper px-2 py-1 font-body text-sm"
            placeholder="Crew size"
            value={crewSize}
            disabled={step !== "details"}
            onChange={(e) => setCrewSize(Number(e.target.value))}
          />
        </div>
        {step === "details" && (
          <button
            type="button"
            onClick={handleCreateDetails}
            disabled={!title || totalDays < 1}
            className="w-fit rounded-sm bg-ink px-4 py-1.5 font-narrow text-sm font-bold uppercase text-paper disabled:opacity-40"
          >
            Continue
          </button>
        )}
      </section>

      {step !== "details" && (
        <section className="flex flex-col gap-2">
          <p className="font-narrow text-xs uppercase tracking-widest text-ink/50">2. Screenplay</p>
          {step === "script" && (
            <>
              <input
                type="file"
                accept="application/pdf"
                disabled={parsing}
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) handleScriptUpload(file);
                }}
              />
              {parsing && <p className="font-body text-xs text-ink/50">Reading the script — this can take 10–30s…</p>}
            </>
          )}
          {scenes.length > 0 && (
            <ul className="flex flex-col gap-px">
              {scenes.map((scene) => (
                <li
                  key={scene.number}
                  className={`flex items-center gap-2 rounded-[2px] px-2 py-0.5 font-narrow text-xs ${STRIP_CLASS[`${scene.int_ext}-${scene.day_night}`] ?? "bg-strip-day-int text-ink"}`}
                >
                  <span className="w-10 shrink-0 font-semibold">Sc.{scene.number}</span>
                  <span className="flex-1 truncate">{scene.synopsis}</span>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      {step === "cast" && (
        <section className="flex flex-col gap-2">
          <p className="font-narrow text-xs uppercase tracking-widest text-ink/50">3. Cast</p>
          <table className="w-full text-left font-body text-xs">
            <thead>
              <tr className="text-ink/50">
                <th className="pb-1">Character</th>
                <th className="pb-1">Minor</th>
                <th className="pb-1">Previous night's wrap</th>
              </tr>
            </thead>
            <tbody>
              {cast.map((entry, index) => (
                <tr key={index}>
                  <td className="py-0.5">
                    <input
                      className="w-full border border-ink/20 bg-paper px-1 py-0.5"
                      value={entry.character_name}
                      onChange={(e) => {
                        const next = [...cast];
                        next[index] = { ...entry, character_name: e.target.value };
                        setCast(next);
                      }}
                    />
                  </td>
                  <td className="py-0.5 text-center">
                    <input
                      type="checkbox"
                      checked={entry.is_minor}
                      onChange={(e) => {
                        const next = [...cast];
                        next[index] = { ...entry, is_minor: e.target.checked };
                        setCast(next);
                      }}
                    />
                  </td>
                  <td className="py-0.5">
                    <input
                      type="datetime-local"
                      className="border border-ink/20 bg-paper px-1 py-0.5"
                      value={entry.previous_night_wrap}
                      onChange={(e) => {
                        const next = [...cast];
                        next[index] = { ...entry, previous_night_wrap: e.target.value };
                        setCast(next);
                      }}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <button
            type="button"
            onClick={handleOpen}
            disabled={opening || cast.some((c) => !c.previous_night_wrap)}
            className="w-fit rounded-sm bg-ink px-4 py-1.5 font-narrow text-sm font-bold uppercase text-paper disabled:opacity-40"
          >
            {opening ? "Opening…" : "Open shooting day"}
          </button>
        </section>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Build the projects grid**

Create `web/src/pages/Projects.tsx`:

```typescript
import { useEffect, useState } from "react";
import { listProjects } from "../api";
import { Link } from "../components/Link";
import type { ProjectRecord } from "../types";
import NewProduction from "./NewProduction";

export default function Projects() {
  const [projects, setProjects] = useState<ProjectRecord[]>([]);
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    listProjects().then(setProjects);
  }, [creating]);

  return (
    <main className="min-h-screen bg-board px-6 py-8 text-paper">
      <div className="mx-auto flex max-w-3xl items-center justify-between pb-6">
        <h1 className="font-narrow text-xl font-bold uppercase tracking-widest">Productions</h1>
        <Link to="/" className="font-body text-xs text-paper/60 underline">
          Back to the console
        </Link>
      </div>

      {creating ? (
        <NewProduction onCancel={() => setCreating(false)} />
      ) : (
        <div className="mx-auto grid max-w-3xl grid-cols-2 gap-3 sm:grid-cols-3">
          {projects.map((project) => (
            <div key={project.slug} className="rounded-sm bg-paper p-3 text-ink">
              <p className="font-narrow text-sm font-bold">{project.title}</p>
              <p className="font-body text-xs text-ink/50">
                {project.total_days} days · crew {project.crew_size}
              </p>
            </div>
          ))}
          <button
            type="button"
            onClick={() => setCreating(true)}
            className="flex items-center justify-center rounded-sm border border-dashed border-paper/30 p-3 font-narrow text-sm font-bold uppercase text-paper/60"
          >
            + New production
          </button>
        </div>
      )}
    </main>
  );
}
```

- [ ] **Step 3: Header gets the active-project line**

Read `web/src/components/Header.tsx` (Task 13 did not touch it) and modify it to accept an optional active-project title, additively — the existing `Day {n} of {total}` line and clock are untouched:

```typescript
import { Link } from "./Link";
import type { DaySnapshot } from "../types";

export function Header({ snapshot, activeProjectTitle }: { snapshot: DaySnapshot; activeProjectTitle?: string }) {
  return (
    <header className="px-4 pt-1.5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="font-narrow text-lg font-bold uppercase tracking-[0.2em] text-ink">MARTINI</div>
          <div className="font-body text-[11px] leading-tight text-ink/55">making the day</div>
          <p className="mt-0.5 max-w-xs font-body text-[10px] leading-snug text-ink/40">
            Watches the shooting day. Warns you before you lose it. Won't suggest anything that breaks a union
            rule.
          </p>
          {activeProjectTitle && (
            <p className="mt-0.5 font-body text-[10px] text-ink/50">
              {activeProjectTitle} · <Link to="/projects" className="underline">change production</Link>
            </p>
          )}
        </div>
        <div className="shrink-0 font-narrow text-xs uppercase tracking-widest text-ink/50">
          Day {snapshot.day_number} of {snapshot.total_days}
        </div>
      </div>
      <div className="mt-0.5 font-narrow text-3xl font-semibold tracking-tight tabular-nums text-ink sm:text-4xl">
        {snapshot.clock ?? "--:--"}
      </div>
    </header>
  );
}
```

In `web/src/pages/Console.tsx`, pass the new prop — the production title is already on the snapshot (`snapshot.production_title`), and it's only meaningfully different from the Day 14 default when a project is active, which the snapshot alone can't tell apart from "Day 14, unmodified." Use `snapshot.production_title !== "Invented Production"` as the signal (the one hardcoded title `emitter/simulator.py`'s `build_day` always uses):

```typescript
        <Header snapshot={snapshot} activeProjectTitle={snapshot.production_title !== "Invented Production" ? snapshot.production_title : undefined} />
```

- [ ] **Step 4: Verify the build**

Run: `cd web && npm run build`
Expected: succeeds with no type errors.

- [ ] **Step 5: Manually smoke-test the routing**

Run: `cd web && npm run dev` (with the backend running separately: `uv run uvicorn server.app:app --reload` in another terminal)
- Load `http://localhost:5173/` → console renders (Day 14)
- Click through to `/projects` via the header link → grid renders, "+ New production" tile present
- Click "+ New production" → three-step form renders inline

Expected: no console errors, both routes render.

- [ ] **Step 6: Commit (Tasks 13 + 14 together)**

```bash
git add web/src/App.tsx web/src/router.ts web/src/pages/ web/src/components/Link.tsx web/src/components/Header.tsx
git commit -m "$(cat <<'EOF'
feat: /projects console page and hand-rolled client routing

No new dependency: a small pathname hook + history.pushState swap
between the console (moved to pages/Console.tsx, unchanged) and the
new /projects grid + three-step new-production flow. Header gains an
active-project line, shown only when a project (not Day 14) is live.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 15: Commit the built console

`web/dist` is committed per CLAUDE.md (the deploy host has no Node). This task exists because every prior frontend change in this plan needs its build artifact committed exactly once, at the end, rather than after each task.

**Files:**
- Modify: `web/dist/**` (generated)

- [ ] **Step 1: Build**

Run: `cd web && npm run build`

- [ ] **Step 2: Commit**

```bash
git add web/dist
git commit -m "$(cat <<'EOF'
chore: rebuild the committed console for the /projects module

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 16: End-to-end verification

**Files:** none (verification only; fix-forward commits land wherever the bug actually is if anything surfaces)

- [ ] **Step 1: Run the full backend test suite**

Run: `uv run pytest -q`
Expected: PASS, full suite (existing + every test this plan added).

- [ ] **Step 2: Generate an invented screenplay PDF for testing**

Write a short (2–3 scene) invented screenplay as plain text — no real film, studio, or person — then convert it to a PDF using whatever's available in this environment (e.g. `pandoc`, `weasyprint`, or a minimal `reportlab` script if one of those is installed; check with `which pandoc` / `python3 -c "import reportlab"` first). Save it to the scratchpad directory, not the repo.

- [ ] **Step 3: Run the real server**

Run: `uv run uvicorn server.app:app --reload` (needs real `GOOGLE_API_KEY`/`GRAFANA_URL`/`GRAFANA_SERVICE_ACCOUNT_TOKEN` in `.env` — this is the one step in this plan that spends real Gemini quota and writes to real Grafana)

- [ ] **Step 4: Walk the full flow in a browser**

1. `http://localhost:8000/` → confirm Day 14 still renders exactly as before this module
2. `/projects` → create a production, upload the invented PDF, confirm scenes return with sane page-eighths (not all "1/8", not absurdly large), fill in cast, "Open shooting day"
3. Confirm redirect to `/` shows the new production's title in the header, not Day 14's
4. Click Start, watch the day replay — confirm it's visibly a different day (different scenes/cast than Day 14)
5. Let it run until `error_budget_consumed` crosses 0.75 — confirm the REPLAN → GATE cycle fires and a rejection card renders with a plain-English reason grounded in the uploaded script's actual cast/turnaround data
6. Check the Grafana dashboard link in the provisioning footer opens a dashboard titled for this production, not Day 14

- [ ] **Step 5: Confirm the quota-cache behavior**

Re-activate the same production a second time (re-upload isn't needed — scenes.json is already cached). Confirm in server logs / by inspecting `data/projects/<slug>/provisioning.json` that the second activation did not call the planner agent again (no new Gemini request in the logs), only a fresh Grafana write.

- [ ] **Step 6: Report results**

Summarize in the final response to the user: what worked exactly as verified above, and call out plainly anything that didn't (a parsing edge case, a UI rough edge, a quota surprise) rather than claiming full success if any step above didn't hold up. This is the CLAUDE.md working-agreement bar: "If you cannot make something work, say so plainly."

---

## Self-Review

**Spec coverage:** every section of `docs/superpowers/specs/2026-09-08-projects-script-breakdown-design.md` maps to a task — Storage (Task 7), backend routes (Task 8), `breakdown.py` + quota (Tasks 2–3), `scheduling.py` (Tasks 4–5), server wiring incl. both Corrections 1–2 (Tasks 5, 6, 8, 9, 10, 11), Correction 3's "quota file is dev-only" (Task 2's docstring + Global Constraints), frontend routing + `/projects` + new-production flow + Header (Tasks 12–14), testing (folded into each task's TDD steps), verification (Task 16).

**Placeholder scan:** no TBD/TODO; every step has real code or an exact command.

**Type consistency:** `CastEntry` defined once (Task 4, `agent/tools/scheduling.py`) and imported everywhere else that needs it (Tasks 7, 8, 12) rather than redefined. `ScenarioResult.scenario`'s shape (`dict[str, dict[str, int]]`) matches `emitter.simulator.load_scenario`'s return type exactly, verified against `replay_day`'s actual usage (`timing["actual_minutes"]`, `timing["takes"]`) in Task 5. `slugify_character_name` defined once (Task 3) and reused by Task 4 rather than reimplemented — verified by Task 4's join test.

---

Plan complete and saved to `docs/superpowers/plans/2026-09-08-projects-script-breakdown.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
