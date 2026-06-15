"""Triage agent.

Uses a Splunk hosted model to assess whether a detection is a true positive,
assign confidence, and recommend severity + actions. Falls back safely if the
model returns malformed output.
"""
from __future__ import annotations

from app.models.domain import Detection, Severity, TriageVerdict
from app.services.ai_model import AIModel, AIModelError

_SYSTEM = (
    "You are a senior SOC analyst performing alert triage. "
    "Given a detection, decide whether it is a true positive and return a JSON "
    "verdict with keys: is_true_positive (bool), confidence (0-1), rationale "
    "(string), recommended_severity (one of info/low/medium/high/critical), "
    "suggested_actions (list of strings)."
)


class TriageAgent:
    def __init__(self, model: AIModel):
        self._model = model

    async def triage(self, detection: Detection) -> TriageVerdict:
        prompt = (
            f"Detection: {detection.title}\n"
            f"Description: {detection.description}\n"
            f"Entity: {detection.entity}\n"
            f"Event count: {detection.event_count}\n"
            f"SPL: {detection.spl_query}\n"
            f"MITRE: {', '.join(detection.mitre_tactics)}\n"
            "Provide your triage verdict as JSON."
        )
        try:
            data = await self._model.complete_json(_SYSTEM, prompt)
        except AIModelError:
            # Safe fallback: treat as needs-review at original severity.
            return TriageVerdict(
                detection_id=detection.id,
                is_true_positive=True,
                confidence=0.5,
                rationale="Model output unavailable; defaulting to analyst review.",
                recommended_severity=detection.severity,
                suggested_actions=["manual_review"],
            )
        return TriageVerdict(
            detection_id=detection.id,
            is_true_positive=bool(data.get("is_true_positive", False)),
            confidence=_clamp(float(data.get("confidence", 0.0))),
            rationale=str(data.get("rationale", "")),
            recommended_severity=_coerce_severity(data.get("recommended_severity")),
            suggested_actions=[str(a) for a in data.get("suggested_actions", [])],
        )


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _coerce_severity(value: object) -> Severity:
    try:
        return Severity(str(value).lower())
    except ValueError:
        return Severity.MEDIUM
