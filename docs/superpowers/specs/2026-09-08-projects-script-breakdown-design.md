# Module 7 — Projects & script breakdown

Status: approved, ready for implementation plan.

## Goal

MARTINI takes real input. A user creates a production, uploads a
screenplay PDF, Gemini breaks it into scenes, enters cast with
turnaround constraints, and the console runs on that generated day —
without touching how the console renders, how the gate decides, or
how the replanner is grounded. Day 14 stays the default when nothing
has been activated.

Routing constraint: `/` stays the console and remains the landing
page. `/projects` is reached only from a header link. A judge who
lands on `/` cold must see a running shooting day, never an empty
projects screen.

## Why this needed a design pass, not just implementation

The literal ask ("build ShootingDay, watch the console replay it")
assumes the console can replay any `ShootingDay`. It can't, as built.
`emitter/simulator.py`'s `replay_day` walks a *separate* scenario
dict — `setup_id -> {actual_minutes, takes}` — that today is
hand-authored fiction in `emitter/scenarios/*.yaml`, decoupled from
the `ShootingDay` plan itself (`Setup.actual_minutes` starts `None`
and is filled in only as replay walks the scenario). A screenplay
breakdown has no signal for how long a setup actually took. Something
has to invent that signal, or activating a project produces a day with
nothing to replay.

The other gap: Grafana metrics carry no per-day label
(`agent/prompts/observer.md`: "one time series per name, no labels").
The whole system is already a singleton — one live day at a time. That
simplifies this module: an activated project *becomes* the one live
day: no per-project metric isolation to build.

## Storage

```
data/projects/<slug>/
  project.json        # title, total_days, crew_size, created_at
  scenes.json          # Gemini breakdown output, cached (see quota below)
  cast.json             # character name, is_minor, previous_night_wrap
  day.json               # built ShootingDay
  provisioning.json  # cached planner decision (see Correction 2)
```

No database, per CLAUDE.md. JSON files, one directory per project,
slug derived from title.

## Backend

### `server/routes/projects.py`

Not `api/routes/` — this repo has no `api/` package; every backend
module lives under `server/`. Router included into `server/app.py`.

- `GET /api/projects` — list `project.json` summaries
- `POST /api/projects` — `{title, total_days, crew_size}` → creates
  the directory + `project.json`, returns the slug
- `GET /api/projects/{slug}` — full project state (whatever of
  scenes/cast/day exist yet)
- `POST /api/projects/{slug}/script` — multipart PDF upload →
  `breakdown_script`, writes `scenes.json`
- `POST /api/projects/{slug}/cast` — cast list → writes `cast.json`
- `POST /api/projects/{slug}/day` — `{day_number, date}` in the body
  (needed by `build_shooting_day`'s signature; nothing else supplies
  them) → `build_shooting_day(scenes, cast, day_number, date)`,
  writes `day.json`. The three-step UI never asks for these — it
  always sends `day_number=1`, `date=<today>`; the field exists on the
  route because the function needs it, not because the user chooses
  it in this version.
- `POST /api/projects/{slug}/activate` — loads it into the running
  console (see Server wiring below)

### `agent/tools/breakdown.py`

```python
def breakdown_script(pdf_bytes: bytes) -> list[Scene]
```

- `google-genai`, Gemini Developer API, `GEMINI_MODEL` from
  `agent.config` (already validated at import time — no new config
  surface).
- Sends the PDF as an inline `types.Part` document, not extracted
  text — the multimodal path is the point.
- Prompt: strict JSON matching `Scene` (`number`, `synopsis`,
  `int_ext`, `day_night`, `location`, `page_eighths` as `"2 3/8"`,
  `cast_names`, `estimated_setups`), with page-eighths explained
  inline (8 eighths = 1 page, the unit a 1st AD schedules in).
- Parses defensively: strips code fences, validates through the
  existing `PageEighths.from_string` + `Scene` pydantic model, raises
  an error naming exactly which field/scene failed — never a bare
  traceback.
- Caching: writes `scenes.json` immediately on success. The route
  checks for `scenes.json` first and never re-parses a script that
  already has one.

**Quota (Correction 3):** a `data/gemini_quota.json` local dev
counter (date + count vs. the 20/day free-tier cap) is a *convenience*
that warns before burning the day's quota locally — it does **not**
run on Cloud Run, where the filesystem is ephemeral and resets every
cold start, so it is not a real guard there. The actual defense is the
429 handler around the `breakdown_script` call: catches
`google.genai.errors.ClientError` with `code == 429`, returns a clear
user-facing error the route surfaces plainly, and — same discipline as
`agent/root.py`'s existing 429 handling — never lets that exception
reach and crash anything (in this case, the upload request handler,
which is not on the replay thread's call path, but the same "never
crash, surface plainly" bar applies).

### `agent/tools/scheduling.py`

```python
def build_shooting_day(scenes: list[Scene], cast: list[CastEntry], day_number: int, date: date) -> ShootingDay
```

Deterministic, no LLM (per CLAUDE.md's `Non-negotiable invariants`).
- `Setup.estimated_minutes` derived from each scene's
  `estimated_setups` (even split of a per-scene estimate; no per-setup
  detail exists from the breakdown).
- Call/wrap times assigned from a standard shoot-day template (general
  call, scheduled wrap, overtime threshold, golden hour, meal-due-by),
  same shape as `emitter/simulator.py`'s constants.
- `Performer.previous_night_wrap` and `is_minor` carried from the cast
  form; `minimum_turnaround_hours` defaulted from
  `gate/rules/production_rules.yaml` (`11.0`, or `12.0` for minors) —
  same source the gate itself checks against, so a provisioned day's
  displayed turnaround margin always agrees with what the gate would
  later approve or reject.

```python
def generate_scenario(day: ShootingDay) -> ScenarioResult
```

New — not in your original prompt, needed because nothing else
produces the performance data `replay_day` requires.

- Deterministic (not random): for each setup, `actual_minutes` =
  `estimated_minutes` with a fixed, reproducible jitter (no RNG seeded
  off wall-clock or anything non-reproducible), modest `takes`.
- Then inflates the setups belonging to the day's single longest scene
  (by `page_eighths`) — takes and `actual_minutes` climb — until
  `error_budget_consumed` crosses `AT_RISK_ERROR_BUDGET_CONSUMED`
  (0.75), so the full SLIP → REPLAN → GATE cycle fires on the user's
  own day, not just Day 14's canned demo.
- **Correction 1 — capped, not unbounded:** inflation stops at 3x each
  setup's own `estimated_minutes` or 15 takes, whichever comes first,
  per setup. If the cap is hit across every setup in the target scene
  and burn still hasn't crossed AT_RISK, generation stops there —
  it does not loop looking for a crossing that isn't reachable within
  the cap.
- Returns `ScenarioResult(scenario: dict[str, dict], at_risk_reachable: bool)`
  — `at_risk_reachable=False` on the capped-out path, so callers (and
  eventually the UI) can say the day is expected to play out close to
  plan rather than silently promising a slip that never comes.
- Not persisted to disk — regenerated fresh from `day.json` every
  replay start. It's a pure function of `day`, so this is
  reproducible, not a re-roll.
- Test: a "generously-slacked" fixture day (huge estimated_minutes
  headroom relative to its error budget) asserts `at_risk_reachable is
  False` and that generation still terminates and returns valid
  timings, proving the cap actually bounds the loop rather than just
  existing in a docstring.

## Server wiring (no spec for this originally — designed from reading `server/`)

`server/state.py` `AppState` gains:
- `active_project_slug: str | None = None`
- `active_total_days: int = TOTAL_SHOOT_DAYS` (threads a project's
  real `total_days` into `DaySnapshot.total_days`, which today is
  always the hardcoded 32; both `server/app.py`'s `_initial_snapshot`
  and `server/replay.py`'s `_base_snapshot` will pass this explicitly
  instead of relying on the pydantic default)

`POST /activate`:
1. Rejects with 409 if `STATE.status` is `running`/`at_risk` (same
   busy guard as `try_start` — don't activate out from under a live
   replay)
2. Loads `day.json`
3. Re-provisions Grafana. **Correction 2 — cache the planner
   decision, not just the Grafana write:** re-provisioning always
   re-runs the two Grafana MCP writes (dashboard + alert rule — no
   Gemini cost), but the `MonitoringPlan` decision (`burn_rate_threshold`,
   `evaluation_window_minutes`, `annotation`) only calls the planner
   LlmAgent if `data/projects/<slug>/provisioning.json` doesn't exist
   yet. First activate is a live Gemini call, cached immediately;
   every later activate of the same project reuses the cached plan
   and only repeats the (free) Grafana write. This needs a small split
   in `agent/subagents/planner.py`'s `provision()` — decide vs. write
   — so `provisioning.py`'s route can call `_decide_monitoring_plan`
   conditionally while always calling the two `provision_*` writes.
   The provisioning footer already distinguishes live vs. cached
   (`ProvisioningSnapshot.live`); a reused-plan activate reports
   `live=False` there the same way a 429 fallback does, so the UI
   doesn't need a new state, just an accurate existing one.
4. Sets `STATE.plan_day`, `STATE.active_project_slug`,
   `STATE.active_total_days`, resets `STATE.recovery = None`
5. Publishes a fresh idle `DaySnapshot` (`event_type="connected"`,
   `status="idle"`) over SSE so an already-open console tab updates
   without a reload

`server/replay.py`'s `run_replay`: when `STATE.active_project_slug` is
set, loads that project's `day.json` + a freshly-generated scenario
(`generate_scenario`) instead of `build_day(scenario_name)` /
`load_scenario(scenario_name)`. When no project is active, behavior is
byte-for-byte what it is today. The console never exposes a
nominal/slipping toggle (`api.ts`'s `startDay()` posts no scenario
param), so there's no UI state to reconcile here.

No changes to `emitter/schedule.py`, `gate/checker.py`,
`agent/subagents/replanner.py`, `agent/subagents/observer.py`, or any
console component (`web/src/components/*`) — every one of them only
ever sees a `ShootingDay`, exactly as before.

## Frontend

No new dependency. Hand-rolled routing: a small hook reads
`window.location.pathname`, a `navigate()` helper does
`history.pushState` + notifies listeners, links use an `onClick` that
prevent-defaults into it. `server/app.py` gains
`@app.get("/projects")` returning the built `index.html` (today only
`/` resolves through `StaticFiles(html=True)`'s directory-index
behavior; a direct load or refresh of `/projects` needs its own
fallback route or it 404s).

`/projects`: grid of project tiles + a "+ New production" tile. Same
paper-on-board language, Archivo Narrow, no new colors — reuses the
existing palette and type choices, no new design tokens.

New-production flow, three steps on one page (not a wizard, per your
spec):
1. Title, total shoot days, crew size
2. PDF drop zone → real progress state while Gemini parses (10–30s) →
   scene breakdown rendered as strips (`StripBoard`-style, reusing
   that component's strip-color logic) — the moment worth showing
3. Cast table: character name (prefilled from the breakdown's
   `cast_names`), is-minor toggle, previous night's wrap time,
   turnaround minimum defaulted from `production_rules.yaml` and
   editable

"Open shooting day" calls `/day` then `/activate`, then navigates to
`/`.

`Header.tsx` gains a small line — active production's title + a link
back to `/projects` — shown only when a project is active; the
default Day 14 view is visually unchanged.

## Testing

- `generate_scenario`: determinism (same `day` in → same scenario
  out), the AT_RISK-crossing behavior, and the capped/`at_risk_reachable
  =False` path on a generously-slacked fixture day (Correction 1)
- `build_shooting_day`: call/wrap math, turnaround defaults pulled
  correctly from `production_rules.yaml`
- `breakdown_script`: defensive parsing (fenced JSON, malformed
  scene, page-eighths edge cases) against fixture text — not a live
  Gemini call in the test suite
- Everything else: tests only where they earn their place, per the
  existing working agreement

## Verification (manual, end of implementation)

Create a production, upload a real screenplay PDF generated for this
purpose (invented — no real film/studio/person, per CLAUDE.md), confirm
scenes come back with sane page eighths, enter cast, build the day,
activate it, and watch the console replay that day rather than Day 14
— including confirming the SLIP → REPLAN → GATE cycle actually fires
once `error_budget_consumed` crosses 0.75.
