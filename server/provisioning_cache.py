"""Disk cache for the boot-time Grafana provisioning result (Module 6).

Written once, on a successful live provision. Read back only when a
live provision attempt fails at startup (quota, network, cold start on
the host) so the console can still show a real dashboard/alert link
and keep running, instead of returning 503 and hiding the provisioning
log.
"""

from __future__ import annotations

from pathlib import Path

from agent.subagents.planner import ProvisioningResult

CACHE_PATH = Path(__file__).parent.parent / "data" / "cached_provisioning.json"


def save_cached_provisioning(result: ProvisioningResult) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(result.model_dump_json(indent=2))


def load_cached_provisioning() -> ProvisioningResult | None:
    if not CACHE_PATH.exists():
        return None
    return ProvisioningResult.model_validate_json(CACHE_PATH.read_text())
