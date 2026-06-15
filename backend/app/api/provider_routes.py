"""Provider plane API: cross-tenant platform administration.

Reserved for the platform owner (PROVIDER_ADMIN). Tenant-scoped roles — including
a tenant's own ADMIN — cannot reach these endpoints (see rbac.has_permission:
the ADMIN wildcard never grants the PROVIDER scope). Every action is audited.

This is the "manage ALL tenants and users" control plane: list/create/suspend/
reactivate tenants, change plans, view users across tenants, and issue an
audited impersonation token for support.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.api.schemas import (
    CreateTenantRequest,
    ImpersonateResponse,
    ProviderUserResponse,
    TenantPlanRequest,
    TenantResponse,
    TenantStatusRequest,
)
from app.core.principal import Principal, issue_token
from app.core.rbac import Role
from app.db.repositories import TenantRepository, UserRepository
from app.services.audit import AuditService

router = APIRouter(prefix="/provider", tags=["provider"])

# Audit partition for platform-level (cross-tenant) actions.
PLATFORM_TENANT = "__platform__"

_VALID_STATUS = {"active", "suspended", "trial"}
_VALID_PLAN = {"free", "pro", "enterprise"}


@router.get("/tenants", response_model=list[TenantResponse])
async def list_tenants(
    principal: Principal = Depends(deps.require_provider),
    session: AsyncSession = Depends(deps.db_session),
) -> list[TenantResponse]:
    tenants = TenantRepository(session)
    users = UserRepository(session)
    out: list[TenantResponse] = []
    for t in await tenants.list():
        if t.name == PLATFORM_TENANT:
            continue
        members = await users.list(t.id)
        out.append(
            TenantResponse(
                id=t.id, name=t.name, status=t.status, plan=t.plan,
                user_count=len(members), created_at=t.created_at,
            )
        )
    return out


@router.post("/tenants", response_model=TenantResponse, status_code=status.HTTP_201_CREATED)
async def create_tenant(
    body: CreateTenantRequest,
    principal: Principal = Depends(deps.require_provider),
    session: AsyncSession = Depends(deps.db_session),
    audit: AuditService = Depends(deps.get_audit),
) -> TenantResponse:
    if body.status not in _VALID_STATUS:
        raise HTTPException(status_code=422, detail=f"Invalid status '{body.status}'")
    if body.plan not in _VALID_PLAN:
        raise HTTPException(status_code=422, detail=f"Invalid plan '{body.plan}'")
    tenants = TenantRepository(session)
    if await tenants.get_by_name(body.name) is not None:
        raise HTTPException(status_code=409, detail="Tenant already exists")
    tenant = await tenants.create(body.name, status=body.status, plan=body.plan)
    users = UserRepository(session)
    await users.create(tenant.id, body.admin_username, body.admin_password, role=Role.ADMIN.value)
    await audit.record(
        tenant_id=PLATFORM_TENANT,
        actor=principal.username,
        action="provider.tenant_created",
        target_type="tenant",
        target_id=tenant.id,
        detail={"name": body.name, "plan": body.plan, "admin": body.admin_username},
    )
    return TenantResponse(
        id=tenant.id, name=tenant.name, status=tenant.status, plan=tenant.plan,
        user_count=1, created_at=tenant.created_at,
    )


@router.put("/tenants/{tenant_id}/status", response_model=TenantResponse)
async def set_tenant_status(
    tenant_id: str,
    body: TenantStatusRequest,
    principal: Principal = Depends(deps.require_provider),
    session: AsyncSession = Depends(deps.db_session),
    audit: AuditService = Depends(deps.get_audit),
) -> TenantResponse:
    if body.status not in _VALID_STATUS:
        raise HTTPException(status_code=422, detail=f"Invalid status '{body.status}'")
    tenants = TenantRepository(session)
    tenant = await tenants.set_status(tenant_id, body.status)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    await audit.record(
        tenant_id=PLATFORM_TENANT,
        actor=principal.username,
        action="provider.tenant_status_changed",
        target_type="tenant",
        target_id=tenant_id,
        detail={"status": body.status},
    )
    members = await UserRepository(session).list(tenant.id)
    return TenantResponse(
        id=tenant.id, name=tenant.name, status=tenant.status, plan=tenant.plan,
        user_count=len(members), created_at=tenant.created_at,
    )


@router.put("/tenants/{tenant_id}/plan", response_model=TenantResponse)
async def set_tenant_plan(
    tenant_id: str,
    body: TenantPlanRequest,
    principal: Principal = Depends(deps.require_provider),
    session: AsyncSession = Depends(deps.db_session),
    audit: AuditService = Depends(deps.get_audit),
) -> TenantResponse:
    if body.plan not in _VALID_PLAN:
        raise HTTPException(status_code=422, detail=f"Invalid plan '{body.plan}'")
    tenants = TenantRepository(session)
    tenant = await tenants.set_plan(tenant_id, body.plan)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    await audit.record(
        tenant_id=PLATFORM_TENANT,
        actor=principal.username,
        action="provider.tenant_plan_changed",
        target_type="tenant",
        target_id=tenant_id,
        detail={"plan": body.plan},
    )
    members = await UserRepository(session).list(tenant.id)
    return TenantResponse(
        id=tenant.id, name=tenant.name, status=tenant.status, plan=tenant.plan,
        user_count=len(members), created_at=tenant.created_at,
    )


@router.get("/users", response_model=list[ProviderUserResponse])
async def list_all_users(
    principal: Principal = Depends(deps.require_provider),
    session: AsyncSession = Depends(deps.db_session),
) -> list[ProviderUserResponse]:
    """Every user across every tenant (platform-wide visibility)."""
    tenants = TenantRepository(session)
    users = UserRepository(session)
    out: list[ProviderUserResponse] = []
    for t in await tenants.list():
        if t.name == PLATFORM_TENANT:
            continue
        for u in await users.list(t.id):
            out.append(
                ProviderUserResponse(
                    id=u.id, username=u.username, role=u.role,
                    tenant_id=t.id, tenant_name=t.name,
                )
            )
    return out


@router.post("/tenants/{tenant_id}/impersonate", response_model=ImpersonateResponse)
async def impersonate(
    tenant_id: str,
    principal: Principal = Depends(deps.require_provider),
    session: AsyncSession = Depends(deps.db_session),
    audit: AuditService = Depends(deps.get_audit),
) -> ImpersonateResponse:
    """Issue a short-lived token acting as a tenant's admin, for support.

    Audited on BOTH the platform partition and the target tenant so the tenant
    has a record that a provider operator accessed their workspace.
    """
    tenants = TenantRepository(session)
    tenant = await tenants.get(tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    users = UserRepository(session)
    members = await users.list(tenant_id)
    admin = next((u for u in members if u.role == Role.ADMIN.value), None)
    if admin is None:
        raise HTTPException(status_code=404, detail="Tenant has no admin to impersonate")
    target = Principal(
        user_id=admin.id, username=admin.username, tenant_id=tenant_id, role=admin.role
    )
    token = issue_token(target)
    await audit.record(
        tenant_id=PLATFORM_TENANT, actor=principal.username,
        action="provider.impersonation", target_type="tenant", target_id=tenant_id,
        detail={"as_user": admin.username},
    )
    await audit.record(
        tenant_id=tenant_id, actor=principal.username,
        action="provider.impersonation", target_type="user", target_id=admin.id,
        detail={"by_provider": principal.username},
    )
    return ImpersonateResponse(
        access_token=token, tenant=tenant.name, role=admin.role,
        impersonated_user=admin.username,
    )
