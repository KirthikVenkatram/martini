"""CLI: run the full replan-and-gate recovery cycle for a shooting day.

    python scripts/recover.py --scenario slipping
"""

from __future__ import annotations

import argparse
import asyncio

from agent.root import run_recovery_cycle
from emitter.simulator import build_day
from gate.explain import explain


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=["slipping", "nominal"], default="slipping")
    args = parser.parse_args()

    day = build_day(args.scenario)
    result = asyncio.run(run_recovery_cycle(day))

    observation = result.observation
    print(f"day {day.day_number} -- observed at {observation.observed_at:%H:%M:%S}")
    print(f"  error budget consumed : {observation.error_budget_consumed:.1%}")
    print(f"  burn rate             : {observation.burn_rate:.2f}")
    print()

    verdicts_by_id = {verdict.option_id: verdict for verdict in result.verdicts}
    rejected = [option for option in result.options if not verdicts_by_id[option.id].approved]
    approved = [option for option in result.options if verdicts_by_id[option.id].approved]

    for option in rejected + approved:
        verdict = verdicts_by_id[option.id]
        status = "REJECTED" if not verdict.approved else "APPROVED"
        print(f"[{status}] {option.id} -- {option.kind}")
        print(f"  {option.description}")
        for violation in verdict.violations:
            print(f"  reason: {explain(violation)}")
        print()

    if result.incident_id:
        print(f"incident opened: {result.incident_id}")
    else:
        print("no incident opened (day not at risk, or no option was legal)")


if __name__ == "__main__":
    main()
