"""Tests for infrastructure boundaries and remaining branches."""
from __future__ import annotations

import httpx
import pytest

from app.services.notifications import (
    CaptureChannel,
    Notification,
    NotificationService,
    WebhookChannel,
)


class TestNotifications:
    async def test_capture_channel(self):
        ch = CaptureChannel()
        n = Notification(event="e", title="t", severity="high", body="b", tenant_id="t1")
        assert await ch.send(n) is True
        assert len(ch.sent) == 1

    async def test_webhook_success(self, monkeypatch):
        class FakeResp:
            status_code = 200

        class FakeClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def post(self, *a, **k):
                return FakeResp()

        monkeypatch.setattr(httpx, "AsyncClient", lambda **k: FakeClient())
        ch = WebhookChannel("https://hooks.example.com/x")
        n = Notification(event="e", title="t", severity="high", body="b", tenant_id="t1")
        assert await ch.send(n) is True

    async def test_webhook_failure_status(self, monkeypatch):
        class FakeResp:
            status_code = 500

        class FakeClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def post(self, *a, **k):
                return FakeResp()

        monkeypatch.setattr(httpx, "AsyncClient", lambda **k: FakeClient())
        ch = WebhookChannel("https://hooks.example.com/x")
        n = Notification(event="e", title="t", severity="high", body="b", tenant_id="t1")
        assert await ch.send(n) is False

    async def test_service_threshold(self):
        cap = CaptureChannel()
        svc = NotificationService([cap], high_risk_threshold=80)
        # Below threshold -> no alert.
        assert await svc.maybe_alert_high_risk("t1", "x", "low", 50) == 0
        # At/above -> alert.
        assert await svc.maybe_alert_high_risk("t1", "x", "critical", 95) == 1

    async def test_service_action_alert(self):
        cap = CaptureChannel()
        svc = NotificationService([cap])
        assert await svc.alert_action_executed("t1", "isolate_host", "h", "success") == 1


class TestLiveSplunkSuccess:
    async def test_search_parses(self, monkeypatch):
        from app.splunk.live_client import LiveSplunkClient

        c = LiveSplunkClient(host="https://x:8089", token="t")

        async def fake_post(payload):
            return {
                "sid": "live-1",
                "results": [
                    {"_raw": "e", "source": "s", "sourcetype": "st", "host": "h",
                     "_time": "2026-06-08T10:00:00Z", "user": "bob"}
                ],
            }

        monkeypatch.setattr(c, "_post_search", fake_post)
        result = await c.search("search index=x")
        assert result.event_count == 1
        assert result.events[0].fields["user"] == "bob"

    async def test_health_ok(self, monkeypatch):
        from app.splunk.live_client import LiveSplunkClient

        c = LiveSplunkClient(host="https://x:8089", token="t")

        class FakeResp:
            status_code = 200

        class FakeClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def get(self, *a, **k):
                return FakeResp()

        monkeypatch.setattr(httpx, "AsyncClient", lambda **k: FakeClient())
        assert await c.health() is True

    async def test_post_search_auth_error(self, monkeypatch):
        from app.splunk.client import SplunkAuthError
        from app.splunk.live_client import LiveSplunkClient

        c = LiveSplunkClient(host="https://x:8089", token="t")

        class FakeResp:
            status_code = 401
            text = "no"

        class FakeClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def post(self, *a, **k):
                return FakeResp()

        monkeypatch.setattr(httpx, "AsyncClient", lambda **k: FakeClient())
        with pytest.raises(SplunkAuthError):
            await c.search("search x")


class TestLiveAISuccess:
    async def test_complete(self, monkeypatch):
        from app.services.ai_model import LiveAIModel

        m = LiveAIModel(base_url="https://x", model="m", token="t")

        class FakeResp:
            status_code = 200

            def json(self):
                return {"choices": [{"message": {"content": "hi"}}]}

        class FakeClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def post(self, *a, **k):
                return FakeResp()

        monkeypatch.setattr(httpx, "AsyncClient", lambda **k: FakeClient())
        assert await m.complete("s", "u") == "hi"


class TestFactories:
    def test_splunk_live_factory(self):
        from app.core.config import Settings
        from app.splunk.factory import build_splunk_client
        from app.splunk.live_client import LiveSplunkClient

        c = build_splunk_client(
            Settings(splunk_backend="live", splunk_host="https://x", splunk_token="t")
        )
        assert isinstance(c, LiveSplunkClient)

    def test_splunk_mcp_factory(self):
        from app.core.config import Settings
        from app.splunk.factory import build_splunk_client
        from app.splunk.mcp_client import McpSplunkClient

        c = build_splunk_client(
            Settings(
                splunk_backend="mcp",
                splunk_mcp_url="https://x/mcp",
                splunk_token="t",
            )
        )
        assert isinstance(c, McpSplunkClient)

    def test_ai_live_factory(self):
        from app.core.config import Settings
        from app.services.ai_factory import build_ai_model
        from app.services.ai_model import LiveAIModel

        m = build_ai_model(Settings(ai_backend="live", splunk_host="https://x", ai_model="m"))
        assert isinstance(m, LiveAIModel)


class TestBootstrapAndSession:
    async def test_init_skipped_when_create_all_false(self, monkeypatch):
        from app.core.config import get_settings
        from app.db.bootstrap import init_db

        monkeypatch.setenv("SENTINEL_DB_CREATE_ALL", "false")
        get_settings.cache_clear()
        # Should be a no-op and not raise even with no engine configured for it.
        await init_db()
        get_settings.cache_clear()

    async def test_init_and_seed(self, monkeypatch, tmp_path):
        # Point at a fresh file DB and exercise real bootstrap + session.
        db = tmp_path / "boot.db"
        monkeypatch.setenv("SENTINEL_DATABASE_URL", f"sqlite+aiosqlite:///{db}")
        from app.core.config import get_settings
        from app.db import session as session_mod

        get_settings.cache_clear()
        await session_mod.reset_engine()
        from app.db.bootstrap import DEFAULT_TENANT, init_db, seed_default

        await init_db()
        await seed_default()
        await seed_default()  # idempotent second call
        # Use the real get_session dependency generator.
        gen = session_mod.get_session()
        s = await gen.__anext__()
        from app.db.repositories import TenantRepository

        assert await TenantRepository(s).get_by_name(DEFAULT_TENANT) is not None
        await gen.aclose()
        await session_mod.reset_engine()
        get_settings.cache_clear()


class TestPrincipalEdge:
    def test_missing_claims(self):
        from app.core.principal import TokenClaimsError, principal_from_token
        from app.core.security import create_access_token

        # Token with no tenant/role/uid claims.
        token = create_access_token("alice")
        with pytest.raises(TokenClaimsError):
            principal_from_token(token)


class TestAgentBranches:
    async def test_triage_clamp_and_coerce(self):
        from app.agents.triage_agent import TriageAgent
        from app.models.domain import Detection, Severity
        from app.services.ai_model import AIModel

        class WeirdModel(AIModel):
            async def complete(self, system, user):
                return (
                    '{"is_true_positive": true, "confidence": 9.0, '
                    '"rationale": "x", "recommended_severity": "nonsense", '
                    '"suggested_actions": ["isolate_host"]}'
                )

        det = Detection(
            id="D1", title="t", description="d", severity=Severity.HIGH,
            spl_query="search x", entity="h",
        )
        verdict = await TriageAgent(WeirdModel()).triage(det)
        assert verdict.confidence == 1.0
        assert verdict.recommended_severity == Severity.MEDIUM

    def test_response_block_ip_target(self):
        from app.agents.response_agent import ResponseAgent
        from app.models.domain import Detection, Severity, TriageVerdict

        det = Detection(
            id="D1", title="t", description="d", severity=Severity.HIGH,
            spl_query="search x", entity="host-a",
        )
        verdict = TriageVerdict(
            detection_id="D1", is_true_positive=True, confidence=0.9, rationale="r",
            recommended_severity=Severity.HIGH, suggested_actions=["block_ip"],
        )
        actions = ResponseAgent().plan(det, verdict)
        assert actions[0].action_type == "block_ip"


def _mcp_stub(monkeypatch, *, status=200, payload=None, raise_connect=False):
    """Install a fake httpx.AsyncClient that returns a canned MCP JSON-RPC response."""

    class FakeResp:
        status_code = status
        text = "error-body"

        def json(self):
            return payload or {}

        def raise_for_status(self):
            if self.status_code >= 400:
                raise httpx.HTTPStatusError("err", request=None, response=None)

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            if raise_connect:
                raise httpx.ConnectError("unreachable")
            return FakeResp()

    monkeypatch.setattr(httpx, "AsyncClient", lambda **k: FakeClient())


class TestMcpSplunkClient:
    def _client(self):
        from app.splunk.mcp_client import McpSplunkClient

        return McpSplunkClient(url="https://x/mcp", token="t")

    def test_requires_url_and_token(self):
        from app.splunk.client import SplunkAuthError, SplunkConnectionError
        from app.splunk.mcp_client import McpSplunkClient

        with pytest.raises(SplunkConnectionError):
            McpSplunkClient(url="", token="t")
        with pytest.raises(SplunkAuthError):
            McpSplunkClient(url="https://x/mcp", token="")

    async def test_search_structured_content(self, monkeypatch):
        payload = {
            "result": {
                "sid": "mcp-1",
                "structuredContent": {
                    "results": [
                        {"_raw": "e", "source": "s", "sourcetype": "st",
                         "host": "h", "_time": "2026-06-08T10:00:00Z", "user": "bob"}
                    ]
                },
            }
        }
        _mcp_stub(monkeypatch, payload=payload)
        result = await self._client().search("index=x")
        assert result.event_count == 1
        assert result.sid == "mcp-1"
        assert result.events[0].fields["user"] == "bob"

    async def test_search_text_block_list(self, monkeypatch):
        import json as _json

        rows = [{"_raw": "e", "host": "h", "_time": "not-a-time"}]
        payload = {"result": {"content": [{"type": "text", "text": _json.dumps(rows)}]}}
        _mcp_stub(monkeypatch, payload=payload)
        result = await self._client().search("search index=x")
        assert result.event_count == 1
        # Unparseable _time falls back to now() (aware datetime).
        assert result.events[0].timestamp.tzinfo is not None

    async def test_search_text_block_results_dict(self, monkeypatch):
        import json as _json

        body = {"results": [{"_raw": "e", "host": "h"}]}
        payload = {"result": {"content": [{"type": "text", "text": _json.dumps(body)}]}}
        _mcp_stub(monkeypatch, payload=payload)
        result = await self._client().search("search x")
        assert result.event_count == 1

    async def test_search_ignores_non_text_and_bad_json(self, monkeypatch):
        payload = {
            "result": {
                "content": [
                    {"type": "image", "data": "x"},
                    {"type": "text", "text": "{not json"},
                ]
            }
        }
        _mcp_stub(monkeypatch, payload=payload)
        result = await self._client().search("search x")
        assert result.event_count == 0

    async def test_empty_spl_rejected(self):
        from app.splunk.client import SplunkQueryError

        with pytest.raises(SplunkQueryError):
            await self._client().search("   ")

    async def test_auth_error(self, monkeypatch):
        from app.splunk.client import SplunkAuthError

        _mcp_stub(monkeypatch, status=401)
        with pytest.raises(SplunkAuthError):
            await self._client().search("search x")

    async def test_query_error_400(self, monkeypatch):
        from app.splunk.client import SplunkQueryError

        _mcp_stub(monkeypatch, status=400)
        with pytest.raises(SplunkQueryError):
            await self._client().search("search x")

    async def test_jsonrpc_error(self, monkeypatch):
        from app.splunk.client import SplunkQueryError

        payload = {"error": {"code": -32000, "message": "bad tool"}}
        _mcp_stub(monkeypatch, payload=payload)
        with pytest.raises(SplunkQueryError):
            await self._client().search("search x")

    async def test_connect_error(self, monkeypatch):
        from app.splunk.client import SplunkConnectionError

        _mcp_stub(monkeypatch, raise_connect=True)
        with pytest.raises(SplunkConnectionError):
            await self._client().search("search x")

    async def test_health_ok(self, monkeypatch):
        _mcp_stub(monkeypatch, status=200, payload={"result": {"tools": []}})
        assert await self._client().health() is True

    async def test_health_bad_status(self, monkeypatch):
        _mcp_stub(monkeypatch, status=503, payload={})
        assert await self._client().health() is False
