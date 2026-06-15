"""Tests for secret encryption, credential storage, and backend resolution."""
from __future__ import annotations

import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.models import Base, TenantCredentialRow


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


class TestCrypto:
    def test_roundtrip(self):
        from app.core.crypto import decrypt_secret, encrypt_secret

        token = encrypt_secret("super-secret-token")
        assert token != "super-secret-token"  # actually encrypted
        assert decrypt_secret(token) == "super-secret-token"

    def test_empty_passthrough(self):
        from app.core.crypto import decrypt_secret, encrypt_secret

        assert encrypt_secret("") == ""
        assert decrypt_secret("") == ""

    def test_decrypt_garbage_raises(self):
        from app.core.crypto import SecretCipherError, decrypt_secret

        try:
            decrypt_secret("not-a-valid-token")
            raise AssertionError("expected SecretCipherError")
        except SecretCipherError:
            pass


class TestCredentialRepository:
    async def test_default_view_is_managed(self, sm):
        from app.services.credentials import CredentialRepository

        async with sm() as s:
            view = await CredentialRepository(s).view("t1")
            assert view.mode == "managed"
            assert view.splunk_token_set is False

    async def test_upsert_and_secret_write_only(self, sm):
        from app.services.credentials import CredentialRepository

        async with sm() as s:
            repo = CredentialRepository(s)
            await repo.upsert(
                "t1", mode="byo", splunk_backend="live",
                splunk_host="https://splunk:8089", splunk_token="tok-123",
            )
            await s.commit()
            view = await repo.view("t1")
            # The view exposes that a token is SET but never the value.
            assert view.mode == "byo"
            assert view.splunk_host == "https://splunk:8089"
            assert view.splunk_token_set is True
            assert not hasattr(view, "splunk_token")
            # Stored value is encrypted, not plaintext.
            row = await repo.get_row("t1")
            assert row.splunk_token_enc != "tok-123"
            assert row.splunk_token_enc != ""

    async def test_none_preserves_empty_clears(self, sm):
        from app.core.crypto import decrypt_secret
        from app.services.credentials import CredentialRepository

        async with sm() as s:
            repo = CredentialRepository(s)
            await repo.upsert("t1", splunk_token="keep-me")
            await s.commit()
            # None leaves it unchanged
            await repo.upsert("t1", splunk_host="h")
            await s.commit()
            row = await repo.get_row("t1")
            assert decrypt_secret(row.splunk_token_enc) == "keep-me"
            # "" clears it
            await repo.upsert("t1", splunk_token="")
            await s.commit()
            row = await repo.get_row("t1")
            assert row.splunk_token_enc == ""

    async def test_upsert_all_fields(self, sm):
        from app.core.crypto import decrypt_secret
        from app.services.credentials import CredentialRepository

        async with sm() as s:
            repo = CredentialRepository(s)
            await repo.upsert(
                "t1", mode="byo", splunk_backend="mcp",
                splunk_mcp_url="https://x/mcp", splunk_mcp_token="mcp-tok",
                ai_backend="live", ai_model="Foundation-Sec-1.1-8B-Instruct",
                ai_token="ai-tok",
            )
            await s.commit()
            row = await repo.get_row("t1")
            assert row.splunk_mcp_url == "https://x/mcp"
            assert decrypt_secret(row.splunk_mcp_token_enc) == "mcp-tok"
            assert row.ai_backend == "live"
            assert row.ai_model == "Foundation-Sec-1.1-8B-Instruct"
            assert decrypt_secret(row.ai_token_enc) == "ai-tok"
            view = await repo.view("t1")
            assert view.splunk_mcp_token_set is True
            assert view.ai_token_set is True


class TestResolver:
    async def test_managed_returns_fallback(self, sm):
        from app.services.ai_model import MockAIModel
        from app.services.credentials import resolve_ai_model, resolve_splunk_client
        from app.splunk.mock_client import MockSplunkClient

        managed_splunk = MockSplunkClient()
        managed_ai = MockAIModel()
        # No row -> managed.
        assert resolve_splunk_client(None, managed_splunk) is managed_splunk
        assert resolve_ai_model(None, managed_ai) is managed_ai
        # Row in managed mode -> managed.
        row = TenantCredentialRow(tenant_id="t1", mode="managed")
        assert resolve_splunk_client(row, managed_splunk) is managed_splunk

    async def test_byo_builds_live_and_mcp(self, sm):
        from app.core.crypto import encrypt_secret
        from app.services.credentials import resolve_splunk_client
        from app.splunk.live_client import LiveSplunkClient
        from app.splunk.mcp_client import McpSplunkClient
        from app.splunk.mock_client import MockSplunkClient

        managed = MockSplunkClient()
        live_row = TenantCredentialRow(
            tenant_id="t1", mode="byo", splunk_backend="live",
            splunk_host="https://x:8089", splunk_token_enc=encrypt_secret("tok"),
        )
        assert isinstance(resolve_splunk_client(live_row, managed), LiveSplunkClient)
        mcp_row = TenantCredentialRow(
            tenant_id="t2", mode="byo", splunk_backend="mcp",
            splunk_mcp_url="https://x/mcp", splunk_mcp_token_enc=encrypt_secret("tok"),
        )
        assert isinstance(resolve_splunk_client(mcp_row, managed), McpSplunkClient)
        # byo + mock backend -> a fresh mock (not the managed one).
        mock_row = TenantCredentialRow(tenant_id="t3", mode="byo", splunk_backend="mock")
        assert isinstance(resolve_splunk_client(mock_row, managed), MockSplunkClient)

    async def test_byo_ai_live(self, sm):
        from app.core.crypto import encrypt_secret
        from app.services.ai_model import LiveAIModel, MockAIModel
        from app.services.credentials import resolve_ai_model

        managed = MockAIModel()
        row = TenantCredentialRow(
            tenant_id="t1", mode="byo", ai_backend="live",
            ai_model="Foundation-Sec-1.1-8B-Instruct", ai_token_enc=encrypt_secret("k"),
            splunk_host="https://model:8089",
        )
        assert isinstance(resolve_ai_model(row, managed), LiveAIModel)
