"""Admin API: tenant-scoped user management. All endpoints require ADMIN."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.api import deps
from app.api.schemas import (
    CreateUserRequest,
    LinkIdentityRequest,
    UpdateRoleRequest,
    UserResponse,
)
from app.core.principal import Principal
from app.core.rbac import Permission, Role
from app.db.repositories import UserRepository
from app.services.audit import AuditService

router = APIRouter(prefix="/admin", tags=["admin"])

_VALID_ROLES = {r.value for r in Role}


def _to_response(user) -> UserResponse:  # type: ignore[no-untyped-def]
    return UserResponse(
        id=user.id,
        username=user.username,
        role=user.role,
        external_id=user.external_id,
        created_at=user.created_at,
    )


@router.get("/users", response_model=list[UserResponse])
async def list_users(
    principal: Principal = Depends(deps.require(Permission.ADMIN)),
    users: UserRepository = Depends(deps.get_user_repo),
) -> list[UserResponse]:
    return [_to_response(u) for u in await users.list(principal.tenant_id)]


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: CreateUserRequest,
    principal: Principal = Depends(deps.require(Permission.ADMIN)),
    users: UserRepository = Depends(deps.get_user_repo),
    audit: AuditService = Depends(deps.get_audit),
) -> UserResponse:
    if body.role not in _VALID_ROLES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown role '{body.role}'",
        )
    existing = await users.get_by_username(principal.tenant_id, body.username)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Username already exists"
        )
    user = await users.create(
        principal.tenant_id, body.username, body.password, role=body.role
    )
    await audit.record(
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="admin.user_created",
        target_type="user",
        target_id=user.id,
        detail={"username": body.username, "role": body.role},
    )
    return _to_response(user)


@router.put("/users/{user_id}/role", response_model=UserResponse)
async def update_role(
    user_id: str,
    body: UpdateRoleRequest,
    principal: Principal = Depends(deps.require(Permission.ADMIN)),
    users: UserRepository = Depends(deps.get_user_repo),
    audit: AuditService = Depends(deps.get_audit),
) -> UserResponse:
    if body.role not in _VALID_ROLES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown role '{body.role}'",
        )
    user = await users.set_role(principal.tenant_id, user_id, body.role)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    await audit.record(
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="admin.role_changed",
        target_type="user",
        target_id=user_id,
        detail={"role": body.role},
    )
    return _to_response(user)


@router.post("/users/{user_id}/link-identity", response_model=UserResponse)
async def link_identity(
    user_id: str,
    body: LinkIdentityRequest,
    principal: Principal = Depends(deps.require(Permission.ADMIN)),
    users: UserRepository = Depends(deps.get_user_repo),
    audit: AuditService = Depends(deps.get_audit),
) -> UserResponse:
    """Link an external IdP subject (OIDC/SAML) to a SentinelAI user for SSO."""
    user = await users.link_external_id(principal.tenant_id, user_id, body.external_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    await audit.record(
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="admin.identity_linked",
        target_type="user",
        target_id=user_id,
        detail={"external_id": body.external_id},
    )
    return _to_response(user)


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: str,
    principal: Principal = Depends(deps.require(Permission.ADMIN)),
    users: UserRepository = Depends(deps.get_user_repo),
    audit: AuditService = Depends(deps.get_audit),
) -> None:
    if user_id == principal.user_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Cannot delete your own account"
        )
    ok = await users.delete(principal.tenant_id, user_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    await audit.record(
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="admin.user_deleted",
        target_type="user",
        target_id=user_id,
    )
