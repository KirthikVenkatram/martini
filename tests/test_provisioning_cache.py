from __future__ import annotations

from datetime import datetime, timezone

from agent.subagents.planner import ProvisioningResult
from server import provisioning_cache


def _result() -> ProvisioningResult:
    return ProvisioningResult(
        dashboard_uid="martini-day-14",
        dashboard_url="https://example.grafana.net/d/martini-day-14",
        alert_rule_uid="abc123",
        alert_rule_url="https://example.grafana.net/alerting/grafana/abc123/view",
        burn_rate_threshold=1.35,
        evaluation_window_minutes=10,
        annotation="Losing time against Scene 42.",
        provisioned_at=datetime.now(timezone.utc),
    )


def test_round_trips_through_disk(tmp_path, monkeypatch):
    monkeypatch.setattr(provisioning_cache, "CACHE_PATH", tmp_path / "cached_provisioning.json")

    provisioning_cache.save_cached_provisioning(_result())
    loaded = provisioning_cache.load_cached_provisioning()

    assert loaded is not None
    assert loaded.dashboard_uid == "martini-day-14"
    assert loaded.burn_rate_threshold == 1.35


def test_returns_none_when_no_cache_exists(tmp_path, monkeypatch):
    monkeypatch.setattr(provisioning_cache, "CACHE_PATH", tmp_path / "missing.json")

    assert provisioning_cache.load_cached_provisioning() is None
