"""Splunk client abstraction.

Everything in the app depends on the ``SplunkClient`` protocol, never on a
concrete transport. This is what lets us run a deterministic mock now and swap
to a real Splunk Enterprise / Cloud instance (or the Splunk MCP Server) later
by setting ``SENTINEL_SPLUNK_BACKEND=live`` plus host/token env vars.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.models.domain import SearchResult


class SplunkError(Exception):
    """Base class for Splunk transport/query errors."""


class SplunkAuthError(SplunkError):
    """Raised when authentication to Splunk fails."""


class SplunkQueryError(SplunkError):
    """Raised when an SPL query is malformed or rejected."""


class SplunkConnectionError(SplunkError):
    """Raised when the Splunk endpoint is unreachable."""


class SplunkClient(ABC):
    """Transport-agnostic Splunk interface."""

    @abstractmethod
    async def search(self, spl: str, earliest: str = "-24h", latest: str = "now") -> SearchResult:
        """Run an SPL search and return structured results."""

    @abstractmethod
    async def health(self) -> bool:
        """Return True if the Splunk backend is reachable and authenticated."""
