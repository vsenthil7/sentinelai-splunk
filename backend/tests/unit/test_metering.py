"""Tests for usage metering and cost calculation."""
from __future__ import annotations

import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.models import Base
from app.services.metering import (
    KIND_ACTION,
    KIND_MODEL_CALL,
    KIND_SEARCH,
    KIND_TOKENS,
    MeteringService,
    PriceBook,
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


class TestPriceBook:
    def test_cost_per_kind(self):
        pb = PriceBook(
            search_cents=2, model_call_cents=5, tokens_cents_per_1k=1, action_cents=10
        )
        assert pb.cost_cents(KIND_SEARCH, 3) == 6
        assert pb.cost_cents(KIND_MODEL_CALL, 4) == 20
        assert pb.cost_cents(KIND_ACTION, 2) == 20

    def test_token_block_rounding(self):
        pb = PriceBook(
            search_cents=2, model_call_cents=5, tokens_cents_per_1k=3, action_cents=10
        )
        # 1 token -> 1 block; 1000 -> 1 block; 1001 -> 2 blocks.
        assert pb.cost_cents(KIND_TOKENS, 1) == 3
        assert pb.cost_cents(KIND_TOKENS, 1000) == 3
        assert pb.cost_cents(KIND_TOKENS, 1001) == 6

    def test_unknown_kind_zero(self):
        pb = PriceBook(
            search_cents=2, model_call_cents=5, tokens_cents_per_1k=1, action_cents=10
        )
        assert pb.cost_cents("bogus", 99) == 0

    def test_from_settings(self):
        pb = PriceBook.from_settings()
        assert pb.search_cents >= 0  # sourced from config defaults


class TestMeteringService:
    async def test_record_and_rollup(self, sm):
        pb = PriceBook(
            search_cents=2, model_call_cents=5, tokens_cents_per_1k=1, action_cents=10
        )
        async with sm() as s:
            svc = MeteringService(s, price_book=pb)
            await svc.record("t1", KIND_SEARCH, quantity=5, detail="run")
            await svc.record("t1", KIND_MODEL_CALL, quantity=3)
            await svc.record("t1", KIND_ACTION, quantity=1)
            await s.commit()
            roll = await svc.rollup("t1")
            assert roll.by_kind[KIND_SEARCH] == {"quantity": 5, "cost_cents": 10}
            assert roll.by_kind[KIND_MODEL_CALL] == {"quantity": 3, "cost_cents": 15}
            assert roll.by_kind[KIND_ACTION] == {"quantity": 1, "cost_cents": 10}
            assert roll.total_cost_cents == 35
            assert roll.total_cost_usd == 0.35

    async def test_unknown_kind_not_recorded(self, sm):
        async with sm() as s:
            svc = MeteringService(s)
            result = await svc.record("t1", "nonsense", quantity=1)
            assert result is None
            await s.commit()
            roll = await svc.rollup("t1")
            assert roll.total_cost_cents == 0

    async def test_rollup_is_tenant_scoped(self, sm):
        pb = PriceBook(
            search_cents=2, model_call_cents=5, tokens_cents_per_1k=1, action_cents=10
        )
        async with sm() as s:
            svc = MeteringService(s, price_book=pb)
            await svc.record("t1", KIND_SEARCH, quantity=10)
            await svc.record("t2", KIND_SEARCH, quantity=1)
            await s.commit()
            assert (await svc.rollup("t1")).total_cost_cents == 20
            assert (await svc.rollup("t2")).total_cost_cents == 2

    async def test_empty_rollup(self, sm):
        async with sm() as s:
            roll = await MeteringService(s).rollup("nobody")
            assert roll.total_cost_cents == 0
            assert roll.by_kind == {}

    async def test_rollup_time_window(self, sm):
        from datetime import UTC, datetime, timedelta

        pb = PriceBook(
            search_cents=2, model_call_cents=5, tokens_cents_per_1k=1, action_cents=10
        )
        async with sm() as s:
            svc = MeteringService(s, price_book=pb)
            await svc.record("t1", KIND_SEARCH, quantity=4)
            await s.commit()
            now = datetime.now(UTC)
            # Window that includes now -> sees the event.
            within = await svc.rollup(
                "t1", since=now - timedelta(hours=1), until=now + timedelta(hours=1)
            )
            assert within.total_cost_cents == 8
            # Window entirely in the past -> excludes it.
            past = await svc.rollup(
                "t1", since=now - timedelta(hours=2), until=now - timedelta(hours=1)
            )
            assert past.total_cost_cents == 0
