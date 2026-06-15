"""Test fixtures for the enterprise architecture.

Each test gets an isolated in-memory SQLite database and a fresh app with
overridden dependencies, so tests are hermetic and parallel-safe.
"""
from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

os.environ.setdefault("SENTINEL_DATABASE_URL", "sqlite+aiosqlite:///:memory:")

from app.api import deps  # noqa: E402
from app.db.bootstrap import DEFAULT_TENANT, DEFAULT_USER  # noqa: E402
from app.db.models import Base  # noqa: E402
from app.db.repositories import TenantRepository, UserRepository  # noqa: E402
from app.main import create_app  # noqa: E402


@pytest_asyncio.fixture
async def engine():
    # A single shared in-memory DB per test via StaticPool-like URI.
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def sessionmaker_(engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)


@pytest_asyncio.fixture
async def session(sessionmaker_) -> AsyncIterator[AsyncSession]:
    async with sessionmaker_() as s:
        yield s


@pytest_asyncio.fixture
async def seeded(sessionmaker_) -> dict[str, str]:
    """Seed default tenant + admin user; return useful ids."""
    async with sessionmaker_() as s:
        tenant = await TenantRepository(s).ensure(DEFAULT_TENANT)
        users = UserRepository(s)
        admin = await users.create(tenant.id, DEFAULT_USER, "sentinel-demo", role="admin")
        await s.commit()
        return {"tenant_id": tenant.id, "tenant": DEFAULT_TENANT, "admin_id": admin.id}


@pytest_asyncio.fixture
async def client(sessionmaker_, seeded) -> AsyncIterator[AsyncClient]:
    app = create_app()

    async def _override_session() -> AsyncIterator[AsyncSession]:
        async with sessionmaker_() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    app.dependency_overrides[deps.db_session] = _override_session
    # Reset stateless singletons that hold mutable state between tests.
    deps._notifier = deps._build_notifier()  # type: ignore[attr-defined]
    deps._splunk.set_healthy(True) if hasattr(deps._splunk, "set_healthy") else None
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def auth(client) -> dict[str, str]:
    resp = await client.post(
        "/api/v1/auth/login",
        json={"username": "analyst", "password": "sentinel-demo", "tenant": "default"},
    )
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def provider_auth(client, sessionmaker_) -> dict[str, str]:
    """Seed the platform tenant + provider_admin and return its auth header."""
    from app.db.bootstrap import (
        PLATFORM_TENANT,
        PROVIDER_PASSWORD,
        PROVIDER_USER,
    )

    async with sessionmaker_() as s:
        platform = await TenantRepository(s).ensure(PLATFORM_TENANT)
        users = UserRepository(s)
        if await users.get_by_username(platform.id, PROVIDER_USER) is None:
            await users.create(
                platform.id, PROVIDER_USER, PROVIDER_PASSWORD, role="provider_admin"
            )
        await s.commit()
    resp = await client.post(
        "/api/v1/auth/login",
        json={"username": PROVIDER_USER, "password": PROVIDER_PASSWORD, "tenant": PLATFORM_TENANT},
    )
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest_asyncio.fixture
async def make_user(client, sessionmaker_, seeded):
    """Factory: create a user with a role and return its auth header + id."""

    async def _make(username: str, role: str, password: str = "password123") -> dict:
        async with sessionmaker_() as s:
            user = await UserRepository(s).create(
                seeded["tenant_id"], username, password, role=role
            )
            await s.commit()
            uid = user.id
        resp = await client.post(
            "/api/v1/auth/login",
            json={"username": username, "password": password, "tenant": "default"},
        )
        return {
            "headers": {"Authorization": f"Bearer {resp.json()['access_token']}"},
            "id": uid,
        }

    return _make
