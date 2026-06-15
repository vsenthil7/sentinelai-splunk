"""Tenant self-service: settings + BYO credentials. Tenant ADMIN only.

- GET  /tenant/settings    : plan/status + non-secret settings JSON
- PUT  /tenant/settings    : update non-secret settings (merge)
- GET  /tenant/credentials : non-secret credential view (secrets as *_set booleans)
- PUT  /tenant/credentials : update credentials; secrets are write-only, encrypted

Secrets are NEVER returned by any endpoint here, and the update request takes
them write-only (None = unchanged, "" = clear). All changes are audited; secret
values are never placed in audit detail or logs.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.api.schemas import (
    CredentialView,
    QuotaResponse,
    QuotaStatusItem,
    TenantSettingsResponse,
    UpdateCredentialsRequest,
    UpdateSettingsRequest,
    UsageRollupResponse,
)
from app.core.principal import Principal
from app.core.rbac import Permission
from app.db.repositories import TenantRepository
from app.services.audit import AuditService
from app.services.credentials import CredentialRepository
from app.services.metering import MeteringService

router = APIRouter(prefix="/tenant", tags=["tenant"])

_VALID_MODES = {"managed", "byo"}
_VALID_SPLUNK = {"mock", "live", "mcp"}
_VALID_AI = {"mock", "live"}


@router.get("/settings", response_model=TenantSettingsResponse)
async def get_settings_(
    principal: Principal = Depends(deps.require(Permission.ADMIN)),
    session: AsyncSession = Depends(deps.db_session),
) -> TenantSettingsResponse:
    tenant = await TenantRepository(session).get(principal.tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return TenantSettingsResponse(
        tenant=tenant.name, plan=tenant.plan, status=tenant.status,
        settings=dict(tenant.settings or {}),
    )


@router.put("/settings", response_model=TenantSettingsResponse)
async def update_settings_(
    body: UpdateSettingsRequest,
    principal: Principal = Depends(deps.require(Permission.ADMIN)),
    session: AsyncSession = Depends(deps.db_session),
    audit: AuditService = Depends(deps.get_audit),
) -> TenantSettingsResponse:
    tenants = TenantRepository(session)
    tenant = await tenants.update_settings(principal.tenant_id, body.settings)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    await audit.record(
        tenant_id=principal.tenant_id, actor=principal.username,
        action="tenant.settings_updated", target_type="tenant",
        target_id=principal.tenant_id, detail={"keys": sorted(body.settings.keys())},
    )
    return TenantSettingsResponse(
        tenant=tenant.name, plan=tenant.plan, status=tenant.status,
        settings=dict(tenant.settings or {}),
    )


@router.get("/credentials", response_model=CredentialView)
async def get_credentials(
    principal: Principal = Depends(deps.require(Permission.ADMIN)),
    session: AsyncSession = Depends(deps.db_session),
) -> CredentialView:
    view = await CredentialRepository(session).view(principal.tenant_id)
    return CredentialView(**view.__dict__)


@router.put("/credentials", response_model=CredentialView)
async def update_credentials(
    body: UpdateCredentialsRequest,
    principal: Principal = Depends(deps.require(Permission.ADMIN)),
    session: AsyncSession = Depends(deps.db_session),
    audit: AuditService = Depends(deps.get_audit),
) -> CredentialView:
    if body.mode is not None and body.mode not in _VALID_MODES:
        raise HTTPException(status_code=422, detail=f"Invalid mode '{body.mode}'")
    if body.splunk_backend is not None and body.splunk_backend not in _VALID_SPLUNK:
        raise HTTPException(status_code=422, detail="Invalid splunk_backend")
    if body.ai_backend is not None and body.ai_backend not in _VALID_AI:
        raise HTTPException(status_code=422, detail="Invalid ai_backend")
    repo = CredentialRepository(session)
    await repo.upsert(
        principal.tenant_id,
        mode=body.mode,
        splunk_backend=body.splunk_backend,
        splunk_host=body.splunk_host,
        splunk_token=body.splunk_token,
        splunk_mcp_url=body.splunk_mcp_url,
        splunk_mcp_token=body.splunk_mcp_token,
        ai_backend=body.ai_backend,
        ai_model=body.ai_model,
        ai_token=body.ai_token,
    )
    # Audit which fields changed — NEVER the secret values themselves.
    changed = [
        k for k, v in body.model_dump().items() if v is not None
    ]
    await audit.record(
        tenant_id=principal.tenant_id, actor=principal.username,
        action="tenant.credentials_updated", target_type="tenant",
        target_id=principal.tenant_id, detail={"changed_fields": sorted(changed)},
    )
    view = await repo.view(principal.tenant_id)
    return CredentialView(**view.__dict__)


@router.get("/usage", response_model=UsageRollupResponse)
async def get_usage(
    principal: Principal = Depends(deps.require(Permission.ADMIN)),
    session: AsyncSession = Depends(deps.db_session),
) -> UsageRollupResponse:
    """This tenant's metered usage and computed cost, grouped by kind."""
    tenant = await TenantRepository(session).get(principal.tenant_id)
    name = tenant.name if tenant else principal.tenant_id
    rollup = await MeteringService(session).rollup(principal.tenant_id)
    return UsageRollupResponse(
        tenant=name, by_kind=rollup.by_kind,
        total_cost_cents=rollup.total_cost_cents, total_cost_usd=rollup.total_cost_usd,
    )


@router.get("/quota", response_model=QuotaResponse)
async def get_quota(
    principal: Principal = Depends(deps.require(Permission.ADMIN)),
    session: AsyncSession = Depends(deps.db_session),
) -> QuotaResponse:
    """This tenant's plan quota headroom (month-to-date) for metered operations."""
    from app.services.metering import KIND_MODEL_CALL, KIND_SEARCH
    from app.services.quotas import QuotaService

    tenant = await TenantRepository(session).get(principal.tenant_id)
    name = tenant.name if tenant else principal.tenant_id
    plan = tenant.plan if tenant else "free"
    svc = QuotaService(session)
    items: list[QuotaStatusItem] = []
    for kind in (KIND_SEARCH, KIND_MODEL_CALL):
        st = await svc.status(principal.tenant_id, plan, kind, want=0)
        items.append(
            QuotaStatusItem(
                kind=st.kind, used=st.used, limit=st.limit,
                remaining=st.remaining, warn=st.warn,
            )
        )
    return QuotaResponse(tenant=name, plan=plan, quotas=items)
