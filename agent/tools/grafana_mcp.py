"""Grafana MCP connection for the MARTINI agent -- read + write (Modules 3-4).

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

The server used to be started with ``--disable-write``, which is its own
read-only mode -- write and delete operations were refused by the server
itself, not just left off the ``tool_filter`` below. That flag is gone:
Module 4 (provisioning) needs the server's write tools reachable. The
``tool_filter`` on each toolset is what actually scopes what a given
caller can do; it was never the safety boundary and still isn't one.

This module imports ``McpToolset`` -- the current, maintained name for
what MARTINI's spec calls ``MCPToolset`` in ``google.adk.tools.mcp_tool``.
The ``MCPToolset`` name still exists in the installed ADK version but is
a deprecated alias that only warns and delegates to ``McpToolset``; the
maintained class is used here under that historical name to avoid
spraying deprecation warnings on every run.

Tool names below were read from the live server's own ``tools/list``
response (grafana/mcp-grafana v1.3.0), not guessed from its README's
prose feature list.
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
"""Read-only subset used by the observer subagent (Module 3)."""

WRITE_TOOLS = [
    "update_dashboard",
    "alerting_manage_rules",
    "create_annotation",
    "create_incident",
    "add_activity_to_incident",
    "create_folder",
    "search_folders",
    "list_datasources",
]
"""Dashboard/alerting/incident write tools used by provisioning (Module 4).

``update_dashboard`` is mcp-grafana's single create-or-update tool for
dashboards -- there is no separate ``create_dashboard``. Provisioning
(agent/tools/provisioning.py) talks to these tools over its own raw MCP
session rather than through this ADK toolset, since it has no LlmAgent
turn in which to supply the ToolContext an McpTool.run_async requires;
``grafana_server_params()`` below is the shared connection config both
paths build on. This toolset is kept here regardless -- for symmetry
with the read path, and for any future LlmAgent (e.g. a later replanner)
that needs to call these tools itself under model control.
"""


def grafana_server_params() -> StdioServerParameters:
    """The stdio launch config shared by every path that talks to mcp-grafana.

    Returns the plain ``mcp`` SDK params object, which is what both
    ADK's ``StdioConnectionParams`` (used by the toolsets below) and a
    raw ``mcp.client.stdio.stdio_client`` session (used by
    agent/tools/provisioning.py) accept.
    """
    return StdioServerParameters(
        command="uvx",
        args=["mcp-grafana"],
        env={
            "GRAFANA_URL": config.GRAFANA_URL,
            "GRAFANA_SERVICE_ACCOUNT_TOKEN": config.GRAFANA_SERVICE_ACCOUNT_TOKEN,
        },
    )


def build_grafana_toolset() -> MCPToolset:
    """Builds the read-only Grafana MCPToolset used by the observer subagent."""
    return MCPToolset(
        connection_params=StdioConnectionParams(
            server_params=grafana_server_params(),
            timeout=10.0,
        ),
        tool_filter=READ_TOOLS,
    )


def build_grafana_write_toolset() -> MCPToolset:
    """Builds the write-capable Grafana MCPToolset, scoped to WRITE_TOOLS."""
    return MCPToolset(
        connection_params=StdioConnectionParams(
            server_params=grafana_server_params(),
            timeout=10.0,
        ),
        tool_filter=WRITE_TOOLS,
    )
