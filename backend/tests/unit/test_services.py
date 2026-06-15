"""Unit tests for service-layer logic (no HTTP, mostly no DB)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.core.rbac import Permission, has_permission, permissions_for
from app.core.resilience import CircuitBreaker, CircuitOpenError, with_retry
from app.models.domain import (
    Detection,
    DetectionStatus,
    Incident,
    Investigation,
    Severity,
    TriageVerdict,
)
from app.services.correlation import correlate
from app.services.enrichment import EnrichmentService, MockEnrichmentProvider
from app.services.executor import ActionExecutor, MockConnector
from app.services.workflow import can_transition, compute_sla


class TestRBAC:
    def test_admin_has_all(self):
        assert has_permission("admin", Permission.AUDIT_READ)
        assert has_permission("admin", Permission.ADMIN)

    def test_viewer_limited(self):
        assert has_permission("viewer", Permission.INVESTIGATION_READ)
        assert not has_permission("viewer", Permission.INVESTIGATION_RUN)

    def test_responder_can_approve(self):
        assert has_permission("responder", Permission.ACTION_APPROVE)

    def test_analyst_cannot_approve(self):
        assert not has_permission("analyst", Permission.ACTION_APPROVE)

    def test_unknown_role_no_perms(self):
        assert permissions_for("nonsense") == set()


class TestResilience:
    async def test_retry_recovers(self):
        calls = {"n": 0}

        async def flaky():
            calls["n"] += 1
            if calls["n"] < 3:
                raise RuntimeError("transient")
            return "ok"

        assert await with_retry(flaky, attempts=3, base_delay=0.0) == "ok"

    async def test_retry_exhausts(self):
        async def always_fail():
            raise RuntimeError("down")

        with pytest.raises(RuntimeError):
            await with_retry(always_fail, attempts=2, base_delay=0.0)

    async def test_dont_retry(self):
        calls = {"n": 0}

        async def fail_validation():
            calls["n"] += 1
            raise ValueError("bad input")

        with pytest.raises(ValueError):
            await with_retry(
                fail_validation, attempts=3, base_delay=0.0, dont_retry=(ValueError,)
            )
        assert calls["n"] == 1

    async def test_breaker_opens(self):
        breaker = CircuitBreaker(failure_threshold=2, reset_after_seconds=999)

        async def always_fail():
            raise RuntimeError("down")

        for _ in range(2):
            with pytest.raises(RuntimeError):
                await with_retry(always_fail, attempts=1, base_delay=0.0, breaker=breaker)
        with pytest.raises(CircuitOpenError):
            await with_retry(always_fail, attempts=1, base_delay=0.0, breaker=breaker)

    def test_breaker_half_open_after_reset(self):
        breaker = CircuitBreaker(failure_threshold=1, reset_after_seconds=0.0)
        breaker.record_failure()
        # reset_after 0 => immediately half-open (not open).
        assert breaker.is_open is False

    def test_breaker_recovers_on_success(self):
        breaker = CircuitBreaker(failure_threshold=1)
        breaker.record_failure()
        breaker.record_success()
        assert breaker.is_open is False


class TestWorkflow:
    def test_legal_transition(self):
        assert can_transition(DetectionStatus.INVESTIGATING, DetectionStatus.CONTAINED)

    def test_illegal_transition(self):
        assert not can_transition(DetectionStatus.CONTAINED, DetectionStatus.NEW)

    def test_sla_not_breached_fresh(self):
        now = datetime.now(timezone.utc)
        sla = compute_sla(now, None, None, now=now)
        assert sla["ack_breached"] is False
        assert sla["contain_breached"] is False

    def test_sla_breached_when_overdue(self):
        created = datetime.now(timezone.utc) - timedelta(hours=3)
        sla = compute_sla(created, None, None)
        assert sla["ack_breached"] is True
        assert sla["contain_breached"] is True

    def test_sla_handles_naive_datetime(self):
        created = datetime.now()  # naive
        sla = compute_sla(created, None, None)
        assert "ack_elapsed_min" in sla


class TestEnrichment:
    async def test_malicious_ip_flagged(self):
        svc = EnrichmentService(MockEnrichmentProvider())
        e = await svc.enrich(host="web-prod-01", user="admin", ips=["203.0.113.5"])
        assert e.threat_intel["verdict"] == "malicious"
        assert "203.0.113.5" in e.indicators
        assert e.boost() > 1.0

    async def test_crown_jewel_boost(self):
        svc = EnrichmentService(MockEnrichmentProvider())
        e = await svc.enrich(host="db-prod-02", user=None, ips=[])
        assert e.asset_criticality == "crown_jewel"

    async def test_benign(self):
        svc = EnrichmentService(MockEnrichmentProvider())
        e = await svc.enrich(host="random-host", user="joe", ips=["10.0.0.1"])
        assert e.threat_intel.get("verdict") == "benign"


class TestExecutor:
    async def test_supported_action(self):
        ex = ActionExecutor([MockConnector()])
        result = await ex.execute("isolate_host", "web-prod-01")
        assert result.status == "success"
        assert result.rollback_token

    async def test_unsupported_action(self):
        ex = ActionExecutor([MockConnector()])
        result = await ex.execute("launch_missile", "x")
        assert result.status == "unsupported"


class TestCorrelation:
    def _inv(self, inv_id, entity, ips, severity=Severity.HIGH):
        det = Detection(
            id=f"DET-{inv_id}",
            title=f"t-{inv_id}",
            description="d",
            severity=severity,
            spl_query="search x",
            entity=entity,
            src_ips=ips,
        )
        return Investigation(id=inv_id, detection=det)

    def test_groups_by_entity(self):
        invs = [
            self._inv("I1", "host-a", []),
            self._inv("I2", "host-a", []),
            self._inv("I3", "host-b", []),
        ]
        incidents = correlate(invs)
        assert len(incidents) == 2

    def test_groups_by_indicator(self):
        invs = [
            self._inv("I1", "host-a", ["1.2.3.4"]),
            self._inv("I2", "host-b", ["1.2.3.4"]),
        ]
        incidents = correlate(invs)
        assert len(incidents) == 1
        assert incidents[0].investigation_ids == ["I1", "I2"]

    def test_severity_rolls_up(self):
        invs = [
            self._inv("I1", "host-a", [], Severity.LOW),
            self._inv("I2", "host-a", [], Severity.CRITICAL),
        ]
        incidents = correlate(invs)
        assert incidents[0].severity == Severity.CRITICAL
