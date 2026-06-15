"""Direct repository tests against an in-memory database."""
from __future__ import annotations

import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.models import Base
from app.db.repositories import (
    CaseWorkflowMixin,
    IncidentRepository,
    InvestigationRepository,
    RuleStateRepository,
    TenantRepository,
    UserRepository,
    _risk_from,
)
from app.models.domain import (
    Detection,
    DetectionStatus,
    Incident,
    Investigation,
    Severity,
    TriageVerdict,
)


@pytest_asyncio.fixture
async def sm():
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(bind=eng, expire_on_commit=False)
    await eng.dispose()


def _inv(inv_id="INV-1", entity="host-a", tp=True, sev=Severity.HIGH):
    det = Detection(
        id=f"DET-{inv_id}", title="Brute force", description="failed auth",
        severity=sev, status=DetectionStatus.INVESTIGATING, spl_query="search x",
        entity=entity, event_count=12, src_ips=["1.2.3.4"],
        enrichment={"risk_boost": 1.2, "asset_criticality": "high"},
    )
    verdict = TriageVerdict(
        detection_id=det.id, is_true_positive=tp, confidence=0.9,
        rationale="r", recommended_severity=sev, suggested_actions=["isolate_host"],
    )
    from app.models.domain import IncidentAction

    return Investigation(
        id=inv_id, detection=det, verdict=verdict,
        actions=[IncidentAction(action_type="isolate_host", target=entity, rationale="r")],
        summary="s",
    )


class TestTenantUserRepo:
    async def test_tenant_ensure_idempotent(self, sm):
        async with sm() as s:
            r = TenantRepository(s)
            t1 = await r.ensure("acme")
            t2 = await r.ensure("acme")
            assert t1.id == t2.id

    async def test_user_crud(self, sm):
        async with sm() as s:
            t = await TenantRepository(s).ensure("acme")
            ur = UserRepository(s)
            u = await ur.create(t.id, "bob", "pw", role="analyst")
            assert await ur.authenticate(t.id, "bob", "pw") is not None
            assert await ur.authenticate(t.id, "bob", "bad") is None
            assert (await ur.set_role(t.id, u.id, "admin")).role == "admin"
            assert await ur.set_role(t.id, "missing", "admin") is None
            await ur.link_external_id(t.id, u.id, "okta|1")
            assert (await ur.get_by_external_id(t.id, "okta|1")).username == "bob"
            assert await ur.delete(t.id, u.id) is True
            assert await ur.delete(t.id, u.id) is False

    async def test_user_list(self, sm):
        async with sm() as s:
            t = await TenantRepository(s).ensure("acme")
            ur = UserRepository(s)
            await ur.create(t.id, "a", "pw")
            await ur.create(t.id, "b", "pw")
            assert len(await ur.list(t.id)) == 2

    async def test_tenant_saas_fields_defaults(self, sm):
        async with sm() as s:
            t = await TenantRepository(s).ensure("acme")
            assert t.status == "active"
            assert t.plan == "enterprise"
            assert t.settings == {}

    async def test_tenant_status_plan_settings(self, sm):
        async with sm() as s:
            r = TenantRepository(s)
            t = await r.create("beta", status="trial", plan="free")
            assert t.status == "trial" and t.plan == "free"
            assert (await r.set_status(t.id, "suspended")).status == "suspended"
            assert (await r.set_plan(t.id, "pro")).plan == "pro"
            updated = await r.update_settings(t.id, {"theme": "dark"})
            assert updated.settings["theme"] == "dark"
            # merge keeps prior keys
            updated2 = await r.update_settings(t.id, {"tz": "UTC"})
            assert updated2.settings["theme"] == "dark" and updated2.settings["tz"] == "UTC"
            # missing tenant
            assert await r.set_status("missing", "active") is None
            assert await r.set_plan("missing", "pro") is None
            assert await r.update_settings("missing", {}) is None

    async def test_tenant_list_all(self, sm):
        async with sm() as s:
            r = TenantRepository(s)
            await r.create("t1")
            await r.create("t2")
            assert len(await r.list()) == 2


class TestInvestigationRepo:
    async def test_save_get_list(self, sm):
        async with sm() as s:
            t = await TenantRepository(s).ensure("acme")
            repo = InvestigationRepository(s)
            await repo.save(t.id, _inv("INV-1"))
            await repo.save(t.id, _inv("INV-2", entity="host-b"))
            got = await repo.get(t.id, "INV-1")
            assert got.id == "INV-1"
            items, total = await repo.list(t.id)
            assert total == 2

    async def test_save_update(self, sm):
        async with sm() as s:
            t = await TenantRepository(s).ensure("acme")
            repo = InvestigationRepository(s)
            await repo.save(t.id, _inv("INV-1"))
            inv = _inv("INV-1")
            inv.summary = "updated"
            await repo.save(t.id, inv)
            items, total = await repo.list(t.id)
            assert total == 1
            assert items[0].summary == "updated"

    async def test_filters(self, sm):
        async with sm() as s:
            t = await TenantRepository(s).ensure("acme")
            repo = InvestigationRepository(s)
            await repo.save(t.id, _inv("INV-1", sev=Severity.CRITICAL))
            await repo.save(t.id, _inv("INV-2", sev=Severity.LOW))
            crit, n = await repo.list(t.id, severity="critical")
            assert n == 1

    async def test_assign_and_approve_and_execute(self, sm):
        from app.services.executor import ActionExecutor, MockConnector

        async with sm() as s:
            t = await TenantRepository(s).ensure("acme")
            repo = InvestigationRepository(s)
            await repo.save(t.id, _inv("INV-1"))
            assert (await repo.set_assignee(t.id, "INV-1", "bob")).assignee == "bob"
            assert await repo.set_assignee(t.id, "missing", "bob") is None
            # execute before approve -> not_approved
            inv, err = await repo.execute_action(
                t.id, "INV-1", 0, ActionExecutor([MockConnector()])
            )
            assert err == "not_approved"
            await repo.approve_action(t.id, "INV-1", 0)
            inv, err = await repo.execute_action(
                t.id, "INV-1", 0, ActionExecutor([MockConnector()])
            )
            assert err is None
            assert inv.actions[0].executed is True

    async def test_approve_bounds(self, sm):
        async with sm() as s:
            t = await TenantRepository(s).ensure("acme")
            repo = InvestigationRepository(s)
            await repo.save(t.id, _inv("INV-1"))
            assert await repo.approve_action(t.id, "INV-1", 99) is None
            assert await repo.approve_action(t.id, "missing", 0) is None

    async def test_notes(self, sm):
        async with sm() as s:
            t = await TenantRepository(s).ensure("acme")
            repo = InvestigationRepository(s)
            await repo.save(t.id, _inv("INV-1"))
            note = await repo.add_note(t.id, "INV-1", "bob", "hello")
            assert note is not None
            assert await repo.add_note(t.id, "missing", "bob", "x") is None
            notes = await repo.list_notes(t.id, "INV-1")
            assert len(notes) == 1


class TestWorkflowRepo:
    async def test_transition_and_sla(self, sm):
        async with sm() as s:
            t = await TenantRepository(s).ensure("acme")
            await InvestigationRepository(s).save(t.id, _inv("INV-1"))
            wf = CaseWorkflowMixin(s)
            inv, err = await wf.transition_status(t.id, "INV-1", "contained")
            assert err is None
            assert inv.detection.status == "contained"
            # illegal
            _, err2 = await wf.transition_status(t.id, "INV-1", "new")
            assert err2 == "illegal_transition"
            # invalid
            _, err3 = await wf.transition_status(t.id, "INV-1", "bogus")
            assert err3 == "invalid_status"
            # missing
            _, err4 = await wf.transition_status(t.id, "missing", "contained")
            assert err4 == "not_found"
            sla = await wf.sla(t.id, "INV-1")
            assert sla is not None
            assert await wf.sla(t.id, "missing") is None


class TestIncidentRepo:
    async def test_replace_and_list(self, sm):
        async with sm() as s:
            t = await TenantRepository(s).ensure("acme")
            repo = IncidentRepository(s)
            inc = Incident(
                id="INC-1", title="t", entity="host-a", severity=Severity.HIGH,
                risk_score=80, investigation_ids=["INV-1"],
            )
            await repo.replace_all(t.id, [inc])
            assert len(await repo.list(t.id)) == 1
            assert (await repo.get(t.id, "INC-1")).id == "INC-1"
            # replace clears prior
            await repo.replace_all(t.id, [])
            assert len(await repo.list(t.id)) == 0
            assert await repo.get(t.id, "INC-1") is None


class TestRuleStateRepo:
    async def test_disable_enable(self, sm):
        async with sm() as s:
            t = await TenantRepository(s).ensure("acme")
            repo = RuleStateRepository(s)
            assert await repo.disabled_rule_ids(t.id) == set()
            await repo.set_enabled(t.id, "R001", False)
            assert "R001" in await repo.disabled_rule_ids(t.id)
            await repo.set_enabled(t.id, "R001", True)
            assert "R001" not in await repo.disabled_rule_ids(t.id)


class TestRiskScoring:
    def test_true_positive_scored(self, sm):
        inv = _inv(tp=True, sev=Severity.HIGH)
        assert _risk_from(inv) > 50

    def test_false_positive_low(self):
        inv = _inv(tp=False, sev=Severity.HIGH)
        assert _risk_from(inv) < 30
