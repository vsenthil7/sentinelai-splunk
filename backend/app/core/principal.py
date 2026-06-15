"""Request principal and SSO-ready identity handling.

A ``Principal`` is the authenticated identity for a request: who they are, which
tenant they belong to, and their role. Tokens carry these claims so every
downstream query can be tenant-scoped and permission-checked.

SSO readiness: ``issue_token`` is identical whether the identity was established
by local password auth or by an external IdP (OIDC/SAML). ``link_external_identity``
records the IdP subject on the user, so an SSO callback can map an external
subject to a SentinelAI user and issue the same token.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.core.rbac import Permission, has_permission
from app.core.security import create_access_token, decode_access_token


@dataclass(frozen=True)
class Principal:
    user_id: str
    username: str
    tenant_id: str
    role: str
    jti: str | None = None

    def can(self, permission: Permission) -> bool:
        return has_permission(self.role, permission)


def issue_token(principal: Principal) -> str:
    return create_access_token(
        subject=principal.username,
        extra={
            "uid": principal.user_id,
            "tenant_id": principal.tenant_id,
            "role": principal.role,
        },
    )


class TokenClaimsError(Exception):
    pass


def principal_from_token(token: str) -> Principal:
    payload = decode_access_token(token)
    username = payload.get("sub")
    tenant_id = payload.get("tenant_id")
    role = payload.get("role")
    user_id = payload.get("uid")
    if not (username and tenant_id and role and user_id):
        raise TokenClaimsError("Token missing required identity claims")
    return Principal(
        user_id=str(user_id),
        username=str(username),
        tenant_id=str(tenant_id),
        role=str(role),
        jti=payload.get("jti"),
    )
