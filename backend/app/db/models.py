"""ORM models. Every business row carries a tenant_id for isolation."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _uuid() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class TenantRow(Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    # SaaS lifecycle: active | suspended | trial. Suspended tenants are blocked
    # at authentication (see api/deps). Trial implies a time-boxed evaluation.
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    # Commercial edition: free | pro | enterprise. Drives quotas (SP9).
    plan: Mapped[str] = mapped_column(String(20), default="enterprise")
    trial_ends_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Per-tenant non-secret settings (display prefs, notification routing, etc.).
    settings: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class UserRow(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(32), ForeignKey("tenants.id"), index=True)
    username: Mapped[str] = mapped_column(String(150), index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(50), default="analyst")
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)  # SSO subject
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class InvestigationRow(Base):
    __tablename__ = "investigations"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(32), ForeignKey("tenants.id"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    severity: Mapped[str] = mapped_column(String(20), index=True)
    status: Mapped[str] = mapped_column(String(30), index=True)
    entity: Mapped[str] = mapped_column(String(200), index=True)
    risk_score: Mapped[int] = mapped_column(Integer, default=0, index=True)
    is_true_positive: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    # Full aggregate snapshot (detection, verdict, timeline, actions, summary)
    payload: Mapped[dict[str, object]] = mapped_column(JSON)
    assignee: Mapped[str | None] = mapped_column(String(150), nullable=True, index=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    contained_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    notes: Mapped[list[CaseNoteRow]] = relationship(
        back_populates="investigation", cascade="all, delete-orphan"
    )


class CaseNoteRow(Base):
    __tablename__ = "case_notes"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    investigation_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("investigations.id"), index=True
    )
    tenant_id: Mapped[str] = mapped_column(String(32), index=True)
    author: Mapped[str] = mapped_column(String(150))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    investigation: Mapped[InvestigationRow] = relationship(back_populates="notes")


class RuleStateRow(Base):
    """Per-tenant enable/disable state for a detection rule."""

    __tablename__ = "rule_states"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(32), ForeignKey("tenants.id"), index=True)
    rule_id: Mapped[str] = mapped_column(String(20), index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class IncidentRow(Base):
    __tablename__ = "incidents"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(32), ForeignKey("tenants.id"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    entity: Mapped[str] = mapped_column(String(200), index=True)
    severity: Mapped[str] = mapped_column(String(20), index=True)
    risk_score: Mapped[int] = mapped_column(Integer, default=0, index=True)
    payload: Mapped[dict[str, object]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AuditLogRow(Base):
    """Append-only, hash-chained audit trail.

    Each row stores the hash of the previous row for the tenant, making any
    deletion or modification detectable (tamper-evidence).
    """

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(32), index=True)
    actor: Mapped[str] = mapped_column(String(150), index=True)
    action: Mapped[str] = mapped_column(String(100), index=True)
    target_type: Mapped[str] = mapped_column(String(50))
    target_id: Mapped[str] = mapped_column(String(64))
    detail: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    prev_hash: Mapped[str] = mapped_column(String(64), default="")
    entry_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class UsageEventRow(Base):
    """A metered, billable usage event for a tenant.

    ``kind`` is one of: search | model_call | tokens | action. ``quantity`` is
    the count (searches, calls, tokens, actions). ``cost_cents`` is the computed
    cost at record time per the active price book (denormalized so historical
    cost is stable even if the price book later changes).
    """

    __tablename__ = "usage_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(32), index=True)
    kind: Mapped[str] = mapped_column(String(20), index=True)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    cost_cents: Mapped[int] = mapped_column(Integer, default=0)
    detail: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, index=True
    )


class TenantCredentialRow(Base):
    """Per-tenant integration credentials. Secret fields are encrypted at rest.

    ``mode`` selects how the tenant's Splunk/model backends are sourced:
      - ``managed``  : use the platform's shared credentials (env-configured).
      - ``byo``      : use the tenant's own credentials stored here (encrypted).
    Secret columns hold Fernet tokens, never plaintext, and are never returned
    by the API (write-only).
    """

    __tablename__ = "tenant_credentials"

    tenant_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("tenants.id"), primary_key=True
    )
    mode: Mapped[str] = mapped_column(String(20), default="managed")
    # Splunk backend selection for this tenant: mock | live | mcp (when byo).
    splunk_backend: Mapped[str] = mapped_column(String(10), default="mock")
    splunk_host: Mapped[str] = mapped_column(String(300), default="")
    splunk_token_enc: Mapped[str] = mapped_column(Text, default="")
    splunk_mcp_url: Mapped[str] = mapped_column(String(300), default="")
    splunk_mcp_token_enc: Mapped[str] = mapped_column(Text, default="")
    # AI/model backend for this tenant: mock | live (when byo).
    ai_backend: Mapped[str] = mapped_column(String(10), default="mock")
    ai_model: Mapped[str] = mapped_column(String(120), default="")
    ai_token_enc: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class RevokedTokenRow(Base):
    """Denylist of revoked JWT IDs (jti). Supports server-side logout.

    Rows can be purged after the token's original expiry; until then the jti
    blocks reuse of a token that was explicitly logged out.
    """

    __tablename__ = "revoked_tokens"

    jti: Mapped[str] = mapped_column(String(32), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(32), index=True)
    revoked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
