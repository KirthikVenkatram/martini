"""CLI: provision Grafana (via MCP) for a shooting day -- dashboard + burn-rate alert.

    python scripts/provision.py --scenario nominal
"""

from __future__ import annotations

import argparse
import asyncio

from agent.subagents.planner import provision
from emitter.simulator import build_day


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=["slipping", "nominal"], default="nominal")
    args = parser.parse_args()

    day = build_day(args.scenario)
    result = asyncio.run(provision(day))

    print(f"day {day.day_number} -- provisioned at {result.provisioned_at:%H:%M:%S}Z")
    print(f"  dashboard uid   : {result.dashboard_uid}")
    print(f"  dashboard url   : {result.dashboard_url}")
    print(f"  alert rule uid  : {result.alert_rule_uid}")


if __name__ == "__main__":
    main()
