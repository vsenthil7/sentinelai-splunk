"""Per-tenant credential storage and backend resolution.

Two responsibilities:
1. ``CredentialRepository`` — read/write a tenant's integration config, with
   secrets encrypted at rest (Fernet) and never returned in plaintext.
2. ``resolve_splunk_client`` / ``resolve_ai_model`` — build the right backend for
   a tenant at request time:
     - mode == "managed": use the platform's shared client (env-configured).
     - mode == "byo": construct a client from the tenant's own decrypted creds.

This is what makes the product real multi-tenant SaaS: two tenants can target
different Splunk instances (or the managed mock) within one running server,
selected per request, without sharing secrets.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt_secret, encrypt_secret
from app.db.models import TenantCredentialRow
from app.services.ai_model import AIModel, LiveAIModel, MockAIModel
from app.splunk.client import SplunkClient
from app.splunk.live_client import LiveSplunkClient
from app.splunk.mcp_client import McpSplunkClient
from app.splunk.mock_client import MockSplunkClient


@dataclass
class CredentialView:
    """Non-secret view of a tenant's credential config (safe to return via API).

    Secret fields are represented only as booleans (``*_set``) so the UI can show
    whether a value exists without ever exposing it.
    """

    mode: str
    splunk_backend: str
    splunk_host: str
    splunk_token_set: bool
    splunk_mcp_url: str
    splunk_mcp_token_set: bool
    ai_backend: str
    ai_model: str
    ai_token_set: bool


class CredentialRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_row(self, tenant_id: str) -> TenantCredentialRow | None:
        return await self._session.get(TenantCredentialRow, tenant_id)

    async def view(self, tenant_id: str) -> CredentialView:
        row = await self.get_row(tenant_id)
        if row is None:
            return CredentialView(
                mode="managed", splunk_backend="mock", splunk_host="",
                splunk_token_set=False, splunk_mcp_url="", splunk_mcp_token_set=False,
                ai_backend="mock", ai_model="", ai_token_set=False,
            )
        return CredentialView(
            mode=row.mode,
            splunk_backend=row.splunk_backend,
            splunk_host=row.splunk_host,
            splunk_token_set=bool(row.splunk_token_enc),
            splunk_mcp_url=row.splunk_mcp_url,
            splunk_mcp_token_set=bool(row.splunk_mcp_token_enc),
            ai_backend=row.ai_backend,
            ai_model=row.ai_model,
            ai_token_set=bool(row.ai_token_enc),
        )

    async def upsert(
        self,
        tenant_id: str,
        *,
        mode: str | None = None,
        splunk_backend: str | None = None,
        splunk_host: str | None = None,
        splunk_token: str | None = None,
        splunk_mcp_url: str | None = None,
        splunk_mcp_token: str | None = None,
        ai_backend: str | None = None,
        ai_model: str | None = None,
        ai_token: str | None = None,
    ) -> TenantCredentialRow:
        """Create or update; secret args are encrypted. None = leave unchanged.

        Passing an empty string for a secret clears it; passing None preserves
        the existing stored value.
        """
        row = await self.get_row(tenant_id)
        if row is None:
            row = TenantCredentialRow(tenant_id=tenant_id)
            self._session.add(row)
        if mode is not None:
            row.mode = mode
        if splunk_backend is not None:
            row.splunk_backend = splunk_backend
        if splunk_host is not None:
            row.splunk_host = splunk_host
        if splunk_token is not None:
            row.splunk_token_enc = encrypt_secret(splunk_token)
        if splunk_mcp_url is not None:
            row.splunk_mcp_url = splunk_mcp_url
        if splunk_mcp_token is not None:
            row.splunk_mcp_token_enc = encrypt_secret(splunk_mcp_token)
        if ai_backend is not None:
            row.ai_backend = ai_backend
        if ai_model is not None:
            row.ai_model = ai_model
        if ai_token is not None:
            row.ai_token_enc = encrypt_secret(ai_token)
        await self._session.flush()
        return row


def resolve_splunk_client(
    row: TenantCredentialRow | None, managed: SplunkClient
) -> SplunkClient:
    """Pick a Splunk client for a tenant: managed fallback, or BYO from creds."""
    if row is None or row.mode != "byo":
        return managed
    if row.splunk_backend == "live":
        return LiveSplunkClient(
            host=row.splunk_host, token=decrypt_secret(row.splunk_token_enc)
        )
    if row.splunk_backend == "mcp":
        return McpSplunkClient(
            url=row.splunk_mcp_url, token=decrypt_secret(row.splunk_mcp_token_enc)
        )
    return MockSplunkClient()


def resolve_ai_model(row: TenantCredentialRow | None, managed: AIModel) -> AIModel:
    """Pick an AI model for a tenant: managed fallback, or BYO from creds."""
    if row is None or row.mode != "byo":
        return managed
    if row.ai_backend == "live":
        return LiveAIModel(
            base_url=row.splunk_mcp_url or row.splunk_host,
            model=row.ai_model or "Foundation-Sec-1.1-8B-Instruct",
            token=decrypt_secret(row.ai_token_enc),
        )
    return MockAIModel()
