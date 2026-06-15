"""Live Splunk client.

Targets the Splunk REST search API using token-based auth (per hackathon note:
OAuth is in Controlled Availability; use tokens to start). The same interface
is satisfied by the MCP Server transport — only ``_post_search`` changes.

This is exercised at runtime when ``SENTINEL_SPLUNK_BACKEND=live``; in CI we
test the mock. Network calls here are isolated behind ``_post_search`` so they
can be contract-tested with a stubbed httpx transport.
"""
from __future__ import annotations

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


class LiveSplunkClient(SplunkClient):
    def __init__(self, host: str, token: str, *, verify: bool = False, timeout: float = 30.0):
        if not host:
            raise SplunkConnectionError("Splunk host not configured")
        if not token:
            raise SplunkAuthError("Splunk token not configured")
        self._host = host.rstrip("/")
        self._headers = {"Authorization": f"Bearer {token}"}
        self._verify = verify
        self._timeout = timeout

    async def _post_search(self, payload: dict[str, str]) -> dict[str, Any]:
        url = f"{self._host}/services/search/v2/jobs/export"
        async with httpx.AsyncClient(verify=self._verify, timeout=self._timeout) as client:
            try:
                resp = await client.post(url, headers=self._headers, data=payload)
            except httpx.ConnectError as exc:  # pragma: no cover - network path
                raise SplunkConnectionError(str(exc)) from exc
            if resp.status_code == 401:
                raise SplunkAuthError("Splunk rejected the token")
            if resp.status_code == 400:
                raise SplunkQueryError(resp.text)
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
            return data

    async def search(
        self, spl: str, earliest: str = "-24h", latest: str = "now"
    ) -> SearchResult:
        if not spl or not spl.strip():
            raise SplunkQueryError("Empty SPL query")
        payload = {
            "search": spl if spl.strip().lower().startswith("search") else f"search {spl}",
            "earliest_time": earliest,
            "latest_time": latest,
            "output_mode": "json",
        }
        data = await self._post_search(payload)
        rows = data.get("results", [])
        events = [
            SplunkEvent(
                raw=row.get("_raw", ""),
                source=row.get("source", ""),
                sourcetype=row.get("sourcetype", ""),
                host=row.get("host", ""),
                timestamp=_parse_time(row.get("_time")),
                fields={k: str(v) for k, v in row.items() if not k.startswith("_")},
            )
            for row in rows
        ]
        return SearchResult(
            sid=data.get("sid", "live"), query=spl, event_count=len(events), events=events
        )

    async def health(self) -> bool:
        url = f"{self._host}/services/server/health"
        async with httpx.AsyncClient(verify=self._verify, timeout=self._timeout) as client:
            try:
                resp = await client.get(url, headers=self._headers)
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
