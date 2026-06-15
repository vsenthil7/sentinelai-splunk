"""Plan-based quotas and enforcement.

Each commercial plan grants a monthly allowance of billable operations. Before a
metered operation runs, the caller checks the quota; when a tenant is at or over
its plan limit, the operation is refused with HTTP 429 (rate/quota exceeded).
Enterprise is effectively unlimited.

Quota windows are calendar-month-to-date, computed from the same UsageEventRow
data the cost engine uses, so usage and quota never diverge.

Honest gaps (documented):
- Counts are read from the DB per check; under very high concurrency a small
  amount of overage is possible (no row lock). Acceptable for this tier; a hard
  financial gate would use a reserved-counter pattern.
- Enforcement is monthly-to-date; there is no rollover or proration.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import UsageEventRow
from app.services.metering import KIND_MODEL_CALL, KIND_SEARCH

# Sentinel for "no limit".
UNLIMITED = -1


@dataclass(frozen=True)
class PlanQuota:
    """Monthly allowances for a plan. -1 (UNLIMITED) means no cap."""

    searches_per_month: int
    model_calls_per_month: int


# Plan -> quota. Free/trial are capped; pro is generous; enterprise unlimited.
PLAN_QUOTAS: dict[str, PlanQuota] = {
    "free": PlanQuota(searches_per_month=100, model_calls_per_month=50),
    "trial": PlanQuota(searches_per_month=250, model_calls_per_month=150),
    "pro": PlanQuota(searches_per_month=10_000, model_calls_per_month=5_000),
    "enterprise": PlanQuota(searches_per_month=UNLIMITED, model_calls_per_month=UNLIMITED),
}

# Soft-warning threshold (fraction of limit) surfaced in headroom responses.
WARN_FRACTION = 0.8


def quota_for(plan: str) -> PlanQuota:
    """Resolve the quota for a plan name; unknown plans fall back to free."""
    return PLAN_QUOTAS.get(plan, PLAN_QUOTAS["free"])


@dataclass
class QuotaStatus:
    kind: str
    used: int
    limit: int  # -1 == unlimited
    allowed: bool  # would one more unit be permitted?
    warn: bool  # at/over the soft-warning threshold

    @property
    def remaining(self) -> int:
        if self.limit == UNLIMITED:
            return UNLIMITED
        return max(0, self.limit - self.used)


def _month_start(now: datetime | None = None) -> datetime:
    n = now or datetime.now(UTC)
    return n.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


class QuotaService:
    """Checks month-to-date usage against a tenant's plan quota."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def _used_this_month(self, tenant_id: str, kind: str) -> int:
        stmt = (
            select(func.coalesce(func.sum(UsageEventRow.quantity), 0))
            .where(UsageEventRow.tenant_id == tenant_id)
            .where(UsageEventRow.kind == kind)
            .where(UsageEventRow.created_at >= _month_start())
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def status(self, tenant_id: str, plan: str, kind: str, want: int = 1) -> QuotaStatus:
        """Quota status for a kind, assuming `want` more units are about to run."""
        quota = quota_for(plan)
        limit = (
            quota.searches_per_month if kind == KIND_SEARCH
            else quota.model_calls_per_month if kind == KIND_MODEL_CALL
            else UNLIMITED
        )
        used = await self._used_this_month(tenant_id, kind)
        if limit == UNLIMITED:
            return QuotaStatus(kind=kind, used=used, limit=UNLIMITED, allowed=True, warn=False)
        allowed = (used + want) <= limit
        warn = used >= int(limit * WARN_FRACTION)
        return QuotaStatus(kind=kind, used=used, limit=limit, allowed=allowed, warn=warn)

    async def check_or_raise(
        self, tenant_id: str, plan: str, kind: str, want: int = 1
    ) -> QuotaStatus:
        """Raise QuotaExceeded if running `want` more units would exceed the cap."""
        st = await self.status(tenant_id, plan, kind, want)
        if not st.allowed:
            raise QuotaExceeded(kind=kind, used=st.used, limit=st.limit)
        return st


class QuotaExceeded(Exception):
    def __init__(self, kind: str, used: int, limit: int):
        self.kind = kind
        self.used = used
        self.limit = limit
        super().__init__(
            f"Monthly {kind} quota exceeded ({used}/{limit}). Upgrade plan to continue."
        )
