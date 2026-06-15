"""Tests for plan quotas and enforcement."""
from __future__ import annotations

import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.models import Base
from app.services.metering import KIND_MODEL_CALL, KIND_SEARCH, MeteringService, PriceBook
from app.services.quotas import (
    PLAN_QUOTAS,
    UNLIMITED,
    QuotaExceeded,
    QuotaService,
    quota_for,
)


@pytest_asyncio.fixture
async def sm():
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(bind=eng, expire_on_commit=False)
    await eng.dispose()


_PB = PriceBook(search_cents=1, model_call_cents=1, tokens_cents_per_1k=1, action_cents=1)


async def _meter(sm, tenant, kind, qty):
    async with sm() as s:
        await MeteringService(s, price_book=_PB).record(tenant, kind, quantity=qty)
        await s.commit()


class TestPlanQuotas:
    def test_known_plans(self):
        assert quota_for("free").searches_per_month == 100
        assert quota_for("enterprise").searches_per_month == UNLIMITED
        assert "pro" in PLAN_QUOTAS

    def test_unknown_plan_falls_back_to_free(self):
        assert quota_for("mystery").searches_per_month == quota_for("free").searches_per_month


class TestQuotaService:
    async def test_under_limit_allowed(self, sm):
        await _meter(sm, "t1", KIND_SEARCH, 10)
        async with sm() as s:
            st = await QuotaService(s).status("t1", "free", KIND_SEARCH, want=1)
            assert st.used == 10
            assert st.limit == 100
            assert st.allowed is True
            assert st.remaining == 90
            assert st.warn is False

    async def test_warn_threshold(self, sm):
        await _meter(sm, "t1", KIND_SEARCH, 80)  # 80% of 100
        async with sm() as s:
            st = await QuotaService(s).status("t1", "free", KIND_SEARCH, want=1)
            assert st.warn is True
            assert st.allowed is True

    async def test_over_limit_denied(self, sm):
        await _meter(sm, "t1", KIND_SEARCH, 100)
        async with sm() as s:
            st = await QuotaService(s).status("t1", "free", KIND_SEARCH, want=1)
            assert st.allowed is False
            assert st.remaining == 0

    async def test_check_or_raise(self, sm):
        await _meter(sm, "t1", KIND_SEARCH, 100)
        async with sm() as s:
            try:
                await QuotaService(s).check_or_raise("t1", "free", KIND_SEARCH, want=1)
                raise AssertionError("expected QuotaExceeded")
            except QuotaExceeded as exc:
                assert exc.kind == KIND_SEARCH
                assert exc.limit == 100

    async def test_enterprise_unlimited(self, sm):
        await _meter(sm, "t1", KIND_SEARCH, 1_000_000)
        async with sm() as s:
            st = await QuotaService(s).status("t1", "enterprise", KIND_SEARCH, want=1000)
            assert st.allowed is True
            assert st.limit == UNLIMITED
            assert st.remaining == UNLIMITED

    async def test_model_call_quota_independent(self, sm):
        await _meter(sm, "t1", KIND_SEARCH, 100)  # searches maxed
        async with sm() as s:
            # model_calls untouched -> still allowed
            st = await QuotaService(s).status("t1", "free", KIND_MODEL_CALL, want=1)
            assert st.allowed is True

    async def test_tenant_scoped(self, sm):
        await _meter(sm, "t1", KIND_SEARCH, 100)
        async with sm() as s:
            other = await QuotaService(s).status("t2", "free", KIND_SEARCH, want=1)
            assert other.used == 0
            assert other.allowed is True
