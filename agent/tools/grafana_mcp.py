"""Grafana MCP connection for the MARTINI agent -- read path (Module 3).

Connects to the official ``grafana/mcp-grafana`` server over stdio via
``uvx``, exactly as its own Quick Start documents, pointed at the
user's Grafana Cloud stack through GRAFANA_URL and
GRAFANA_SERVICE_ACCOUNT_TOKEN. Grafana Cloud does not publish a stable,
generally reachable hosted MCP endpoint URL for an arbitrary stack, so
this repo cannot target one without guessing a host -- the documented
stdio path is used instead. If a hosted endpoint becomes available for
this stack, swap the ``connection_params`` below for
``StreamableHTTPConnectionParams`` pointed at that URL; nothing else in
this module needs to change.

The server is started with ``--disable-write``, which is its own
read-only mode (see its README) -- write and delete operations are
refused by the server itself, not just left off the ``tool_filter``
below. That filter exists for a second, narrower reason: it's just
prompt hygiene, keeping the ~60-tool surface out of the model's
context so tool selection stays sharp. Module 4 (provisioning) will
need a *separate* toolset built without ``--disable-write``.

This module imports ``McpToolset`` -- the current, maintained name for
what MARTINI's spec calls ``MCPToolset`` in ``google.adk.tools.mcp_tool``.
The ``MCPToolset`` name still exists in the installed ADK version but is
a deprecated alias that only warns and delegates to ``McpToolset``; the
maintained class is used here under that historical name to avoid
spraying deprecation warnings on every run.
"""

from __future__ import annotations

from google.adk.tools.mcp_tool import McpToolset as MCPToolset
from google.adk.tools.mcp_tool import StdioConnectionParams
from mcp import StdioServerParameters

from agent import config

READ_TOOLS = [
    "query_prometheus",
    "query_loki_logs",
    "search_dashboards",
    "alerting_manage_rules",
]
"""Tool names as registered by grafana/mcp-grafana's Go source (tools/*.go),
not guessed from the README's prose feature list."""


def build_grafana_toolset() -> MCPToolset:
    """Builds the read-only Grafana MCPToolset used by the observer subagent."""
    return MCPToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command="uvx",
                args=["mcp-grafana", "--disable-write"],
                env={
                    "GRAFANA_URL": config.GRAFANA_URL,
                    "GRAFANA_SERVICE_ACCOUNT_TOKEN": config.GRAFANA_SERVICE_ACCOUNT_TOKEN,
                },
            ),
            timeout=10.0,
        ),
        tool_filter=READ_TOOLS,
    )
