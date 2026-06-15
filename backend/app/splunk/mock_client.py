"""Deterministic mock Splunk backend for local dev and tests.

Generates realistic security telemetry (auth logs, network, endpoint) so the
full agentic pipeline and UI run end-to-end without a live Splunk instance.
Swap for ``LiveSplunkClient`` via env vars when wiring to real Splunk.
"""
from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime, timedelta

from app.models.domain import SearchResult, SplunkEvent
from app.splunk.client import SplunkClient, SplunkQueryError

# Minimal SPL validation: must start with `search` or a piped/generating command,
# and must not be empty. Mirrors how a real instance rejects garbage.
_VALID_SPL = re.compile(r"^\s*(search\b|index\s*=|\||from\b|tstats\b)", re.IGNORECASE)


class MockSplunkClient(SplunkClient):
    """Seeded, deterministic Splunk stand-in."""

    def __init__(self, seed: int = 1337) -> None:
        self._seed = seed
        self._healthy = True

    def _make_sid(self, spl: str) -> str:
        digest = hashlib.sha256(f"{self._seed}:{spl}".encode()).hexdigest()
        return f"mock-{digest[:12]}"

    def set_healthy(self, value: bool) -> None:
        """Test hook to simulate an unreachable backend."""
        self._healthy = value

    async def search(
        self, spl: str, earliest: str = "-24h", latest: str = "now"
    ) -> SearchResult:
        if not spl or not spl.strip():
            raise SplunkQueryError("Empty SPL query")
        if not _VALID_SPL.match(spl):
            raise SplunkQueryError(f"Malformed SPL: {spl!r}")

        events = self._generate_events(spl)
        return SearchResult(
            sid=self._make_sid(spl),
            query=spl,
            event_count=len(events),
            events=events,
        )

    async def health(self) -> bool:
        return self._healthy

    def _generate_events(self, spl: str) -> list[SplunkEvent]:
        """Deterministically synthesize events keyed on the query content."""
        base = datetime.now(UTC)
        lowered = spl.lower()

        if "failed" in lowered or "authentication" in lowered:
            return [
                SplunkEvent(
                    raw=f"Failed password for user admin from 203.0.113.{i}",
                    source="/var/log/auth.log",
                    sourcetype="linux_secure",
                    host="web-prod-01",
                    timestamp=base - timedelta(minutes=i),
                    fields={"user": "admin", "src_ip": f"203.0.113.{i}", "action": "failure"},
                )
                for i in range(1, 13)
            ]
        if "network" in lowered or "firewall" in lowered or "bytes" in lowered:
            return [
                SplunkEvent(
                    raw=f"Outbound connection to 198.51.100.{i}:4444 bytes=540000",
                    source="firewall",
                    sourcetype="cisco:asa",
                    host="db-prod-02",
                    timestamp=base - timedelta(minutes=i * 2),
                    fields={"dest_ip": f"198.51.100.{i}", "dest_port": "4444", "bytes": "540000"},
                )
                for i in range(1, 6)
            ]
        if "process" in lowered or "endpoint" in lowered or "powershell" in lowered:
            return [
                SplunkEvent(
                    raw="powershell.exe -enc SQBFAFgA... (encoded command)",
                    source="WinEventLog:Security",
                    sourcetype="WinEventLog",
                    host="ws-finance-07",
                    timestamp=base - timedelta(minutes=i * 3),
                    fields={"process": "powershell.exe", "parent": "winword.exe"},
                )
                for i in range(1, 4)
            ]
        # Generic: no matches
        return []
