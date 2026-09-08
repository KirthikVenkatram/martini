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
from server import derived, narration  # noqa: E402
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
        pages_remaining_eighths=day.total_page_eighths.eighths,
        total_page_eighths=day.total_page_eighths.eighths,
        setups_total=day.total_setups,
        timeline=derived.timeline_snapshot(day, day.general_call),
        pace=derived.pace_snapshot(day, day.general_call),
        cast_clocks=derived.cast_clock_snapshots(day, day.general_call),
        **narration.idle_narration(day),
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


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})


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
