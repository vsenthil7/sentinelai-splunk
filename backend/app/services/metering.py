"""Usage metering and cost calculation.

Answers the question: "how much did each tenant's activity cost?" Every billable
event (an SPL search, an AI model call, tokens processed, a response action) is
recorded with a cost computed from a configurable price book. Costs are
denormalized onto each event row so historical totals stay stable even if the
price book changes later.

Design notes:
- The price book lives in settings (env-overridable) so pricing can be tuned per
  deployment without code changes.
- ``MeteringService.record`` is best-effort and must never break the request it
  meters; callers wrap it so a metering failure can't fail an investigation.
- Rollups are computed with SQL aggregation, grouped by kind, for a tenant and
  optional time window.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.models import UsageEventRow

# Recognized billable event kinds.
KIND_SEARCH = "search"
KIND_MODEL_CALL = "model_call"
KIND_TOKENS = "tokens"
KIND_ACTION = "action"
VALID_KINDS = {KIND_SEARCH, KIND_MODEL_CALL, KIND_TOKENS, KIND_ACTION}


@dataclass(frozen=True)
class PriceBook:
    """Cents-per-unit pricing. Sourced from settings; tunable per deployment."""

    search_cents: int
    model_call_cents: int
    tokens_cents_per_1k: int
    action_cents: int

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> PriceBook:
        s = settings or get_settings()
        return cls(
            search_cents=s.price_search_cents,
            model_call_cents=s.price_model_call_cents,
            tokens_cents_per_1k=s.price_tokens_cents_per_1k,
            action_cents=s.price_action_cents,
        )

    def cost_cents(self, kind: str, quantity: int) -> int:
        """Compute the cost in cents for a quantity of a given event kind."""
        if kind == KIND_SEARCH:
            return self.search_cents * quantity
        if kind == KIND_MODEL_CALL:
            return self.model_call_cents * quantity
        if kind == KIND_TOKENS:
            # tokens priced per 1,000 (rounded up to the nearest 1k block).
            blocks = (quantity + 999) // 1000
            return self.tokens_cents_per_1k * blocks
        if kind == KIND_ACTION:
            return self.action_cents * quantity
        return 0


@dataclass
class UsageRollup:
    tenant_id: str
    by_kind: dict[str, dict[str, int]]  # kind -> {"quantity": n, "cost_cents": c}
    total_cost_cents: int

    @property
    def total_cost_usd(self) -> float:
        return round(self.total_cost_cents / 100, 2)


class MeteringService:
    """Records billable usage events and computes per-tenant cost rollups."""

    def __init__(self, session: AsyncSession, price_book: PriceBook | None = None):
        self._session = session
        self._prices = price_book or PriceBook.from_settings()

    async def record(
        self, tenant_id: str, kind: str, quantity: int = 1, detail: str = ""
    ) -> UsageEventRow | None:
        """Record a usage event, computing cost from the price book.

        Returns None for an unrecognized kind (so a typo can't silently bill).
        """
        if kind not in VALID_KINDS:
            return None
        cost = self._prices.cost_cents(kind, quantity)
        row = UsageEventRow(
            tenant_id=tenant_id, kind=kind, quantity=quantity,
            cost_cents=cost, detail=detail[:200],
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def rollup(
        self,
        tenant_id: str,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> UsageRollup:
        """Aggregate usage + cost for a tenant, grouped by kind."""
        stmt = (
            select(
                UsageEventRow.kind,
                func.coalesce(func.sum(UsageEventRow.quantity), 0),
                func.coalesce(func.sum(UsageEventRow.cost_cents), 0),
            )
            .where(UsageEventRow.tenant_id == tenant_id)
            .group_by(UsageEventRow.kind)
        )
        if since is not None:
            stmt = stmt.where(UsageEventRow.created_at >= since)
        if until is not None:
            stmt = stmt.where(UsageEventRow.created_at <= until)
        result = await self._session.execute(stmt)
        by_kind: dict[str, dict[str, int]] = {}
        total = 0
        for kind, qty, cost in result.all():
            by_kind[kind] = {"quantity": int(qty), "cost_cents": int(cost)}
            total += int(cost)
        return UsageRollup(tenant_id=tenant_id, by_kind=by_kind, total_cost_cents=total)
