"""Tamper-evident audit logging.

Every security-relevant action is recorded append-only. Each entry embeds the
hash of the previous entry for its tenant, forming a chain: altering or deleting
any historical entry breaks every subsequent hash, so tampering is detectable
via ``verify_chain``.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLogRow


def _compute_hash(
    tenant_id: str,
    actor: str,
    action: str,
    target_type: str,
    target_id: str,
    detail: dict[str, Any],
    prev_hash: str,
) -> str:
    canonical = json.dumps(
        {
            "tenant_id": tenant_id,
            "actor": actor,
            "action": action,
            "target_type": target_type,
            "target_id": target_id,
            "detail": detail,
            "prev_hash": prev_hash,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class AuditService:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def _last_hash(self, tenant_id: str) -> str:
        result = await self._session.execute(
            select(AuditLogRow.entry_hash)
            .where(AuditLogRow.tenant_id == tenant_id)
            .order_by(AuditLogRow.id.desc())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        return row or ""

    async def record(
        self,
        *,
        tenant_id: str,
        actor: str,
        action: str,
        target_type: str,
        target_id: str,
        detail: dict[str, Any] | None = None,
    ) -> AuditLogRow:
        detail = detail or {}
        prev_hash = await self._last_hash(tenant_id)
        entry_hash = _compute_hash(
            tenant_id, actor, action, target_type, target_id, detail, prev_hash
        )
        entry = AuditLogRow(
            tenant_id=tenant_id,
            actor=actor,
            action=action,
            target_type=target_type,
            target_id=target_id,
            detail=detail,
            prev_hash=prev_hash,
            entry_hash=entry_hash,
        )
        self._session.add(entry)
        await self._session.flush()
        return entry

    async def list(self, tenant_id: str, limit: int = 100, offset: int = 0) -> list[AuditLogRow]:
        result = await self._session.execute(
            select(AuditLogRow)
            .where(AuditLogRow.tenant_id == tenant_id)
            .order_by(AuditLogRow.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def verify_chain(self, tenant_id: str) -> bool:
        """Recompute the chain; return True iff every entry's hash is intact."""
        result = await self._session.execute(
            select(AuditLogRow)
            .where(AuditLogRow.tenant_id == tenant_id)
            .order_by(AuditLogRow.id.asc())
        )
        prev_hash = ""
        for entry in result.scalars().all():
            expected = _compute_hash(
                entry.tenant_id,
                entry.actor,
                entry.action,
                entry.target_type,
                entry.target_id,
                entry.detail,
                prev_hash,
            )
            if entry.prev_hash != prev_hash or entry.entry_hash != expected:
                return False
            prev_hash = entry.entry_hash
        return True
