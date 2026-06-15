"""Domain models shared across the agentic security pipeline."""
from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, Field


def _now() -> datetime:
    return datetime.now(UTC)


class Severity(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class DetectionStatus(str, Enum):
    NEW = "new"
    TRIAGED = "triaged"
    INVESTIGATING = "investigating"
    CONTAINED = "contained"
    RESOLVED = "resolved"
    FALSE_POSITIVE = "false_positive"


class SplunkEvent(BaseModel):
    """A raw event row returned from a Splunk search."""

    raw: str
    source: str
    sourcetype: str
    host: str
    timestamp: datetime = Field(default_factory=_now)
    fields: dict[str, str] = Field(default_factory=dict)


class SearchResult(BaseModel):
    sid: str
    query: str
    event_count: int
    events: list[SplunkEvent] = Field(default_factory=list)


class Detection(BaseModel):
    id: str
    title: str
    description: str
    severity: Severity
    status: DetectionStatus = DetectionStatus.NEW
    spl_query: str
    entity: str  # affected host/user/ip
    event_count: int = 0
    created_at: datetime = Field(default_factory=_now)
    mitre_tactics: list[str] = Field(default_factory=list)
    src_ips: list[str] = Field(default_factory=list)
    users: list[str] = Field(default_factory=list)
    enrichment: dict[str, object] = Field(default_factory=dict)


class TriageVerdict(BaseModel):
    detection_id: str
    is_true_positive: bool
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str
    recommended_severity: Severity
    suggested_actions: list[str] = Field(default_factory=list)


class IncidentAction(BaseModel):
    action_type: str  # e.g. "isolate_host", "disable_user", "block_ip"
    target: str
    rationale: str
    requires_approval: bool = True
    executed: bool = False
    execution_status: str | None = None  # success | failed | unsupported
    execution_detail: str | None = None
    rollback_token: str | None = None


class Investigation(BaseModel):
    id: str
    detection: Detection
    verdict: TriageVerdict | None = None
    timeline: list[str] = Field(default_factory=list)
    actions: list[IncidentAction] = Field(default_factory=list)
    summary: str = ""
    assignee: str | None = None
    created_at: datetime = Field(default_factory=_now)


class Incident(BaseModel):
    """A correlated group of investigations sharing an entity or indicators."""

    id: str
    title: str
    entity: str
    severity: Severity
    risk_score: int = 0
    investigation_ids: list[str] = Field(default_factory=list)
    indicators: list[str] = Field(default_factory=list)
    mitre_tactics: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_now)
