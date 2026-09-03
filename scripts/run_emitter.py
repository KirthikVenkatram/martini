"""CLI: replay a MARTINI shooting day as OTel metrics/logs.

    python scripts/run_emitter.py --scenario slipping --speed 480
    python scripts/run_emitter.py --scenario nominal --dry-run
"""

from __future__ import annotations

import argparse

from dotenv import load_dotenv

from emitter.simulator import build_day, load_scenario, replay_day


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=["slipping", "nominal"], required=True)
    parser.add_argument("--speed", type=float, default=480.0, help="wall-clock compression factor")
    parser.add_argument(
        "--dry-run", action="store_true", help="print metrics/logs to stdout instead of exporting"
    )
    args = parser.parse_args()

    day = build_day(args.scenario)
    scenario = load_scenario(args.scenario)

    def on_event(event: dict) -> None:
        scene = event.get("scene", "-")
        setup = event.get("setup", "-")
        print(
            f"[{event['now']:%H:%M}] {event['type']:<14} scene={scene} setup={setup} "
            f"pages={event['pages_completed_eighths']}/{event['pages_completed_eighths'] + event['pages_remaining_eighths']} "
            f"setups={event['setups_completed']}/{event['setups_total']}"
        )

    replay_day(day, scenario, speed_factor=args.speed, on_event=on_event, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
