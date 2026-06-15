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
