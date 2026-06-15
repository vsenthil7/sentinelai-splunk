"""Detection agent.

Runs a library of SPL detection rules against Splunk and converts hits into
``Detection`` objects. Rules are data, so adding coverage = adding a rule.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.core.resilience import CircuitBreaker, with_retry
from app.models.domain import Detection, SearchResult, Severity
from app.splunk.client import SplunkClient, SplunkQueryError


@dataclass(frozen=True)
class DetectionRule:
    rule_id: str
    title: str
    description: str
    spl: str
    base_severity: Severity
    mitre_tactics: tuple[str, ...]
    min_events: int = 1


# Curated rule library (extensible). Each maps to a MITRE tactic.
DEFAULT_RULES: tuple[DetectionRule, ...] = (
    DetectionRule(
        rule_id="R001",
        title="Brute-force authentication",
        description="High volume of failed authentication attempts against a host.",
        spl="search index=auth action=failure failed authentication",
        base_severity=Severity.HIGH,
        mitre_tactics=("TA0006",),  # Credential Access
        min_events=10,
    ),
    DetectionRule(
        rule_id="R002",
        title="Suspicious outbound network traffic",
        description="Outbound connections on uncommon ports with large transfer volume.",
        spl="search index=network firewall bytes > 500000",
        base_severity=Severity.HIGH,
        mitre_tactics=("TA0010",),  # Exfiltration
        min_events=1,
    ),
    DetectionRule(
        rule_id="R003",
        title="Encoded PowerShell execution",
        description="PowerShell launched with an encoded command from an Office parent process.",
        spl="search index=endpoint process powershell encoded",
        base_severity=Severity.CRITICAL,
        mitre_tactics=("TA0002", "TA0005"),  # Execution, Defense Evasion
        min_events=1,
    ),
    DetectionRule(
        rule_id="R004",
        title="Successful login after brute force",
        description="Successful authentication following a burst of failures (likely compromise).",
        spl="search index=auth failed authentication action=success",
        base_severity=Severity.CRITICAL,
        mitre_tactics=("TA0006", "TA0001"),  # Credential Access, Initial Access
        min_events=10,
    ),
    DetectionRule(
        rule_id="R005",
        title="Privilege escalation attempt",
        description="Unexpected addition of an account to a privileged group.",
        spl="search index=endpoint process privilege escalation",
        base_severity=Severity.HIGH,
        mitre_tactics=("TA0004",),  # Privilege Escalation
        min_events=1,
    ),
)


class DetectionAgent:
    def __init__(self, splunk: SplunkClient, rules: tuple[DetectionRule, ...] = DEFAULT_RULES):
        self._splunk = splunk
        self._rules = rules
        self._breaker = CircuitBreaker()

    async def run(self, disabled_rule_ids: set[str] | None = None) -> list[Detection]:
        disabled = disabled_rule_ids or set()
        detections: list[Detection] = []
        for rule in self._rules:
            if rule.rule_id in disabled:
                continue

            async def _do_search(r: DetectionRule = rule) -> SearchResult:
                return await self._splunk.search(r.spl)

            result = await with_retry(
                _do_search,
                attempts=3,
                breaker=self._breaker,
                dont_retry=(SplunkQueryError,),
            )
            if result.event_count < rule.min_events:
                continue
            entity = result.events[0].host if result.events else "unknown"
            src_ips = sorted(
                {
                    e.fields[key]
                    for e in result.events
                    for key in ("src_ip", "dest_ip")
                    if key in e.fields
                }
            )
            users = sorted(
                {e.fields["user"] for e in result.events if "user" in e.fields}
            )
            detections.append(
                Detection(
                    id=f"DET-{uuid.uuid4().hex[:8]}",
                    title=rule.title,
                    description=rule.description,
                    severity=rule.base_severity,
                    spl_query=rule.spl,
                    entity=entity,
                    event_count=result.event_count,
                    mitre_tactics=list(rule.mitre_tactics),
                    src_ips=src_ips,
                    users=users,
                )
            )
        return detections
