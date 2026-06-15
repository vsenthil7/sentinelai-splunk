"""Unit tests for agents, security, clients, and the audit hash chain."""
from __future__ import annotations

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.agents.detection_agent import DEFAULT_RULES, DetectionAgent, DetectionRule
from app.agents.orchestrator import Orchestrator
from app.agents.response_agent import ResponseAgent
from app.agents.triage_agent import TriageAgent
from app.core.security import (
    AuthError,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.db.models import Base
from app.models.domain import Detection, Severity, TriageVerdict
from app.services.ai_model import AIModel, LiveAIModel, MockAIModel
from app.services.audit import AuditService
from app.splunk.client import SplunkQueryError
from app.splunk.live_client import LiveSplunkClient
from app.splunk.mock_client import MockSplunkClient


class TestSecurity:
    def test_hash_verify(self):
        h = hash_password("secret")
        assert verify_password("secret", h)
        assert not verify_password("wrong", h)

    def test_long_password(self):
        pw = "a" * 200
        assert verify_password(pw, hash_password(pw))

    def test_bad_hash(self):
        assert verify_password("x", "not-a-hash") is False

    def test_token_roundtrip(self):
        token = create_access_token("alice", {"tenant_id": "t1", "role": "admin"})
        payload = decode_access_token(token)
        assert payload["sub"] == "alice"
        assert payload["tenant_id"] == "t1"

    def test_bad_token(self):
        with pytest.raises(AuthError):
            decode_access_token("garbage")


class TestDetectionAgent:
    async def test_runs_rules(self):
        agent = DetectionAgent(MockSplunkClient())
        detections = await agent.run()
        assert len(detections) == 5

    async def test_skips_disabled(self):
        agent = DetectionAgent(MockSplunkClient())
        detections = await agent.run(disabled_rule_ids={"R001", "R002"})
        ids_titles = {d.title for d in detections}
        assert "Brute-force authentication" not in ids_titles

    async def test_entity_extraction(self):
        agent = DetectionAgent(MockSplunkClient())
        detections = await agent.run()
        brute = next(d for d in detections if "Brute" in d.title)
        assert brute.src_ips  # IPs extracted from events

    async def test_min_events_filter(self):
        rule = DetectionRule(
            rule_id="X", title="t", description="d",
            spl="search index=auth failed", base_severity=Severity.LOW,
            mitre_tactics=("TA0006",), min_events=1000,
        )
        agent = DetectionAgent(MockSplunkClient(), rules=(rule,))
        assert await agent.run() == []

    def test_default_rules(self):
        assert len(DEFAULT_RULES) == 5


class TestTriageAgent:
    async def test_true_positive(self):
        agent = TriageAgent(MockAIModel())
        det = Detection(
            id="D1", title="Brute", description="failed authentication",
            severity=Severity.HIGH, spl_query="search x", entity="h", event_count=12,
        )
        verdict = await agent.triage(det)
        assert verdict.is_true_positive

    async def test_malformed_model_fallback(self):
        class BadModel(AIModel):
            async def complete(self, system, user):
                return "not json"

        agent = TriageAgent(BadModel())
        det = Detection(
            id="D1", title="t", description="d", severity=Severity.MEDIUM,
            spl_query="search x", entity="h",
        )
        verdict = await agent.triage(det)
        assert verdict.confidence == 0.5


class TestResponseAgent:
    def test_no_actions_for_fp(self):
        det = Detection(
            id="D1", title="t", description="d", severity=Severity.LOW,
            spl_query="search x", entity="h",
        )
        verdict = TriageVerdict(
            detection_id="D1", is_true_positive=False, confidence=0.2,
            rationale="benign", recommended_severity=Severity.LOW,
            suggested_actions=["monitor"],
        )
        assert ResponseAgent().plan(det, verdict) == []

    def test_gated_actions(self):
        det = Detection(
            id="D1", title="t", description="d", severity=Severity.HIGH,
            spl_query="search x", entity="h",
        )
        verdict = TriageVerdict(
            detection_id="D1", is_true_positive=True, confidence=0.9,
            rationale="bad", recommended_severity=Severity.HIGH,
            suggested_actions=["isolate_host", "collect_forensics"],
        )
        actions = ResponseAgent().plan(det, verdict)
        isolate = next(a for a in actions if a.action_type == "isolate_host")
        assert isolate.requires_approval is True


class TestOrchestrator:
    async def test_full_pipeline(self):
        orch = Orchestrator(MockSplunkClient(), MockAIModel())
        invs = await orch.run_full_pipeline()
        assert len(invs) == 5
        assert all(i.verdict is not None for i in invs)

    async def test_pipeline_respects_disabled(self):
        orch = Orchestrator(MockSplunkClient(), MockAIModel())
        invs = await orch.run_full_pipeline(disabled_rule_ids={"R001", "R002", "R003"})
        assert len(invs) == 2


class TestMockSplunk:
    async def test_malformed_raises(self):
        with pytest.raises(SplunkQueryError):
            await MockSplunkClient().search("garbage")

    async def test_health(self):
        c = MockSplunkClient()
        assert await c.health() is True
        c.set_healthy(False)
        assert await c.health() is False


class TestLiveClients:
    def test_live_splunk_requires_host(self):
        from app.splunk.client import SplunkConnectionError

        with pytest.raises(SplunkConnectionError):
            LiveSplunkClient(host="", token="t")

    async def test_live_ai_error_status(self, monkeypatch):
        from app.services.ai_model import AIModelError

        m = LiveAIModel(base_url="https://x", model="m")

        class FakeResp:
            status_code = 500
            text = "err"

        class FakeClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def post(self, *a, **k):
                return FakeResp()

        monkeypatch.setattr(httpx, "AsyncClient", lambda **k: FakeClient())
        with pytest.raises(AIModelError):
            await m.complete("s", "u")


class TestAuditChain:
    async def _session(self):
        eng = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        async with eng.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        return async_sessionmaker(bind=eng, expire_on_commit=False)

    async def test_chain_valid(self):
        maker = await self._session()
        async with maker() as s:
            audit = AuditService(s)
            for i in range(3):
                await audit.record(
                    tenant_id="t1", actor="a", action="x", target_type="y", target_id=str(i)
                )
            await s.commit()
            assert await audit.verify_chain("t1") is True

    async def test_chain_detects_tamper(self):
        from sqlalchemy import update

        from app.db.models import AuditLogRow

        maker = await self._session()
        async with maker() as s:
            audit = AuditService(s)
            for i in range(3):
                await audit.record(
                    tenant_id="t1", actor="a", action="x", target_type="y", target_id=str(i)
                )
            await s.commit()
            await s.execute(
                update(AuditLogRow).where(AuditLogRow.target_id == "1").values(actor="evil")
            )
            await s.commit()
            assert await audit.verify_chain("t1") is False
