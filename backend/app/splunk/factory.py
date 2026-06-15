"""Selects the Splunk client implementation from settings."""
from __future__ import annotations

from app.core.config import Settings, get_settings
from app.splunk.client import SplunkClient
from app.splunk.live_client import LiveSplunkClient
from app.splunk.mock_client import MockSplunkClient


def build_splunk_client(settings: Settings | None = None) -> SplunkClient:
    settings = settings or get_settings()
    if settings.splunk_backend == "live":
        return LiveSplunkClient(host=settings.splunk_host, token=settings.splunk_token)
    return MockSplunkClient()
