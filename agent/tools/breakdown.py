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
