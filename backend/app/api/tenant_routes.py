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
    TenantSettingsResponse,
    UpdateCredentialsRequest,
    UpdateSettingsRequest,
)
from app.core.principal import Principal
from app.core.rbac import Permission
from app.db.repositories import TenantRepository
from app.services.audit import AuditService
from app.services.credentials import CredentialRepository

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
