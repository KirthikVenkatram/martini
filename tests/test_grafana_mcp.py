from __future__ import annotations

from agent.tools.grafana_mcp import READ_TOOLS


def test_read_tools_can_discover_the_prometheus_datasource_uid():
    """The observer must be able to look up a real datasource UID.

    query_prometheus requires a datasourceUid, and Grafana Cloud names
    it per-stack -- without list_datasources in its toolset, the
    observer has no legal way to learn it and can only guess.
    """
    assert "list_datasources" in READ_TOOLS
