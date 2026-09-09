# MARTINI

An AI agent that treats a film shooting day as a production system it is on call for.

MARTINI reads a screenplay, breaks it down into scenes, builds the shooting day,
provisions its own SLO dashboard and alert rules in Grafana, watches the day burn
its error budget, and — when the day starts slipping — proposes schedule recovery
plans grounded in what is actually in the scenes. Every recovery option is passed
through a deterministic gate that checks turnaround, meal, minor, and crew-rest
rules before it can ever reach a human.

The name: a "martini shot" is the last shot of the shooting day.

All production names, screenplays, and cast in this repo — including the "Day 14"
demo — are invented for this project. No real film, studio, or person appears
anywhere in the data, tests, or code.

## The five beats

1. **PROVISION** — the agent creates a dashboard and alert rules in Grafana via
   the official Grafana MCP server, generated from the day's plan.
2. **RUN** — the emitter replays the shooting day as OpenTelemetry metrics; the
   console streams it live over SSE.
3. **SLIP** — a scene runs long, the error budget burn crosses threshold, the
   agent's own alert fires.
4. **REPLAN** — the agent queries Grafana for current state; Gemini proposes
   recovery options grounded in scene content from the script breakdown.
5. **GATE** — a deterministic Python checker rejects any illegal option with a
   plain-language reason, approves the legal one, and the agent opens a Grafana
   incident.

Beat 1 (the agent *writes* to Grafana) and beat 5 (a visible rejection with a
reason, never a silent LLM judgment call) are the two things this project is
built to prove.

## How it fits together

```
screenplay (PDF)
      │  Gemini multimodal breakdown
      ▼
  scenes + cast  ──────────────►  gate/rules/production_rules.yaml (data)
      │                                    ▲
      ▼                                    │ deterministic check
  ShootingDay  ──► emitter/  ──OTel──►  Grafana Cloud  ◄──MCP──►  agent/
  (schedule math)   (replay)                                  (observe · plan ·
                                                                 replan · provision)
                                                                        │
                                                                        ▼
                                                              server/ (FastAPI + SSE)
                                                                        │
                                                                        ▼
                                                              web/ (React console)
```

- **`emitter/`** — the domain model and schedule math (`models.py`, `schedule.py`
  — turnaround, meal breaks, burn rate, error budget), the OTel metric/log
  pipeline (`otel.py`), and the replay engine (`simulator.py`) that walks a
  shooting day against canned per-setup timing data (`scenarios/*.yaml`) at
  compressed wall-clock speed. The built-in "Day 14" fixture is an invented
  quarry-town drama — `data/day_14_screenplay.pdf`, five invented cast members,
  no real film, studio, or person — run through Gemini's multimodal breakdown
  at build time (`scripts/build_day.py`) and committed as `data/day_14.json`,
  which `simulator.py::build_day()` loads. Per-scene page-eighths stay a
  hand-set planning number in `build_day.py` rather than Gemini's own estimate
  (which swings wildly run to run) — everything else about a scene (synopsis,
  INT/EXT, cast) comes straight from the breakdown.
- **`gate/`** — the deterministic legality checker. `checker.py::check()` never
  makes a network call (a test asserts this directly) and never lets an LLM
  decide whether a plan is legal. Rules live as data in
  `gate/rules/production_rules.yaml`: turnaround minimums (11h general / 12h
  minors), meal-break spacing, minor working-hour and wrap-time limits, and
  crew rest between days. Each rule's YAML `description` is a template that
  becomes a real sentence at check time, e.g. *"Places PRIYA 40m inside the
  required turnaround — PRIYA needs 11h between wrap and next call..."* — the
  demo's built-in turnaround violation is a real, computed rejection, not a
  scripted one.
- **`agent/`** — built on `google-adk` with native `MCPToolset`, talking to the
  official `grafana/mcp-grafana` binary over stdio (never a REST wrapper we
  wrote). Three `LlmAgent` subagents: an **observer** that perceives the day
  only through Grafana (no direct schedule access), a **planner** that decides
  and provisions the monitoring plan, and a **replanner** that proposes exactly
  two recovery options grounded in scene content plus the observer's live
  numbers. `agent/root.py::run_recovery_cycle` wires observe → replan → gate
  each option → open a Grafana incident if the day is at risk. Gemini is
  called only when an alert fires, never per emitter tick.
- **`server/`** — a FastAPI app. `GET /api/day/stream` is the SSE feed the
  console renders; `POST /api/day/start` kicks off a replay (`nominal` or
  `slipping`); `/api/projects/*` (Module 7) lets a user upload their own
  screenplay, build a day from it, and activate it as the live console day —
  the console itself stays a singleton showing one running day at a time.
- **`web/`** — a Vite + React 19 + TypeScript + Tailwind v4 console with no
  state library and no component library. `web/dist` is committed because the
  deploy host has no Node. The hero of the page is the error budget bar and a
  plain-English verdict headline, not a chart; the only element that ever gets
  the burn color is a rejected recovery card, and its reason is rendered as a
  sentence, never a code or a badge. The strip-board palette and Archivo
  Narrow / Inter type come straight from real film scheduling paperwork.

## Setup

Requires Python 3.11+, [uv](https://docs.astral.sh/uv/), and Node (for the
frontend build only — the running server serves the committed `web/dist`).

```bash
uv pip install -e .[dev]
cp .env.example .env   # fill in Grafana + Gemini credentials
```

Environment variables (see `.env.example`):

| Variable | Purpose |
|---|---|
| `GOOGLE_GENAI_USE_VERTEXAI` | `TRUE` for Vertex AI, `FALSE` for the AI Studio developer API |
| `GOOGLE_API_KEY` | Gemini key when using the developer API |
| `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION` | Vertex AI project/region |
| `GEMINI_MODEL` | Gemini model id |
| `GRAFANA_URL`, `GRAFANA_SERVICE_ACCOUNT_TOKEN` | Grafana Cloud stack + service account token |
| `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_EXPORTER_OTLP_HEADERS`, `OTEL_EXPORTER_OTLP_PROTOCOL` | OTLP export to Grafana Cloud |

## Running it

```bash
uvicorn server.app:app --reload
```

Opens the productions grid at `/`, with the Day 14 sample production (always
available, unmodified) at `/day/14`. Start a replay from the console, or from
the CLI:

```bash
python scripts/build_day.py                                     # rebuild data/day_14.json from the screenplay
python scripts/run_emitter.py --scenario slipping --speed 480   # replay only
python scripts/observe.py --day 14                              # query Grafana state
python scripts/provision.py --scenario nominal                  # provision dashboard + alerts
python scripts/recover.py --scenario slipping                   # run one full recovery cycle
```

To rebuild the frontend after touching `web/src`:

```bash
cd web && npm ci && npm run build
```

## Testing

```bash
pytest
```

`tests/test_gate.py` is the suite that matters most here — it asserts every
rule path against a real computed shortfall (not a fixture value) and includes
a test that patches `socket` to prove the gate never touches the network.

## Deployment

`Dockerfile` is a multi-stage, host-agnostic build (Node stage builds `web/`,
Python 3.11-slim stage runs `uvicorn`) — the same image runs on Render or
Cloud Run via the `${PORT}` convention.

`infra/deploy_cloudrun.sh` deploys to Cloud Run: it syncs the two secret env
vars into GCP Secret Manager, grants the runtime service account the IAM roles
it needs (Vertex AI, Artifact Registry, Secret Manager access), then
`gcloud run deploy`s from source with `--min-instances=1` so the service stays
warm. Everything non-secret goes in via `--set-env-vars`; secrets are wired in
with `--set-secrets` and never touch the command line.

## License

Apache-2.0 — see [LICENSE](LICENSE).
