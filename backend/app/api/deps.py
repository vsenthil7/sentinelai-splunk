"""FastAPI dependencies: DB session, principal auth, RBAC enforcement, services."""
from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.db.repositories import CaseWorkflowMixin

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.orchestrator import Orchestrator
from app.core.config import get_settings
from app.core.principal import Principal, TokenClaimsError, principal_from_token
from app.core.rbac import Permission
from app.core.security import AuthError
from app.db.repositories import (
    IncidentRepository,
    InvestigationRepository,
    UserRepository,
)
from app.db.session import get_session
from app.services.ai_factory import build_ai_model
from app.services.audit import AuditService
from app.services.executor import ActionExecutor, MockConnector
from app.services.notifications import (
    CaptureChannel,
    NotificationChannel,
    NotificationService,
    WebhookChannel,
)
from app.splunk.client import SplunkClient
from app.splunk.factory import build_splunk_client

# Stateless infrastructure singletons (no per-tenant state).
_splunk = build_splunk_client()
_model = build_ai_model()
_orchestrator = Orchestrator(_splunk, _model)
_executor = ActionExecutor([MockConnector()])


def _build_notifier() -> NotificationService:
    settings = get_settings()
    channels: list[NotificationChannel] = [CaptureChannel()]
    if settings.notify_webhook_url:
        channels.append(WebhookChannel(settings.notify_webhook_url))
    return NotificationService(channels, settings.notify_high_risk_threshold)


_notifier = _build_notifier()


def get_splunk() -> SplunkClient:
    return _splunk


def get_orchestrator() -> Orchestrator:
    return _orchestrator


def get_executor() -> ActionExecutor:
    return _executor


def get_notifier() -> NotificationService:
    return _notifier


async def db_session() -> AsyncIterator[AsyncSession]:
    async for session in get_session():
        yield session


def get_user_repo(session: AsyncSession = Depends(db_session)) -> UserRepository:
    return UserRepository(session)


def get_investigation_repo(
    session: AsyncSession = Depends(db_session),
) -> InvestigationRepository:
    return InvestigationRepository(session)


def get_incident_repo(
    session: AsyncSession = Depends(db_session),
) -> IncidentRepository:
    return IncidentRepository(session)


def get_workflow(session: AsyncSession = Depends(db_session)) -> CaseWorkflowMixin:
    from app.db.repositories import CaseWorkflowMixin

    return CaseWorkflowMixin(session)


def get_rule_repo(session: AsyncSession = Depends(db_session)):  # type: ignore[no-untyped-def]
    from app.db.repositories import RuleStateRepository

    return RuleStateRepository(session)


def get_audit(session: AsyncSession = Depends(db_session)) -> AuditService:
    return AuditService(session)


async def get_principal(
    authorization: str = Header(default=""),
    session: AsyncSession = Depends(db_session),
) -> Principal:
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token"
        )
    token = authorization.split(" ", 1)[1].strip()
    try:
        principal = principal_from_token(token)
    except (AuthError, TokenClaimsError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)
        ) from exc
    # Enforce server-side revocation (logout).
    if principal.jti is not None:
        from app.db.repositories import TokenRepository

        if await TokenRepository(session).is_revoked(principal.jti):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has been revoked"
            )
    # Block all access for suspended tenants (even with a previously valid token).
    from app.db.repositories import TenantRepository

    tenant = await TenantRepository(session).get(principal.tenant_id)
    if tenant is not None and tenant.status == "suspended":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Tenant is suspended"
        )
    return principal


def require(permission: Permission) -> Callable[[Principal], Awaitable[Principal]]:
    """Dependency factory enforcing a permission on the request principal."""

    async def _checker(principal: Principal = Depends(get_principal)) -> Principal:
        if not principal.can(permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{principal.role}' lacks permission '{permission.value}'",
            )
        return principal

    return _checker


async def require_provider(principal: Principal = Depends(get_principal)) -> Principal:
    """Gate for the cross-tenant provider plane.

    Requires the PROVIDER scope, which only PROVIDER_ADMIN holds. Tenant admins
    explicitly do NOT inherit this (see rbac.has_permission), so the provider
    plane is unreachable by tenant-scoped roles.
    """
    if not principal.can(Permission.PROVIDER):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Provider administration requires the provider_admin role",
        )
    return principal
