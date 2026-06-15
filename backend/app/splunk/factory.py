"""Selects the Splunk client implementation from settings.

Three transports satisfy the same :class:`SplunkClient` protocol:

- ``mock`` — deterministic, offline, used in tests and ``make demo-offline``.
- ``live`` — Splunk Enterprise/Cloud REST search API (token auth).
- ``mcp``  — Splunk MCP Server over JSON-RPC (agent-to-Splunk via MCP).

Selection is a single env var, ``SENTINEL_SPLUNK_BACKEND``.
"""
from __future__ import annotations

from app.core.config import Settings, get_settings
from app.splunk.client import SplunkClient
from app.splunk.live_client import LiveSplunkClient
from app.splunk.mcp_client import McpSplunkClient
from app.splunk.mock_client import MockSplunkClient


def build_splunk_client(settings: Settings | None = None) -> SplunkClient:
    settings = settings or get_settings()
    if settings.splunk_backend == "live":
        return LiveSplunkClient(host=settings.splunk_host, token=settings.splunk_token)
    if settings.splunk_backend == "mcp":
        return McpSplunkClient(
            url=settings.splunk_mcp_url,
            token=settings.splunk_token,
            search_tool=settings.splunk_mcp_search_tool,
        )
    return MockSplunkClient()
