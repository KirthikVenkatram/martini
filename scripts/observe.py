"""CLI: query Grafana (via MCP) for a shooting day's current state.

    python scripts/observe.py --day 14
"""

from __future__ import annotations

import argparse
import asyncio

from agent.subagents.observer import observe


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--day", type=int, default=14, dest="day_number")
    args = parser.parse_args()

    observation = asyncio.run(observe(args.day_number))

    print(f"day {args.day_number} -- observed at {observation.observed_at:%H:%M:%S}")
    print(f"  error budget consumed : {observation.error_budget_consumed:.1%}")
    print(f"  burn rate             : {observation.burn_rate:.2f}")
    print(
        "  pages (eighths)       : "
        f"{observation.pages_completed_eighths} done, "
        f"{observation.pages_remaining_eighths} remaining"
    )
    print(
        "  setups                : "
        f"{observation.setups_completed}/{observation.setups_total}"
    )
    print(f"  projected wrap offset : {observation.projected_wrap_offset_minutes:+.0f} min")
    if observation.firing_alerts:
        print(f"  firing alerts         : {', '.join(observation.firing_alerts)}")
    else:
        print("  firing alerts         : none")


if __name__ == "__main__":
    main()
