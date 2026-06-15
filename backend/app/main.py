"""SentinelAI FastAPI application entrypoint."""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware

from app.api.admin_routes import router as admin_router
from app.api.provider_routes import router as provider_router
from app.api.routes import router
from app.api.tenant_routes import router as tenant_router
from app.core.config import get_settings
from app.core.metrics import metrics
from app.core.middleware import (
    RateLimitMiddleware,
    RequestLoggingMiddleware,
    configure_logging,
)
from app.db.bootstrap import init_db, seed_default


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_json)
    await init_db()
    await seed_default()
    yield


def _cors_origins(raw: str) -> list[str]:
    return [o.strip() for o in raw.split(",") if o.strip()] or ["*"]


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        description="Agentic Threat Detection & Incident Response on Splunk",
        version="0.3.0",
        lifespan=lifespan,
    )
    app.add_middleware(RateLimitMiddleware, limit_per_minute=settings.rate_limit_per_minute)
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins(settings.cors_origins),
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router, prefix="/api/v1")
    app.include_router(admin_router, prefix="/api/v1")
    app.include_router(provider_router, prefix="/api/v1")
    app.include_router(tenant_router, prefix="/api/v1")

    @app.get("/metrics", tags=["system"])
    async def metrics_endpoint() -> Response:
        return Response(content=metrics.render(), media_type="text/plain")

    return app


app = create_app()
