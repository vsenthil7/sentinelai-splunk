"""API routes: tenant-scoped, RBAC-gated, audited."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.orchestrator import Orchestrator
from app.api import deps
from app.api.schemas import (
    ApprovalRequest,
    AssignRequest,
    AuditEntryResponse,
    AuditListResponse,
    HealthResponse,
    InvestigationList,
    LoginRequest,
    MitreCoverageResponse,
    NoteRequest,
    NoteResponse,
    RuleResponse,
    RuleToggleRequest,
    SearchRequest,
    SLAResponse,
    StatusRequest,
    TokenResponse,
)
from app.core.config import get_settings
from app.core.principal import Principal, issue_token
from app.core.rbac import Permission
from app.db.repositories import (
    CaseWorkflowMixin,
    IncidentRepository,
    InvestigationRepository,
    RuleStateRepository,
    TenantRepository,
    UserRepository,
)
from app.models.domain import Detection, Incident, Investigation, SearchResult
from app.services.audit import AuditService
from app.services.correlation import correlate
from app.services.executor import ActionExecutor
from app.services.metering import MeteringService
from app.services.notifications import NotificationService
from app.splunk.client import SplunkClient, SplunkError

router = APIRouter()


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT, tags=["auth"])
async def logout(
    principal: Principal = Depends(deps.get_principal),
    session: AsyncSession = Depends(deps.db_session),
    audit: AuditService = Depends(deps.get_audit),
) -> None:
    """Revoke the caller's current token server-side."""
    from app.db.repositories import TokenRepository

    if principal.jti is not None:
        await TokenRepository(session).revoke(principal.tenant_id, principal.jti)
    await audit.record(
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="auth.logout",
        target_type="user",
        target_id=principal.user_id,
    )


@router.get("/health", response_model=HealthResponse, tags=["system"])
async def health(splunk: SplunkClient = Depends(deps.get_splunk)) -> HealthResponse:
    settings = get_settings()
    ok = await splunk.health()
    return HealthResponse(
        status="ok" if ok else "degraded", splunk=ok, backend=settings.splunk_backend
    )


@router.get("/health/live", tags=["system"])
async def liveness() -> dict[str, str]:
    """Process is up. Used by orchestrators to decide restarts."""
    return {"status": "alive"}


@router.get("/health/ready", tags=["system"])
async def readiness(
    splunk: SplunkClient = Depends(deps.get_splunk),
    session: AsyncSession = Depends(deps.db_session),
) -> dict[str, object]:
    """Dependencies reachable. Used to gate traffic. 503 when not ready."""
    from sqlalchemy import text

    checks: dict[str, bool] = {}
    try:
        await session.execute(text("SELECT 1"))
        checks["database"] = True
    except Exception:
        checks["database"] = False
    checks["splunk"] = await splunk.health()
    ready = all(checks.values())
    if not ready:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"ready": False, "checks": checks},
        )
    return {"ready": True, "checks": checks}


@router.post("/auth/login", response_model=TokenResponse, tags=["auth"])
async def login(
    body: LoginRequest,
    session: AsyncSession = Depends(deps.db_session),
) -> TokenResponse:
    tenants = TenantRepository(session)
    users = UserRepository(session)
    audit = AuditService(session)
    tenant = await tenants.get_by_name(body.tenant)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if tenant.status == "suspended":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant is suspended")
    user = await users.authenticate(tenant.id, body.username, body.password)
    if not user:
        await audit.record(
            tenant_id=tenant.id,
            actor=body.username,
            action="auth.login.failed",
            target_type="user",
            target_id=body.username,
        )
        # Persist the audit record before the request unwinds with a 401.
        await session.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    principal = Principal(
        user_id=user.id, username=user.username, tenant_id=tenant.id, role=user.role
    )
    await audit.record(
        tenant_id=tenant.id,
        actor=user.username,
        action="auth.login.success",
        target_type="user",
        target_id=user.id,
    )
    return TokenResponse(
        access_token=issue_token(principal), role=user.role, tenant=tenant.name
    )


@router.post("/search", response_model=SearchResult, tags=["splunk"])
async def search(
    body: SearchRequest,
    principal: Principal = Depends(deps.require(Permission.SEARCH_RUN)),
    splunk: SplunkClient = Depends(deps.get_splunk),
) -> SearchResult:
    try:
        return await splunk.search(body.spl, body.earliest, body.latest)
    except SplunkError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/detections/run", response_model=list[Detection], tags=["agents"])
async def run_detections(
    principal: Principal = Depends(deps.require(Permission.DETECTION_RUN)),
    orch: Orchestrator = Depends(deps.get_tenant_orchestrator),
) -> list[Detection]:
    return await orch.run_detections()


@router.post("/investigations/run", response_model=InvestigationList, tags=["agents"])
async def run_investigations(
    principal: Principal = Depends(deps.require(Permission.INVESTIGATION_RUN)),
    orch: Orchestrator = Depends(deps.get_tenant_orchestrator),
    repo: InvestigationRepository = Depends(deps.get_investigation_repo),
    incident_repo: IncidentRepository = Depends(deps.get_incident_repo),
    audit: AuditService = Depends(deps.get_audit),
    notifier: NotificationService = Depends(deps.get_notifier),
    rules: RuleStateRepository = Depends(deps.get_rule_repo),
    metering: MeteringService = Depends(deps.get_metering),
    session: AsyncSession = Depends(deps.db_session),
) -> InvestigationList:
    from app.agents.detection_agent import DEFAULT_RULES
    from app.services.metering import KIND_MODEL_CALL, KIND_SEARCH
    from app.services.quotas import QuotaExceeded, QuotaService

    disabled = await rules.disabled_rule_ids(principal.tenant_id)
    enabled_rule_count = sum(1 for r in DEFAULT_RULES if r.rule_id not in disabled)
    # Enforce the tenant's monthly search quota BEFORE doing the work.
    tenant = await TenantRepository(session).get(principal.tenant_id)
    plan = tenant.plan if tenant else "free"
    try:
        await QuotaService(session).check_or_raise(
            principal.tenant_id, plan, KIND_SEARCH, want=enabled_rule_count
        )
    except QuotaExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "quota_exceeded", "kind": exc.kind,
                "used": exc.used, "limit": exc.limit,
                "message": "Monthly search quota exceeded. Upgrade plan to continue.",
            },
        ) from exc
    investigations = await orch.run_full_pipeline(disabled)
    # Meter the work performed: one SPL search per enabled detection rule, and
    # one model call per investigation triaged (best-effort; never fails the run).
    await metering.record(
        principal.tenant_id, KIND_SEARCH, quantity=enabled_rule_count, detail="detection run"
    )
    if investigations:
        await metering.record(
            principal.tenant_id, KIND_MODEL_CALL, quantity=len(investigations),
            detail="triage",
        )
    for inv in investigations:
        await repo.save(principal.tenant_id, inv)
        await audit.record(
            tenant_id=principal.tenant_id,
            actor=principal.username,
            action="investigation.created",
            target_type="investigation",
            target_id=inv.id,
            detail={"severity": inv.detection.severity.value, "title": inv.detection.title},
        )
    items, total = await repo.list(principal.tenant_id)
    # Correlate all of the tenant's investigations into incidents.
    incidents = correlate(items)
    for inc in incidents:
        inc.risk_score = _incident_risk(inc, items)
    await incident_repo.replace_all(principal.tenant_id, incidents)
    # Alert on high-risk incidents.
    for inc in incidents:
        await notifier.maybe_alert_high_risk(
            principal.tenant_id, inc.title, inc.severity.value, inc.risk_score
        )
    return InvestigationList(investigations=items, total=total, limit=len(items), offset=0)


def _incident_risk(incident: Incident, investigations: list[Investigation]) -> int:
    from app.db.repositories import _risk_from

    members = [i for i in investigations if i.id in incident.investigation_ids]
    return max((_risk_from(m) for m in members), default=0)


@router.get("/investigations", response_model=InvestigationList, tags=["investigations"])
async def list_investigations(
    principal: Principal = Depends(deps.require(Permission.INVESTIGATION_READ)),
    repo: InvestigationRepository = Depends(deps.get_investigation_repo),
    status_filter: str | None = Query(default=None, alias="status"),
    severity: str | None = Query(default=None),
    assignee: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> InvestigationList:
    items, total = await repo.list(
        principal.tenant_id,
        status=status_filter,
        severity=severity,
        assignee=assignee,
        limit=limit,
        offset=offset,
    )
    return InvestigationList(investigations=items, total=total, limit=limit, offset=offset)


@router.get(
    "/investigations/{investigation_id}",
    response_model=Investigation,
    tags=["investigations"],
)
async def get_investigation(
    investigation_id: str,
    principal: Principal = Depends(deps.require(Permission.INVESTIGATION_READ)),
    repo: InvestigationRepository = Depends(deps.get_investigation_repo),
) -> Investigation:
    inv = await repo.get(principal.tenant_id, investigation_id)
    if not inv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Investigation not found")
    return inv


@router.post(
    "/investigations/{investigation_id}/approve",
    response_model=Investigation,
    tags=["investigations"],
)
async def approve_action(
    investigation_id: str,
    body: ApprovalRequest,
    principal: Principal = Depends(deps.require(Permission.ACTION_APPROVE)),
    repo: InvestigationRepository = Depends(deps.get_investigation_repo),
    audit: AuditService = Depends(deps.get_audit),
) -> Investigation:
    inv = await repo.approve_action(principal.tenant_id, investigation_id, body.action_index)
    if not inv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Investigation or action not found",
        )
    await audit.record(
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="action.approved",
        target_type="investigation",
        target_id=investigation_id,
        detail={"action_index": body.action_index},
    )
    return inv


@router.post(
    "/investigations/{investigation_id}/execute",
    response_model=Investigation,
    tags=["investigations"],
)
async def execute_action(
    investigation_id: str,
    body: ApprovalRequest,
    principal: Principal = Depends(deps.require(Permission.ACTION_APPROVE)),
    repo: InvestigationRepository = Depends(deps.get_investigation_repo),
    audit: AuditService = Depends(deps.get_audit),
    executor: ActionExecutor = Depends(deps.get_executor),
    notifier: NotificationService = Depends(deps.get_notifier),
    metering: MeteringService = Depends(deps.get_metering),
) -> Investigation:
    inv, error = await repo.execute_action(
        principal.tenant_id, investigation_id, body.action_index, executor
    )
    if error == "not_approved":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Action must be approved before execution",
        )
    if error or inv is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Investigation or action not found",
        )
    executed = inv.actions[body.action_index]
    # Meter the executed response action (best-effort).
    from app.services.metering import KIND_ACTION

    await metering.record(
        principal.tenant_id, KIND_ACTION, quantity=1, detail=executed.action_type
    )
    await audit.record(
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="action.executed",
        target_type="investigation",
        target_id=investigation_id,
        detail={
            "action_index": body.action_index,
            "action_type": executed.action_type,
            "status": executed.execution_status,
        },
    )
    await notifier.alert_action_executed(
        principal.tenant_id,
        executed.action_type,
        executed.target,
        executed.execution_status or "unknown",
    )
    return inv


@router.post(
    "/investigations/{investigation_id}/status",
    response_model=Investigation,
    tags=["cases"],
)
async def transition_status(
    investigation_id: str,
    body: StatusRequest,
    principal: Principal = Depends(deps.require(Permission.CASE_WRITE)),
    workflow: CaseWorkflowMixin = Depends(deps.get_workflow),
    audit: AuditService = Depends(deps.get_audit),
) -> Investigation:
    inv, error = await workflow.transition_status(
        principal.tenant_id, investigation_id, body.status
    )
    if error == "illegal_transition":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Illegal status transition to '{body.status}'",
        )
    if error == "invalid_status":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown status '{body.status}'",
        )
    if error or inv is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Investigation not found")
    await audit.record(
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="case.status_changed",
        target_type="investigation",
        target_id=investigation_id,
        detail={"status": body.status},
    )
    return inv


@router.get(
    "/investigations/{investigation_id}/sla",
    response_model=SLAResponse,
    tags=["cases"],
)
async def get_sla(
    investigation_id: str,
    principal: Principal = Depends(deps.require(Permission.INVESTIGATION_READ)),
    workflow: CaseWorkflowMixin = Depends(deps.get_workflow),
) -> SLAResponse:
    sla = await workflow.sla(principal.tenant_id, investigation_id)
    if sla is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Investigation not found")
    return SLAResponse.model_validate(sla)


@router.post(
    "/investigations/{investigation_id}/assign",
    response_model=Investigation,
    tags=["cases"],
)
async def assign_investigation(
    investigation_id: str,
    body: AssignRequest,
    principal: Principal = Depends(deps.require(Permission.CASE_WRITE)),
    repo: InvestigationRepository = Depends(deps.get_investigation_repo),
    audit: AuditService = Depends(deps.get_audit),
) -> Investigation:
    inv = await repo.set_assignee(principal.tenant_id, investigation_id, body.assignee)
    if not inv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Investigation not found")
    await audit.record(
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="case.assigned",
        target_type="investigation",
        target_id=investigation_id,
        detail={"assignee": body.assignee},
    )
    return inv


@router.post(
    "/investigations/{investigation_id}/notes",
    response_model=NoteResponse,
    tags=["cases"],
)
async def add_note(
    investigation_id: str,
    body: NoteRequest,
    principal: Principal = Depends(deps.require(Permission.CASE_WRITE)),
    repo: InvestigationRepository = Depends(deps.get_investigation_repo),
    audit: AuditService = Depends(deps.get_audit),
) -> NoteResponse:
    note = await repo.add_note(
        principal.tenant_id, investigation_id, principal.username, body.body
    )
    if not note:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Investigation not found")
    await audit.record(
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="case.note_added",
        target_type="investigation",
        target_id=investigation_id,
    )
    return NoteResponse(
        id=note.id, author=note.author, body=note.body, created_at=note.created_at
    )


@router.get(
    "/investigations/{investigation_id}/notes",
    response_model=list[NoteResponse],
    tags=["cases"],
)
async def list_notes(
    investigation_id: str,
    principal: Principal = Depends(deps.require(Permission.INVESTIGATION_READ)),
    repo: InvestigationRepository = Depends(deps.get_investigation_repo),
) -> list[NoteResponse]:
    notes = await repo.list_notes(principal.tenant_id, investigation_id)
    return [
        NoteResponse(id=n.id, author=n.author, body=n.body, created_at=n.created_at)
        for n in notes
    ]


@router.get("/rules", response_model=list[RuleResponse], tags=["rules"])
async def list_rules(
    principal: Principal = Depends(deps.require(Permission.INVESTIGATION_READ)),
    rules: RuleStateRepository = Depends(deps.get_rule_repo),
) -> list[RuleResponse]:
    from app.agents.detection_agent import DEFAULT_RULES

    disabled = await rules.disabled_rule_ids(principal.tenant_id)
    return [
        RuleResponse(
            rule_id=r.rule_id,
            title=r.title,
            description=r.description,
            base_severity=r.base_severity.value,
            mitre_tactics=list(r.mitre_tactics),
            enabled=r.rule_id not in disabled,
        )
        for r in DEFAULT_RULES
    ]


@router.put("/rules/{rule_id}", response_model=RuleResponse, tags=["rules"])
async def toggle_rule(
    rule_id: str,
    body: RuleToggleRequest,
    principal: Principal = Depends(deps.require(Permission.ADMIN)),
    rules: RuleStateRepository = Depends(deps.get_rule_repo),
    audit: AuditService = Depends(deps.get_audit),
) -> RuleResponse:
    from app.agents.detection_agent import DEFAULT_RULES

    rule = next((r for r in DEFAULT_RULES if r.rule_id == rule_id), None)
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")
    await rules.set_enabled(principal.tenant_id, rule_id, body.enabled)
    await audit.record(
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="rule.toggled",
        target_type="rule",
        target_id=rule_id,
        detail={"enabled": body.enabled},
    )
    return RuleResponse(
        rule_id=rule.rule_id,
        title=rule.title,
        description=rule.description,
        base_severity=rule.base_severity.value,
        mitre_tactics=list(rule.mitre_tactics),
        enabled=body.enabled,
    )


@router.get("/rules/mitre-coverage", response_model=MitreCoverageResponse, tags=["rules"])
async def mitre_coverage(
    principal: Principal = Depends(deps.require(Permission.INVESTIGATION_READ)),
    rules: RuleStateRepository = Depends(deps.get_rule_repo),
) -> MitreCoverageResponse:
    from app.agents.detection_agent import DEFAULT_RULES

    disabled = await rules.disabled_rule_ids(principal.tenant_id)
    coverage: dict[str, int] = {}
    enabled_count = 0
    for r in DEFAULT_RULES:
        if r.rule_id in disabled:
            continue
        enabled_count += 1
        for tactic in r.mitre_tactics:
            coverage[tactic] = coverage.get(tactic, 0) + 1
    return MitreCoverageResponse(
        coverage=coverage, total_rules=len(DEFAULT_RULES), enabled_rules=enabled_count
    )


@router.get("/ai/models", tags=["agents"])
async def ai_models(
    principal: Principal = Depends(deps.require(Permission.INVESTIGATION_READ)),
) -> dict[str, object]:
    """Splunk hosted-model catalog and task routing.

    Shows which Splunk-hosted model each agent task is routed to, so the
    "right model for the job" design is inspectable: Foundation-Sec for security
    triage, gpt-oss for summaries, Cisco Deep Time Series for anomaly scoring.
    """
    from app.core.config import get_settings as _gs
    from app.services.hosted_models import DEFAULT_MODEL_FOR_TASK, catalog

    settings = _gs()
    return {
        "ai_backend": settings.ai_backend,
        "active_triage_model": settings.ai_model,
        "task_routing": {t.value: m for t, m in DEFAULT_MODEL_FOR_TASK.items()},
        "catalog": catalog(),
    }


@router.get("/notifications", tags=["system"])
async def list_notifications(
    principal: Principal = Depends(deps.require(Permission.INVESTIGATION_READ)),
    notifier: NotificationService = Depends(deps.get_notifier),
) -> dict[str, object]:
    """Inspect captured notifications for this tenant (capture channel only)."""
    from app.services.notifications import CaptureChannel

    captured: list[dict[str, object]] = []
    for channel in notifier._channels:  # noqa: SLF001 - internal inspection endpoint
        if isinstance(channel, CaptureChannel):
            captured = [
                {
                    "event": n.event,
                    "title": n.title,
                    "severity": n.severity,
                    "body": n.body,
                    "created_at": n.created_at.isoformat(),
                }
                for n in channel.sent
                if n.tenant_id == principal.tenant_id
            ]
    return {"notifications": captured, "count": len(captured)}


@router.get("/incidents", response_model=list[Incident], tags=["incidents"])
async def list_incidents(
    principal: Principal = Depends(deps.require(Permission.INVESTIGATION_READ)),
    incident_repo: IncidentRepository = Depends(deps.get_incident_repo),
) -> list[Incident]:
    return await incident_repo.list(principal.tenant_id)


@router.get("/incidents/{incident_id}", response_model=Incident, tags=["incidents"])
async def get_incident(
    incident_id: str,
    principal: Principal = Depends(deps.require(Permission.INVESTIGATION_READ)),
    incident_repo: IncidentRepository = Depends(deps.get_incident_repo),
) -> Incident:
    inc = await incident_repo.get(principal.tenant_id, incident_id)
    if not inc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")
    return inc


@router.get("/audit", response_model=AuditListResponse, tags=["audit"])
async def list_audit(
    principal: Principal = Depends(deps.require(Permission.AUDIT_READ)),
    audit: AuditService = Depends(deps.get_audit),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> AuditListResponse:
    entries = await audit.list(principal.tenant_id, limit=limit, offset=offset)
    chain_valid = await audit.verify_chain(principal.tenant_id)
    return AuditListResponse(
        entries=[
            AuditEntryResponse(
                id=e.id,
                actor=e.actor,
                action=e.action,
                target_type=e.target_type,
                target_id=e.target_id,
                detail=e.detail,
                entry_hash=e.entry_hash,
                created_at=e.created_at,
            )
            for e in entries
        ],
        chain_valid=chain_valid,
    )
