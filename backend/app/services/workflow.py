"""Case workflow: status transitions and SLA timers.

Enforces a valid status lifecycle and computes SLA clocks (time-to-acknowledge,
time-to-contain) so a SOC lead can see whether cases are being worked within
target windows.
"""
from __future__ import annotations

from datetime import UTC, datetime

from app.models.domain import DetectionStatus

# Allowed forward/again transitions. Resolution states are terminal-ish but a
# case can be reopened to investigating.
_ALLOWED: dict[DetectionStatus, set[DetectionStatus]] = {
    DetectionStatus.NEW: {DetectionStatus.TRIAGED, DetectionStatus.FALSE_POSITIVE},
    DetectionStatus.TRIAGED: {
        DetectionStatus.INVESTIGATING,
        DetectionStatus.FALSE_POSITIVE,
    },
    DetectionStatus.INVESTIGATING: {
        DetectionStatus.CONTAINED,
        DetectionStatus.RESOLVED,
        DetectionStatus.FALSE_POSITIVE,
    },
    DetectionStatus.CONTAINED: {
        DetectionStatus.RESOLVED,
        DetectionStatus.INVESTIGATING,
    },
    DetectionStatus.RESOLVED: {DetectionStatus.INVESTIGATING},
    DetectionStatus.FALSE_POSITIVE: {DetectionStatus.INVESTIGATING},
}

# SLA targets in minutes.
SLA_ACKNOWLEDGE_MIN = 15
SLA_CONTAIN_MIN = 60


def can_transition(current: DetectionStatus, target: DetectionStatus) -> bool:
    return target in _ALLOWED.get(current, set())


def compute_sla(
    created_at: datetime,
    acknowledged_at: datetime | None,
    contained_at: datetime | None,
    now: datetime | None = None,
) -> dict[str, object]:
    now = now or datetime.now(UTC)

    def _aware(dt: datetime) -> datetime:
        # SQLite may return naive datetimes; treat them as UTC.
        return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)

    def _minutes(a: datetime, b: datetime) -> float:
        return round((_aware(b) - _aware(a)).total_seconds() / 60.0, 1)

    created_at = _aware(created_at)
    acknowledged_at = _aware(acknowledged_at) if acknowledged_at else None
    contained_at = _aware(contained_at) if contained_at else None

    ack_elapsed = _minutes(created_at, acknowledged_at or now)
    contain_elapsed = _minutes(created_at, contained_at or now)
    return {
        "ack_target_min": SLA_ACKNOWLEDGE_MIN,
        "ack_elapsed_min": ack_elapsed,
        "ack_breached": acknowledged_at is None and ack_elapsed > SLA_ACKNOWLEDGE_MIN,
        "contain_target_min": SLA_CONTAIN_MIN,
        "contain_elapsed_min": contain_elapsed,
        "contain_breached": contained_at is None and contain_elapsed > SLA_CONTAIN_MIN,
    }
