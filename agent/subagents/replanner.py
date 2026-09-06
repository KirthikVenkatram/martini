"""The replanner subagent -- MARTINI's recovery proposals (Module 5).

An ADK LlmAgent that, once the day is at risk, proposes recovery
options grounded in scene content -- not just duration -- from the
day's own plan (agent/subagents/observer.py's read of Grafana, plus
the static scene/cast structure on ShootingDay). It never decides
whether an option is legal: gate/checker.py's deterministic check()
does that afterward. The replanner proposes; the gate disposes.
"""

from __future__ import annotations

import json
from pathlib import Path

from google.adk.agents import LlmAgent
from google.adk.runners import InMemoryRunner
from google.genai import types
from pydantic import BaseModel, ValidationError

from agent.config import GEMINI_MODEL
from agent.subagents.observer import DayObservation
from emitter.models import Scene, ShootingDay
from gate.checker import RecoveryOption

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "replanner.md"

_EXPECTED_OPTION_COUNT = 2


def _build_replanner_agent() -> LlmAgent:
    return LlmAgent(
        name="replanner",
        model=GEMINI_MODEL,
        instruction=_PROMPT_PATH.read_text(),
        description="Proposes schedule recovery options grounded in scene content.",
    )


class _RecoveryOptionsResponse(BaseModel):
    options: list[RecoveryOption]


def parse_recovery_options(raw_text: str) -> list[RecoveryOption]:
    """Parses the replanner's raw model output into its RecoveryOptions.

    Raised errors name what was wrong (invalid JSON, a schema mismatch,
    or the wrong option count) so a malformed model reply is
    diagnosable, not a bare traceback.
    """
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"replanner did not return valid JSON: {raw_text!r}") from exc

    try:
        response = _RecoveryOptionsResponse.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"replanner output does not match expected schema: {exc}") from exc

    if len(response.options) != _EXPECTED_OPTION_COUNT:
        raise ValueError(
            f"replanner must propose exactly {_EXPECTED_OPTION_COUNT} options, got {len(response.options)}"
        )

    return response.options


def _scene_shooting_order(day: ShootingDay) -> list[Scene]:
    """day.scenes ordered the way they're actually shot, per day.setups.

    Scenes with no setup yet (nothing has been scheduled to them) fall
    back to the end, in their ShootingDay.scenes order.
    """
    seen_numbers: list[str] = []
    for setup in day.setups:
        if setup.scene_number not in seen_numbers:
            seen_numbers.append(setup.scene_number)

    scenes_by_number = {scene.number: scene for scene in day.scenes}
    ordered = [scenes_by_number[number] for number in seen_numbers if number in scenes_by_number]
    remaining = [scene for scene in day.scenes if scene.number not in seen_numbers]
    return ordered + remaining


def _shot_and_remaining_scenes(day: ShootingDay, observation: DayObservation) -> tuple[list[Scene], list[Scene]]:
    """Splits day.scenes into shot/remaining using observation's page count.

    day itself is the static plan (script breakdown, cast, page
    counts) -- it never reflects live progress, since the replanner
    perceives that only through Grafana, same as the observer. This
    walks the plan in shooting order and calls a scene "shot" once the
    cumulative page count reaches what the observation says is done.
    A scene whose pages straddle that boundary counts as shot -- this
    is prompt grounding, not the gate's maths.
    """
    ordered = _scene_shooting_order(day)
    shot: list[Scene] = []
    remaining: list[Scene] = []
    cumulative = 0
    for scene in ordered:
        (shot if cumulative < observation.pages_completed_eighths else remaining).append(scene)
        cumulative += scene.page_eighths.eighths
    return shot, remaining


def _cast_line(day: ShootingDay, scene: Scene) -> str:
    performers_by_id = {performer.id: performer for performer in day.performers}
    names = [performers_by_id[cast_id].character_name if cast_id in performers_by_id else cast_id for cast_id in scene.cast_ids]
    return ", ".join(names) if names else "none listed"


def _build_prompt_message(day: ShootingDay, observation: DayObservation) -> str:
    shot, remaining = _shot_and_remaining_scenes(day, observation)

    lines = [
        f"Day {day.day_number} -- {day.production_title}",
        f"Shoot date: {day.shoot_date.isoformat()}",
        f"Error budget consumed: {observation.error_budget_consumed:.0%}",
        f"Burn rate: {observation.burn_rate:.2f}x sustainable pace",
        f"Pages: {observation.pages_completed_eighths}/"
        f"{observation.pages_completed_eighths + observation.pages_remaining_eighths} eighths shot",
        f"Setups: {observation.setups_completed}/{observation.setups_total}",
        f"Projected wrap offset: {observation.projected_wrap_offset_minutes:+.0f} minutes",
        f"Minutes to golden hour: {observation.minutes_to_golden_hour}",
        "",
        "Cast on this day:",
    ]

    if day.performers:
        for performer in day.performers:
            tag = " (minor)" if performer.is_minor else ""
            lines.append(
                f"- {performer.character_name}{tag}, id={performer.id}, call {performer.call_time.isoformat()}"
            )
    else:
        lines.append("- none provided")

    lines.append("")
    lines.append("Scenes already shot:")
    for scene in shot:
        lines.append(f"- Sc.{scene.number} ({scene.page_eighths} pages): {scene.synopsis}. Cast: {_cast_line(day, scene)}.")

    lines.append("")
    lines.append("Scenes remaining, in shooting order:")
    for scene in remaining:
        lines.append(f"- Sc.{scene.number} ({scene.page_eighths} pages): {scene.synopsis}. Cast: {_cast_line(day, scene)}.")

    lines.append("")
    lines.append("Propose exactly two recovery options.")
    return "\n".join(lines)


async def replan(day: ShootingDay, observation: DayObservation) -> list[RecoveryOption]:
    """Asks the replanner agent for exactly two recovery options."""
    agent = _build_replanner_agent()
    runner = InMemoryRunner(agent=agent, app_name="martini-replanner")
    session = await runner.session_service.create_session(
        app_name="martini-replanner", user_id="martini"
    )
    message = types.Content(role="user", parts=[types.Part(text=_build_prompt_message(day, observation))])

    raw_text: str | None = None
    async for event in runner.run_async(
        user_id="martini", session_id=session.id, new_message=message
    ):
        if event.is_final_response() and event.content and event.content.parts:
            raw_text = event.content.parts[0].text

    if raw_text is None:
        raise RuntimeError("replanner agent produced no final response")

    return parse_recovery_options(raw_text)
