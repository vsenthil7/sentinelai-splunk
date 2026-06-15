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
    ADMIN = "admin:*"  # user/tenant management


class Role(str, Enum):
    VIEWER = "viewer"
    ANALYST = "analyst"
    RESPONDER = "responder"
    ADMIN = "admin"


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
    Role.ADMIN: set(Permission),  # all permissions
}


def permissions_for(role: str) -> set[Permission]:
    try:
        return _ROLE_PERMISSIONS[Role(role)]
    except ValueError:
        return set()


def has_permission(role: str, permission: Permission) -> bool:
    perms = permissions_for(role)
    return Permission.ADMIN in perms or permission in perms
