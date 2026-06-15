"""API-layer schemas (request/response DTOs)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.domain import Investigation


class LoginRequest(BaseModel):
    username: str
    password: str
    tenant: str = "default"


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    tenant: str


class SearchRequest(BaseModel):
    spl: str
    earliest: str = "-24h"
    latest: str = "now"


class ApprovalRequest(BaseModel):
    action_index: int


class AssignRequest(BaseModel):
    assignee: str | None = None


class NoteRequest(BaseModel):
    body: str = Field(min_length=1, max_length=5000)


class StatusRequest(BaseModel):
    status: str


class SLAResponse(BaseModel):
    ack_target_min: int
    ack_elapsed_min: float
    ack_breached: bool
    contain_target_min: int
    contain_elapsed_min: float
    contain_breached: bool


class NoteResponse(BaseModel):
    id: str
    author: str
    body: str
    created_at: datetime


class HealthResponse(BaseModel):
    status: str
    splunk: bool
    backend: str


class InvestigationList(BaseModel):
    investigations: list[Investigation]
    total: int
    limit: int
    offset: int


class AuditEntryResponse(BaseModel):
    id: int
    actor: str
    action: str
    target_type: str
    target_id: str
    detail: dict[str, object]
    entry_hash: str
    created_at: datetime


class AuditListResponse(BaseModel):
    entries: list[AuditEntryResponse]
    chain_valid: bool


class CreateUserRequest(BaseModel):
    username: str = Field(min_length=1, max_length=150)
    password: str = Field(min_length=8, max_length=200)
    role: str = "analyst"


class UpdateRoleRequest(BaseModel):
    role: str


class LinkIdentityRequest(BaseModel):
    external_id: str = Field(min_length=1, max_length=255)


class UserResponse(BaseModel):
    id: str
    username: str
    role: str
    external_id: str | None = None
    created_at: datetime


class RuleResponse(BaseModel):
    rule_id: str
    title: str
    description: str
    base_severity: str
    mitre_tactics: list[str]
    enabled: bool


class RuleToggleRequest(BaseModel):
    enabled: bool


class MitreCoverageResponse(BaseModel):
    coverage: dict[str, int]  # tactic -> number of enabled rules
    total_rules: int
    enabled_rules: int


# ---- Provider plane (cross-tenant, PROVIDER_ADMIN only) ----


class TenantResponse(BaseModel):
    id: str
    name: str
    status: str
    plan: str
    user_count: int
    created_at: datetime


class CreateTenantRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    plan: str = "pro"
    status: str = "active"
    admin_username: str = Field(min_length=1, max_length=150)
    admin_password: str = Field(min_length=8, max_length=200)


class TenantStatusRequest(BaseModel):
    status: str  # active | suspended | trial


class TenantPlanRequest(BaseModel):
    plan: str  # free | pro | enterprise


class ProviderUserResponse(BaseModel):
    id: str
    username: str
    role: str
    tenant_id: str
    tenant_name: str


class ImpersonateResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    tenant: str
    role: str
    impersonated_user: str


# ---- Tenant self-service settings + BYO credentials (tenant ADMIN) ----


class CredentialView(BaseModel):
    """Non-secret view. Secrets shown only as *_set booleans, never values."""

    mode: str
    splunk_backend: str
    splunk_host: str
    splunk_token_set: bool
    splunk_mcp_url: str
    splunk_mcp_token_set: bool
    ai_backend: str
    ai_model: str
    ai_token_set: bool


class UpdateCredentialsRequest(BaseModel):
    # None = leave unchanged; "" = clear. Secrets are write-only.
    mode: str | None = None  # managed | byo
    splunk_backend: str | None = None  # mock | live | mcp
    splunk_host: str | None = None
    splunk_token: str | None = None
    splunk_mcp_url: str | None = None
    splunk_mcp_token: str | None = None
    ai_backend: str | None = None  # mock | live
    ai_model: str | None = None
    ai_token: str | None = None


class TenantSettingsResponse(BaseModel):
    tenant: str
    plan: str
    status: str
    settings: dict[str, object]


class UpdateSettingsRequest(BaseModel):
    settings: dict[str, object]


class UsageRollupResponse(BaseModel):
    tenant: str
    by_kind: dict[str, dict[str, int]]  # kind -> {quantity, cost_cents}
    total_cost_cents: int
    total_cost_usd: float


class ProviderUsageRow(BaseModel):
    tenant_id: str
    tenant_name: str
    plan: str
    total_cost_cents: int
    total_cost_usd: float


class ProviderUsageResponse(BaseModel):
    tenants: list[ProviderUsageRow]
    grand_total_cents: int
    grand_total_usd: float
