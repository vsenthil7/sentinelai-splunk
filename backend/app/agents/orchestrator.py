"""Agentic orchestrator.

Chains the detection, enrichment, triage, and response agents into full
investigations: detect -> enrich -> triage -> plan response -> summarize.
This is the agentic loop the product exposes to the SOC analyst.
"""
from __future__ import annotations

import uuid

from app.agents.detection_agent import DetectionAgent
from app.agents.response_agent import ResponseAgent
from app.agents.triage_agent import TriageAgent
from app.models.domain import Detection, DetectionStatus, Investigation
from app.services.ai_model import AIModel
from app.services.enrichment import (
    EnrichmentService,
    MockEnrichmentProvider,
)
from app.splunk.client import SplunkClient

_SUMMARY_SYSTEM = (
    "You are a SOC lead writing a concise incident summary for stakeholders. "
    "Summarize the detection, the triage verdict, and the planned actions in 2-3 sentences."
)


class Orchestrator:
    def __init__(
        self,
        splunk: SplunkClient,
        model: AIModel,
        enrichment: EnrichmentService | None = None,
    ):
        self._detector = DetectionAgent(splunk)
        self._triager = TriageAgent(model)
        self._responder = ResponseAgent()
        self._model = model
        self._enrichment = enrichment or EnrichmentService(MockEnrichmentProvider())

    async def run_detections(self, disabled_rule_ids: set[str] | None = None) -> list[Detection]:
        return await self._detector.run(disabled_rule_ids)

    async def run_full_pipeline(
        self, disabled_rule_ids: set[str] | None = None
    ) -> list[Investigation]:
        detections = await self.run_detections(disabled_rule_ids)
        return [await self.investigate(d) for d in detections]

    async def investigate(self, detection: Detection) -> Investigation:
        # Enrich first so triage and risk scoring have context.
        enrichment = await self._enrichment.enrich(
            host=detection.entity,
            user=detection.users[0] if detection.users else None,
            ips=detection.src_ips,
        )
        detection.enrichment = {
            "threat_intel": enrichment.threat_intel,
            "asset_criticality": enrichment.asset_criticality,
            "identity_context": enrichment.identity_context,
            "indicators": enrichment.indicators,
            "risk_boost": round(enrichment.boost(), 3),
        }

        verdict = await self._triager.triage(detection)
        actions = self._responder.plan(detection, verdict)
        status = (
            DetectionStatus.INVESTIGATING
            if verdict.is_true_positive
            else DetectionStatus.FALSE_POSITIVE
        )
        detection.status = status
        detection.severity = verdict.recommended_severity

        timeline = [
            f"Detection raised: {detection.title} on {detection.entity}",
            f"Enrichment: asset={enrichment.asset_criticality}, "
            f"TI={enrichment.threat_intel.get('verdict', 'n/a')}, "
            f"indicators={len(enrichment.indicators)}",
            f"Triage verdict: {'TRUE' if verdict.is_true_positive else 'FALSE'} positive "
            f"(confidence {verdict.confidence:.2f})",
        ]
        timeline += [f"Action planned: {a.action_type} -> {a.target}" for a in actions]

        summary = await self._model.complete(
            _SUMMARY_SYSTEM,
            f"Detection: {detection.title}; Asset criticality: "
            f"{enrichment.asset_criticality}; Verdict TP={verdict.is_true_positive}; "
            f"Actions: {[a.action_type for a in actions]}",
        )

        return Investigation(
            id=f"INV-{uuid.uuid4().hex[:8]}",
            detection=detection,
            verdict=verdict,
            timeline=timeline,
            actions=actions,
            summary=summary,
        )
