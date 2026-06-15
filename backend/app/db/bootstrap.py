"""Schema creation and seed data.

For dev/demo we create tables directly from metadata; Alembic migrations are
provided for prod (see alembic/). Seeds a default tenant and analyst account.
"""
from __future__ import annotations

from app.db.models import Base
from app.db.repositories import TenantRepository, UserRepository
from app.db.session import get_engine, get_sessionmaker

DEFAULT_TENANT = "default"
DEFAULT_USER = "analyst"
DEFAULT_PASSWORD = "sentinel-demo"


async def init_db() -> None:
    """Create tables from metadata for dev/test.

    In production set SENTINEL_DB_CREATE_ALL=false and manage schema with
    `alembic upgrade head`; this becomes a no-op so migrations are authoritative.
    """
    from app.core.config import get_settings

    if not get_settings().db_create_all:
        return
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def seed_default() -> None:
    maker = get_sessionmaker()
    async with maker() as session:
        tenants = TenantRepository(session)
        users = UserRepository(session)
        tenant = await tenants.ensure(DEFAULT_TENANT)
        existing = await users.get_by_username(tenant.id, DEFAULT_USER)
        if existing is None:
            await users.create(
                tenant.id, DEFAULT_USER, DEFAULT_PASSWORD, role="admin"
            )
        await session.commit()
