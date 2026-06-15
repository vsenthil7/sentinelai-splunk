"""Role-based access control.

Roles map to permission sets. Permissions gate API operations. This is
deliberately simple and explicit so it is auditable; it can later be backed by
a policy engine without changing call sites.
"""
from __future__ import annotations

from enum import Enum


class Permission(str, Enum):
    SEARCH_RUN = "search:run"
    DETECTION_RUN = "detection:run"
    INVESTIGATION_READ = "investigation:read"
    INVESTIGATION_RUN = "investigation:run"
    ACTION_APPROVE = "action:approve"
    CASE_WRITE = "case:write"  # notes, assignment, status
    AUDIT_READ = "audit:read"
    ADMIN = "admin:*"  # tenant-scoped user/settings management
    PROVIDER = "provider:*"  # cross-tenant platform administration (super-admin)


class Role(str, Enum):
    VIEWER = "viewer"
    ANALYST = "analyst"
    RESPONDER = "responder"
    ADMIN = "admin"
    PROVIDER_ADMIN = "provider_admin"  # platform owner; above tenant admin


_ROLE_PERMISSIONS: dict[Role, set[Permission]] = {
    Role.VIEWER: {
        Permission.INVESTIGATION_READ,
    },
    Role.ANALYST: {
        Permission.INVESTIGATION_READ,
        Permission.SEARCH_RUN,
        Permission.DETECTION_RUN,
        Permission.INVESTIGATION_RUN,
        Permission.CASE_WRITE,
    },
    Role.RESPONDER: {
        Permission.INVESTIGATION_READ,
        Permission.SEARCH_RUN,
        Permission.DETECTION_RUN,
        Permission.INVESTIGATION_RUN,
        Permission.CASE_WRITE,
        Permission.ACTION_APPROVE,
    },
    # Tenant admin gets everything EXCEPT the cross-tenant provider scope.
    Role.ADMIN: set(Permission) - {Permission.PROVIDER},
    # Provider admin (platform owner) holds the provider scope. Provider routes
    # gate on PROVIDER specifically; this role is not a tenant member.
    Role.PROVIDER_ADMIN: {Permission.PROVIDER},
}


def permissions_for(role: str) -> set[Permission]:
    try:
        return _ROLE_PERMISSIONS[Role(role)]
    except ValueError:
        return set()


def has_permission(role: str, permission: Permission) -> bool:
    perms = permissions_for(role)
    if permission in perms:
        return True
    # ADMIN wildcard grants tenant-scoped permissions, but NEVER the provider
    # scope (which is cross-tenant and reserved for PROVIDER_ADMIN).
    if permission is Permission.PROVIDER:
        return False
    return Permission.ADMIN in perms
