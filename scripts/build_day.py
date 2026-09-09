"""CLI: run Day 14's invented screenplay through Gemini's multimodal
breakdown and commit the result as data/day_14.json (Module 1b).

    python scripts/build_day.py

A build-time step, not a runtime one: emitter/simulator.py loads the
committed data/day_14.json, it never calls Gemini itself. Re-run this
whenever data/day_14_screenplay.pdf changes.

Gemini's own page_eighths estimate swings wildly between runs on this
same document (34, then 42, then 364 total page-eighths across three
otherwise-unremarkable calls) -- not usable as a stable scheduling
input. A real 1st AD's page-eighths estimate is itself a planning
judgment call, not a mechanical fact the screenplay hands you, so this
script keeps that judgment call hand-set (PLANNED_PAGE_EIGHTHS below,
the same figures this demo has always used, chosen so the slipping
scenario's error budget genuinely crosses AT_RISK by Scene 42) and
takes everything else Gemini reports -- synopsis, INT/EXT, day/night,
location, cast -- as-is.
"""

from __future__ import annotations

import json
from pathlib import Path

from agent.tools.breakdown import breakdown_script
from emitter.models import PageEighths

_SCREENPLAY_PATH = Path(__file__).parent.parent / "data" / "day_14_screenplay.pdf"
_OUTPUT_PATH = Path(__file__).parent.parent / "data" / "day_14.json"

PLANNED_PAGE_EIGHTHS = {
    "1": 4, "2": 4, "3": 4, "4": 4,
    "5": 2, "5B": 1, "5C": 1,
    "42": 4, "42B": 4, "42C": 2, "42D": 5,
    "43": 17,
}


def main() -> None:
    pdf_bytes = _SCREENPLAY_PATH.read_bytes()
    scenes = breakdown_script(pdf_bytes)

    missing = [scene.number for scene in scenes if scene.number not in PLANNED_PAGE_EIGHTHS]
    if missing:
        raise SystemExit(
            f"breakdown returned scene(s) with no planned page count: {missing} -- "
            "add them to PLANNED_PAGE_EIGHTHS or fix the screenplay's scene numbers."
        )

    planned_scenes = [
        scene.model_copy(update={"page_eighths": PageEighths(eighths=PLANNED_PAGE_EIGHTHS[scene.number])})
        for scene in scenes
    ]

    payload = [scene.model_dump(mode="json") for scene in planned_scenes]
    _OUTPUT_PATH.write_text(json.dumps(payload, indent=2) + "\n")

    total_eighths = sum(scene.page_eighths.eighths for scene in planned_scenes)
    print(f"wrote {_OUTPUT_PATH} -- {len(planned_scenes)} scenes, {total_eighths} page-eighths")
    for scene in planned_scenes:
        print(f"  {scene.number:>4}  {scene.int_ext}-{scene.day_night}  {scene.page_eighths.eighths}/8  {scene.synopsis}")


if __name__ == "__main__":
    main()
