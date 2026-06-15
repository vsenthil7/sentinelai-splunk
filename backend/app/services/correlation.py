"""Incident correlation.

Groups investigations that are likely the same incident so analysts triage once
instead of chasing duplicate alerts. Grouping key: shared affected entity, OR
overlapping threat indicators. Severity/risk roll up to the max of members.
"""
from __future__ import annotations

import uuid

from app.models.domain import Incident, Investigation, Severity

_SEV_ORDER = {
    Severity.INFO: 0,
    Severity.LOW: 1,
    Severity.MEDIUM: 2,
    Severity.HIGH: 3,
    Severity.CRITICAL: 4,
}


def _indicators_of(inv: Investigation) -> set[str]:
    raw = inv.detection.enrichment.get("indicators", [])
    indicators = set(raw) if isinstance(raw, list) else set()
    indicators.update(inv.detection.src_ips)
    return indicators


def correlate(investigations: list[Investigation]) -> list[Incident]:
    """Union-find style grouping by shared entity or overlapping indicators."""
    groups: list[list[Investigation]] = []
    group_keys: list[tuple[set[str], set[str]]] = []  # (entities, indicators)

    for inv in investigations:
        entity = {inv.detection.entity}
        indicators = _indicators_of(inv)
        placed = False
        for i, (g_entities, g_indicators) in enumerate(group_keys):
            if entity & g_entities or (indicators and indicators & g_indicators):
                groups[i].append(inv)
                g_entities |= entity
                g_indicators |= indicators
                placed = True
                break
        if not placed:
            groups.append([inv])
            group_keys.append((set(entity), set(indicators)))

    incidents: list[Incident] = []
    for members in groups:
        top = max(members, key=lambda m: _SEV_ORDER.get(m.detection.severity, 0))
        all_indicators: set[str] = set()
        tactics: set[str] = set()
        for m in members:
            all_indicators |= _indicators_of(m)
            tactics.update(m.detection.mitre_tactics)
        incidents.append(
            Incident(
                id=f"INC-{uuid.uuid4().hex[:8]}",
                title=top.detection.title
                if len(members) == 1
                else f"{top.detection.title} (+{len(members) - 1} related)",
                entity=top.detection.entity,
                severity=top.detection.severity,
                investigation_ids=[m.id for m in members],
                indicators=sorted(all_indicators),
                mitre_tactics=sorted(tactics),
            )
        )
    return incidents
