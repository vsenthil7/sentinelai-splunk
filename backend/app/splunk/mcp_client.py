"""Splunk MCP Server client.

This backend connects SentinelAI's agents to Splunk through the **Splunk MCP
Server** (Model Context Protocol) rather than the raw REST API. Per the
hackathon note, OAuth for the MCP Server is in Controlled Availability, so we
use **token-based authentication** to get started today.

Why a dedicated backend (vs. ``LiveSplunkClient``):
- The MCP Server is the sanctioned way to let AI agents call Splunk *tools*
  (``run_oneshot_search``, ``run_search`` etc.) over a single audited channel,
  which is exactly the "Best Use of Splunk MCP Server" pattern: an agent
  orchestrating Splunk actions through MCP instead of hand-rolled REST.
- It satisfies the same :class:`SplunkClient` protocol, so the detection agent,
  orchestrator, and every test are transport-agnostic — selecting MCP is one
  env var (``SENTINEL_SPLUNK_BACKEND=mcp``).

Transport: MCP over HTTP using JSON-RPC 2.0 ``tools/call`` requests. The single
network method ``_call_tool`` is isolated so it can be contract-tested with a
stubbed httpx transport, identical to the live REST client's design.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import httpx

from app.models.domain import SearchResult, SplunkEvent
from app.splunk.client import (
    SplunkAuthError,
    SplunkClient,
    SplunkConnectionError,
    SplunkQueryError,
)

# Default Splunk MCP Server search tool name. Configurable for forward-compat
# with tool-name changes across MCP TA versions.
_DEFAULT_SEARCH_TOOL = "run_oneshot_search"


class McpSplunkClient(SplunkClient):
    """Talks to Splunk via the MCP Server's JSON-RPC ``tools/call`` endpoint."""

    def __init__(
        self,
        url: str,
        token: str,
        *,
        search_tool: str = _DEFAULT_SEARCH_TOOL,
        verify: bool = False,
        timeout: float = 60.0,
    ) -> None:
        if not url:
            raise SplunkConnectionError("Splunk MCP Server URL not configured")
        if not token:
            raise SplunkAuthError("Splunk MCP token not configured")
        self._url = url.rstrip("/")
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        self._search_tool = search_tool
        self._verify = verify
        self._timeout = timeout
        self._rpc_id = 0

    def _next_id(self) -> int:
        self._rpc_id += 1
        return self._rpc_id

    async def _call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Issue a single MCP ``tools/call`` JSON-RPC request.

        Isolated for contract testing with a stubbed transport. Maps MCP/HTTP
        failure modes onto the SplunkError taxonomy the rest of the app knows.
        """
        request = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
        async with httpx.AsyncClient(verify=self._verify, timeout=self._timeout) as client:
            try:
                resp = await client.post(self._url, headers=self._headers, json=request)
            except httpx.ConnectError as exc:  # pragma: no cover - network path
                raise SplunkConnectionError(str(exc)) from exc
            if resp.status_code == 401:
                raise SplunkAuthError("Splunk MCP Server rejected the token")
            if resp.status_code == 400:
                raise SplunkQueryError(resp.text)
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
        if "error" in data and data["error"]:
            # JSON-RPC level error (bad tool, bad SPL, server fault).
            message = str(data["error"].get("message", data["error"]))
            raise SplunkQueryError(message)
        result: dict[str, Any] = data.get("result", {})
        return result

    @staticmethod
    def _extract_rows(result: dict[str, Any]) -> list[dict[str, Any]]:
        """Pull event rows out of an MCP tool result.

        MCP tool results carry a ``content`` list of typed blocks; search tools
        return their rows as a JSON text block. We parse the first text block
        that decodes to a list (the result set), tolerating servers that also
        attach structured ``structuredContent``.
        """
        structured = result.get("structuredContent")
        if isinstance(structured, dict) and isinstance(structured.get("results"), list):
            return [r for r in structured["results"] if isinstance(r, dict)]
        for block in result.get("content", []):
            if not isinstance(block, dict) or block.get("type") != "text":
                continue
            text = block.get("text", "")
            try:
                parsed = json.loads(text)
            except (json.JSONDecodeError, TypeError):
                continue
            if isinstance(parsed, list):
                return [r for r in parsed if isinstance(r, dict)]
            if isinstance(parsed, dict) and isinstance(parsed.get("results"), list):
                return [r for r in parsed["results"] if isinstance(r, dict)]
        return []

    async def search(
        self, spl: str, earliest: str = "-24h", latest: str = "now"
    ) -> SearchResult:
        if not spl or not spl.strip():
            raise SplunkQueryError("Empty SPL query")
        arguments = {
            "query": spl if spl.strip().lower().startswith("search") else f"search {spl}",
            "earliest_time": earliest,
            "latest_time": latest,
        }
        result = await self._call_tool(self._search_tool, arguments)
        rows = self._extract_rows(result)
        events = [
            SplunkEvent(
                raw=str(row.get("_raw", "")),
                source=str(row.get("source", "")),
                sourcetype=str(row.get("sourcetype", "")),
                host=str(row.get("host", "")),
                timestamp=_parse_time(row.get("_time")),
                fields={k: str(v) for k, v in row.items() if not k.startswith("_")},
            )
            for row in rows
        ]
        return SearchResult(
            sid=str(result.get("sid", "mcp")),
            query=spl,
            event_count=len(events),
            events=events,
        )

    async def health(self) -> bool:
        """Health-check by listing MCP tools; reachable + authed => healthy."""
        request = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "tools/list",
            "params": {},
        }
        async with httpx.AsyncClient(verify=self._verify, timeout=self._timeout) as client:
            try:
                resp = await client.post(self._url, headers=self._headers, json=request)
            except httpx.HTTPError:  # pragma: no cover - network path
                return False
            return resp.status_code == 200


def _parse_time(value: object) -> datetime:
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime.now(UTC)
