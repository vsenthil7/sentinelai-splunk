"""Selects the AI model implementation from settings."""
from __future__ import annotations

from app.core.config import Settings, get_settings
from app.services.ai_model import AIModel, LiveAIModel, MockAIModel


def build_ai_model(settings: Settings | None = None) -> AIModel:
    settings = settings or get_settings()
    if settings.ai_backend == "live":
        return LiveAIModel(
            base_url=settings.splunk_mcp_url or settings.splunk_host,
            model=settings.ai_model,
            token=settings.splunk_token,
        )
    return MockAIModel()
