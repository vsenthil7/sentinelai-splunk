"""Tenant-scoped repositories.

All queries are filtered by tenant_id, enforcing isolation at the data layer
rather than relying on callers to remember. Investigations are stored as a
queryable header plus a full JSON aggregate payload.
"""
from __future__ import annotations

import builtins
from datetime import UTC
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password
from app.db.models import CaseNoteRow, IncidentRow, InvestigationRow, TenantRow, UserRow
from app.models.domain import Incident, Investigation

if TYPE_CHECKING:
    from app.services.executor import ActionExecutor


class TenantRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_name(self, name: str) -> TenantRow | None:
        result = await self._session.execute(select(TenantRow).where(TenantRow.name == name))
        return result.scalar_one_or_none()

    async def get(self, tenant_id: str) -> TenantRow | None:
        return await self._session.get(TenantRow, tenant_id)

    async def create(self, name: str) -> TenantRow:
        tenant = TenantRow(name=name)
        self._session.add(tenant)
        await self._session.flush()
        return tenant

    async def ensure(self, name: str) -> TenantRow:
        return await self.get_by_name(name) or await self.create(name)


class UserRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_username(self, tenant_id: str, username: str) -> UserRow | None:
        result = await self._session.execute(
            select(UserRow).where(
                UserRow.tenant_id == tenant_id, UserRow.username == username
            )
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        tenant_id: str,
        username: str,
        password: str,
        role: str = "analyst",
        external_id: str | None = None,
    ) -> UserRow:
        user = UserRow(
            tenant_id=tenant_id,
            username=username,
            password_hash=hash_password(password),
            role=role,
            external_id=external_id,
        )
        self._session.add(user)
        await self._session.flush()
        return user

    async def authenticate(
        self, tenant_id: str, username: str, password: str
    ) -> UserRow | None:
        user = await self.get_by_username(tenant_id, username)
        if user and verify_password(password, user.password_hash):
            return user
        return None

    async def list(self, tenant_id: str) -> list[UserRow]:
        result = await self._session.execute(
            select(UserRow).where(UserRow.tenant_id == tenant_id).order_by(UserRow.username)
        )
        return list(result.scalars().all())

    async def get(self, tenant_id: str, user_id: str) -> UserRow | None:
        result = await self._session.execute(
            select(UserRow).where(UserRow.tenant_id == tenant_id, UserRow.id == user_id)
        )
        return result.scalar_one_or_none()

    async def set_role(self, tenant_id: str, user_id: str, role: str) -> UserRow | None:
        user = await self.get(tenant_id, user_id)
        if user is None:
            return None
        user.role = role
        await self._session.flush()
        return user

    async def delete(self, tenant_id: str, user_id: str) -> bool:
        user = await self.get(tenant_id, user_id)
        if user is None:
            return False
        await self._session.delete(user)
        await self._session.flush()
        return True

    async def get_by_external_id(
        self, tenant_id: str, external_id: str
    ) -> UserRow | None:
        result = await self._session.execute(
            select(UserRow).where(
                UserRow.tenant_id == tenant_id, UserRow.external_id == external_id
            )
        )
        return result.scalar_one_or_none()

    async def link_external_id(
        self, tenant_id: str, user_id: str, external_id: str
    ) -> UserRow | None:
        user = await self.get(tenant_id, user_id)
        if user is None:
            return None
        user.external_id = external_id
        await self._session.flush()
        return user


class InvestigationRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def save(self, tenant_id: str, inv: Investigation) -> InvestigationRow:
        existing = await self._get_row(tenant_id, inv.id)
        payload = inv.model_dump(mode="json")
        if existing is None:
            row = InvestigationRow(
                id=inv.id,
                tenant_id=tenant_id,
                title=inv.detection.title,
                severity=inv.detection.severity.value,
                status=inv.detection.status.value,
                entity=inv.detection.entity,
                risk_score=_risk_from(inv),
                is_true_positive=inv.verdict.is_true_positive if inv.verdict else None,
                payload=payload,
            )
            self._session.add(row)
            await self._session.flush()
            return row
        existing.title = inv.detection.title
        existing.severity = inv.detection.severity.value
        existing.status = inv.detection.status.value
        existing.entity = inv.detection.entity
        existing.risk_score = _risk_from(inv)
        existing.is_true_positive = inv.verdict.is_true_positive if inv.verdict else None
        existing.payload = payload
        await self._session.flush()
        return existing

    async def _get_row(self, tenant_id: str, inv_id: str) -> InvestigationRow | None:
        result = await self._session.execute(
            select(InvestigationRow).where(
                InvestigationRow.tenant_id == tenant_id, InvestigationRow.id == inv_id
            )
        )
        return result.scalar_one_or_none()

    async def get(self, tenant_id: str, inv_id: str) -> Investigation | None:
        row = await self._get_row(tenant_id, inv_id)
        if row is None:
            return None
        return Investigation.model_validate(row.payload)

    async def list(
        self,
        tenant_id: str,
        *,
        status: str | None = None,
        severity: str | None = None,
        assignee: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Investigation], int]:
        base = select(InvestigationRow).where(InvestigationRow.tenant_id == tenant_id)
        if status:
            base = base.where(InvestigationRow.status == status)
        if severity:
            base = base.where(InvestigationRow.severity == severity)
        if assignee:
            base = base.where(InvestigationRow.assignee == assignee)
        ordered = base.order_by(
            InvestigationRow.risk_score.desc(), InvestigationRow.created_at.desc()
        )
        result = await self._session.execute(ordered.limit(limit).offset(offset))
        rows = list(result.scalars().all())
        # Total count for pagination metadata.
        count_result = await self._session.execute(base)
        total = len(list(count_result.scalars().all()))
        return [Investigation.model_validate(r.payload) for r in rows], total

    async def set_assignee(
        self, tenant_id: str, inv_id: str, assignee: str | None
    ) -> Investigation | None:
        row = await self._get_row(tenant_id, inv_id)
        if row is None:
            return None
        row.assignee = assignee
        payload = dict(row.payload)
        payload["assignee"] = assignee
        row.payload = payload
        await self._session.flush()
        return Investigation.model_validate(row.payload)

    async def approve_action(
        self, tenant_id: str, inv_id: str, action_index: int
    ) -> Investigation | None:
        row = await self._get_row(tenant_id, inv_id)
        if row is None:
            return None
        payload = dict(row.payload)
        actions = list(cast("list[dict[str, Any]]", payload.get("actions", [])))
        if action_index < 0 or action_index >= len(actions):
            return None
        action = dict(actions[action_index])
        action["requires_approval"] = False
        actions[action_index] = action
        payload["actions"] = actions
        row.payload = payload
        await self._session.flush()
        return Investigation.model_validate(payload)

    async def execute_action(
        self,
        tenant_id: str,
        inv_id: str,
        action_index: int,
        executor: ActionExecutor,
    ) -> tuple[Investigation | None, str | None]:
        """Execute an approved action via the executor; persist execution state.

        Returns (investigation, error). error is set when the action can't run:
        'not_found', 'out_of_range', or 'not_approved'.
        """
        row = await self._get_row(tenant_id, inv_id)
        if row is None:
            return None, "not_found"
        payload = dict(row.payload)
        actions = list(cast("list[dict[str, Any]]", payload.get("actions", [])))
        if action_index < 0 or action_index >= len(actions):
            return None, "out_of_range"
        action = dict(actions[action_index])
        if action.get("requires_approval", True):
            return None, "not_approved"
        result = await executor.execute(action["action_type"], action["target"])
        action["executed"] = True
        action["execution_status"] = result.status
        action["execution_detail"] = result.detail
        action["rollback_token"] = result.rollback_token
        actions[action_index] = action
        payload["actions"] = actions
        if row.status == "investigating":
            row.status = "contained"
            detection = dict(cast("dict[str, Any]", payload["detection"]))
            detection["status"] = "contained"
            payload["detection"] = detection
        row.payload = payload
        await self._session.flush()
        return Investigation.model_validate(payload), None

    async def add_note(
        self, tenant_id: str, inv_id: str, author: str, body: str
    ) -> CaseNoteRow | None:
        row = await self._get_row(tenant_id, inv_id)
        if row is None:
            return None
        note = CaseNoteRow(
            investigation_id=inv_id, tenant_id=tenant_id, author=author, body=body
        )
        self._session.add(note)
        await self._session.flush()
        return note

    async def list_notes(self, tenant_id: str, inv_id: str) -> builtins.list[CaseNoteRow]:
        result = await self._session.execute(
            select(CaseNoteRow)
            .where(CaseNoteRow.tenant_id == tenant_id, CaseNoteRow.investigation_id == inv_id)
            .order_by(CaseNoteRow.created_at.asc())
        )
        return list(result.scalars().all())


def _risk_from(inv: Investigation) -> int:
    """Derive a 0-100 risk score from severity, triage confidence, enrichment."""
    sev_weight = {"info": 10, "low": 30, "medium": 55, "high": 80, "critical": 95}
    base = sev_weight.get(inv.detection.severity.value, 50)
    boost = 1.0
    raw_boost = inv.detection.enrichment.get("risk_boost")
    if isinstance(raw_boost, (int, float)):
        boost = float(raw_boost)
    if inv.verdict is not None:
        if not inv.verdict.is_true_positive:
            return max(0, int(base * 0.2))
        scored = base * (0.6 + 0.4 * inv.verdict.confidence) * boost
        return min(100, int(scored))
    return min(100, int(base * boost))


class IncidentRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def replace_all(self, tenant_id: str, incidents: list[Incident]) -> None:
        """Recompute step: clear this tenant's incidents and store the new set."""
        existing = await self._session.execute(
            select(IncidentRow).where(IncidentRow.tenant_id == tenant_id)
        )
        for row in existing.scalars().all():
            await self._session.delete(row)
        for inc in incidents:
            self._session.add(
                IncidentRow(
                    id=inc.id,
                    tenant_id=tenant_id,
                    title=inc.title,
                    entity=inc.entity,
                    severity=inc.severity.value,
                    risk_score=inc.risk_score,
                    payload=inc.model_dump(mode="json"),
                )
            )
        await self._session.flush()

    async def list(self, tenant_id: str) -> list[Incident]:
        result = await self._session.execute(
            select(IncidentRow)
            .where(IncidentRow.tenant_id == tenant_id)
            .order_by(IncidentRow.risk_score.desc(), IncidentRow.created_at.desc())
        )
        return [Incident.model_validate(r.payload) for r in result.scalars().all()]

    async def get(self, tenant_id: str, incident_id: str) -> Incident | None:
        result = await self._session.execute(
            select(IncidentRow).where(
                IncidentRow.tenant_id == tenant_id, IncidentRow.id == incident_id
            )
        )
        row = result.scalar_one_or_none()
        return Incident.model_validate(row.payload) if row else None


class CaseWorkflowMixin:
    """Status-transition + SLA operations on investigations (uses same session)."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def transition_status(
        self, tenant_id: str, inv_id: str, target: str
    ) -> tuple[Investigation | None, str | None]:
        from datetime import datetime

        from app.models.domain import DetectionStatus
        from app.services.workflow import can_transition

        result = await self._session.execute(
            select(InvestigationRow).where(
                InvestigationRow.tenant_id == tenant_id, InvestigationRow.id == inv_id
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None, "not_found"
        try:
            current = DetectionStatus(row.status)
            target_status = DetectionStatus(target)
        except ValueError:
            return None, "invalid_status"
        if not can_transition(current, target_status):
            return None, "illegal_transition"
        now = datetime.now(UTC)
        row.status = target_status.value
        payload = dict(row.payload)
        detection = dict(cast("dict[str, Any]", payload["detection"]))
        detection["status"] = target_status.value
        payload["detection"] = detection
        row.payload = payload
        if target_status == DetectionStatus.INVESTIGATING and row.acknowledged_at is None:
            row.acknowledged_at = now
        if target_status == DetectionStatus.CONTAINED and row.contained_at is None:
            row.contained_at = now
        await self._session.flush()
        return Investigation.model_validate(payload), None

    async def sla(self, tenant_id: str, inv_id: str) -> dict[str, object] | None:
        from app.services.workflow import compute_sla

        result = await self._session.execute(
            select(InvestigationRow).where(
                InvestigationRow.tenant_id == tenant_id, InvestigationRow.id == inv_id
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return compute_sla(row.created_at, row.acknowledged_at, row.contained_at)


class RuleStateRepository:
    """Per-tenant detection rule enable/disable state."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def disabled_rule_ids(self, tenant_id: str) -> set[str]:
        from app.db.models import RuleStateRow

        result = await self._session.execute(
            select(RuleStateRow).where(
                RuleStateRow.tenant_id == tenant_id, RuleStateRow.enabled.is_(False)
            )
        )
        return {row.rule_id for row in result.scalars().all()}

    async def set_enabled(self, tenant_id: str, rule_id: str, enabled: bool) -> None:
        from app.db.models import RuleStateRow

        result = await self._session.execute(
            select(RuleStateRow).where(
                RuleStateRow.tenant_id == tenant_id, RuleStateRow.rule_id == rule_id
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            self._session.add(
                RuleStateRow(tenant_id=tenant_id, rule_id=rule_id, enabled=enabled)
            )
        else:
            row.enabled = enabled
        await self._session.flush()


class TokenRepository:
    """Server-side token revocation (logout)."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def revoke(self, tenant_id: str, jti: str) -> None:
        from app.db.models import RevokedTokenRow

        existing = await self._session.get(RevokedTokenRow, jti)
        if existing is None:
            self._session.add(RevokedTokenRow(jti=jti, tenant_id=tenant_id))
            await self._session.flush()

    async def is_revoked(self, jti: str) -> bool:
        from app.db.models import RevokedTokenRow

        return await self._session.get(RevokedTokenRow, jti) is not None
